import hashlib
import json
import logging
import threading
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.certificates.generator import generate_certificate_pdf
from app.core.config import settings
from app.db.models.certificate import Certificate, CertificateStatus
from app.db.models.generation_job import GenerationJob, JobStatus
from app.schemas.job import RECIPIENT_ADAPTER, GenerationJobCreate, RecipientInput

logger = logging.getLogger(__name__)
_LOCAL_JOB_LOCKS: dict[str, threading.RLock] = {}
_LOCAL_JOB_LOCKS_GUARD = threading.Lock()


@contextmanager
def _job_lock(db: Session, job_id: str):
    """Serialize processing for one job across worker processes and threads."""
    bind = db.get_bind()
    if bind.dialect.name == "postgresql":
        lock_key = f"bulk-certificate-generator:{job_id}"
        db.execute(
            text("SELECT pg_advisory_lock(hashtextextended(:lock_key, 0))"),
            {"lock_key": lock_key},
        )
        try:
            yield
        finally:
            try:
                db.execute(
                    text("SELECT pg_advisory_unlock(hashtextextended(:lock_key, 0))"),
                    {"lock_key": lock_key},
                )
            except Exception:
                logger.exception("Could not release PostgreSQL advisory lock for job %s", job_id)
        return

    with _LOCAL_JOB_LOCKS_GUARD:
        lock = _LOCAL_JOB_LOCKS.setdefault(job_id, threading.RLock())
    with lock:
        yield


def _request_fingerprint(payload: GenerationJobCreate) -> str:
    canonical = payload.model_dump(mode="json", exclude={"idempotency_key"})
    serialized = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def get_idempotent_job_or_raise(db: Session, payload: GenerationJobCreate) -> GenerationJob | None:
    if not payload.idempotency_key:
        return None
    existing = db.scalar(
        select(GenerationJob).where(GenerationJob.idempotency_key == payload.idempotency_key)
    )
    if existing is None:
        return None
    fingerprint = _request_fingerprint(payload)
    if existing.request_fingerprint and existing.request_fingerprint != fingerprint:
        raise ValueError(
            "The idempotency key was already used for a different generation request."
        )
    return existing


def create_job(db: Session, payload: GenerationJobCreate) -> GenerationJob:
    existing = get_idempotent_job_or_raise(db, payload)
    if existing:
        return existing
    fingerprint = _request_fingerprint(payload) if payload.idempotency_key else None

    job = GenerationJob(
        total_count=len(payload.recipients),
        idempotency_key=payload.idempotency_key,
        request_fingerprint=fingerprint,
        certificate_title=payload.certificate.title,
        course_name=payload.certificate.course_name,
        completion_date=payload.certificate.completion_date,
        issuer_name=payload.certificate.issuer_name,
        issuer_designation=payload.certificate.issuer_designation,
    )
    db.add(job)
    db.flush()

    invalid_count = 0
    pending_count = 0
    seen_recipients: set[tuple[str, str | None]] = set()

    for index, raw_recipient in enumerate(payload.recipients, start=1):
        recipient, error = _validate_recipient(raw_recipient, index)
        if recipient is not None:
            email_key = str(recipient.email).casefold() if recipient.email else None
            key = (recipient.name.casefold(), email_key)
            if key in seen_recipients:
                recipient = None
                error = f"Recipient #{index}: duplicate recipient in the same request."
            else:
                seen_recipients.add(key)

        if recipient is None:
            invalid_count += 1
            db.add(
                Certificate(
                    job_id=job.id,
                    recipient_name=_safe_display_name(raw_recipient, index),
                    recipient_email=None,
                    status=CertificateStatus.FAILED,
                    error_message=error,
                    completed_at=datetime.now(UTC),
                )
            )
            continue

        pending_count += 1
        db.add(
            Certificate(
                job_id=job.id,
                recipient_name=recipient.name,
                recipient_email=str(recipient.email) if recipient.email is not None else None,
                status=CertificateStatus.PENDING,
            )
        )

    job.pending_count = pending_count
    job.processing_count = 0
    job.completed_count = 0
    job.failed_count = invalid_count
    job.error_summary = (
        f"{invalid_count} of {job.total_count} recipient(s) failed input validation."
        if invalid_count
        else None
    )

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if payload.idempotency_key:
            existing = db.scalar(
                select(GenerationJob).where(
                    GenerationJob.idempotency_key == payload.idempotency_key
                )
            )
            if existing:
                if existing.request_fingerprint and existing.request_fingerprint != fingerprint:
                    raise ValueError(
                    "The idempotency key was already used for a different generation request."
                    ) from None
                return existing
        raise

    db.refresh(job)

    if pending_count == 0:
        job.status = (
            JobStatus.COMPLETED_WITH_ERRORS if invalid_count else JobStatus.COMPLETED
        )
        job.completed_at = datetime.now(UTC)
        db.commit()
        db.refresh(job)

    return job


def get_job(db: Session, job_id: str) -> GenerationJob | None:
    return db.scalar(select(GenerationJob).where(GenerationJob.id == job_id))


def get_job_counts(db: Session, job_id: str) -> dict[CertificateStatus, int]:
    rows = db.execute(
        select(Certificate.status, func.count(Certificate.id))
        .where(Certificate.job_id == job_id)
        .group_by(Certificate.status)
    ).all()
    return {status: int(count) for status, count in rows}


def process_job(job_id: str) -> None:
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        with _job_lock(db, job_id):
            job = get_job(db, job_id)
            if not job:
                logger.error("Job %s not found", job_id)
                return
            if job.status in {JobStatus.COMPLETED, JobStatus.COMPLETED_WITH_ERRORS}:
                return

            _reconcile_job_counts(db, job)
            if job.processing_count:
                # A previous worker died while this job was active. The database lock
                # guarantees nobody else can be processing it while we recover it.
                db.execute(
                    update(Certificate)
                    .where(
                        Certificate.job_id == job.id,
                        Certificate.status == CertificateStatus.PROCESSING,
                    )
                    .values(status=CertificateStatus.PENDING)
                )
                job.pending_count += job.processing_count
                job.processing_count = 0
                db.commit()

            job.status = JobStatus.PROCESSING
            job.started_at = job.started_at or datetime.now(UTC)
            job.completed_at = None
            db.commit()

            while True:
                certificate = _claim_next_certificate(db, job)
                if certificate is None:
                    break
                _process_one(db, job, certificate)

            _finalize_job(db, job)
    finally:
        db.close()


def _claim_next_certificate(db: Session, job: GenerationJob) -> Certificate | None:
    if job.pending_count <= 0:
        return None

    certificate = db.scalar(
        select(Certificate)
        .where(
            Certificate.job_id == job.id,
            Certificate.status == CertificateStatus.PENDING,
        )
        .order_by(Certificate.created_at, Certificate.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if certificate is None:
        job.pending_count = 0
        db.commit()
        return None

    certificate.status = CertificateStatus.PROCESSING
    job.pending_count -= 1
    job.processing_count += 1
    db.commit()
    return certificate


def _process_one(db: Session, job: GenerationJob, cert: Certificate) -> None:
    try:
        output_dir = Path(settings.storage_dir) / job.id
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{cert.id}.pdf"
        generate_certificate_pdf(
            output_path=output_path,
            certificate_id=cert.id,
            recipient_name=cert.recipient_name,
            title=job.certificate_title,
            course_name=job.course_name,
            completion_date=job.completion_date,
            issuer_name=job.issuer_name,
            issuer_designation=job.issuer_designation,
        )
        cert.file_path = str(output_path)
        cert.status = CertificateStatus.COMPLETED
        cert.completed_at = datetime.now(UTC)
        job.processing_count = max(0, job.processing_count - 1)
        job.completed_count += 1
        db.commit()
        logger.info("Certificate %s generated", cert.id)
    except Exception as exc:  # isolate one recipient failure
        db.rollback()
        cert = db.get(Certificate, cert.id)
        job = db.get(GenerationJob, job.id)
        if cert is None or job is None:
            raise
        cert.status = CertificateStatus.FAILED
        cert.error_message = _safe_error(exc)
        cert.completed_at = datetime.now(UTC)
        job.processing_count = max(0, job.processing_count - 1)
        job.failed_count += 1
        db.commit()
        logger.exception("Certificate %s failed", cert.id)


def _reconcile_job_counts(db: Session, job: GenerationJob) -> None:
    counts = get_job_counts(db, job.id)
    job.pending_count = counts.get(CertificateStatus.PENDING, 0)
    job.processing_count = counts.get(CertificateStatus.PROCESSING, 0)
    job.completed_count = counts.get(CertificateStatus.COMPLETED, 0)
    job.failed_count = counts.get(CertificateStatus.FAILED, 0)
    db.commit()


def _finalize_job(db: Session, job: GenerationJob) -> None:
    processed = job.completed_count + job.failed_count
    if processed < job.total_count:
        job.status = JobStatus.FAILED
        job.error_summary = (
            f"Generation stopped before all recipients were processed: "
            f"{processed} of {job.total_count} processed."
        )
    elif job.failed_count == 0:
        job.status = JobStatus.COMPLETED
        job.error_summary = None
    else:
        job.status = JobStatus.COMPLETED_WITH_ERRORS
        job.error_summary = f"{job.failed_count} of {job.total_count} certificate(s) failed."

    job.completed_at = datetime.now(UTC)
    db.commit()


def _validate_recipient(raw_recipient: Any, index: int) -> tuple[RecipientInput | None, str | None]:
    if not isinstance(raw_recipient, dict):
        return None, f"Recipient #{index}: must be a JSON object."

    try:
        return RECIPIENT_ADAPTER.validate_python(raw_recipient), None
    except ValidationError as exc:
        messages: list[str] = []
        for error in exc.errors():
            location = ".".join(str(part) for part in error.get("loc", ())) or "recipient"
            messages.append(f"{location}: {error.get('msg', 'invalid value')}")
        return None, f"Recipient #{index}: " + "; ".join(messages)[:460]


def _safe_display_name(raw_recipient: Any, index: int) -> str:
    if isinstance(raw_recipient, dict):
        value = raw_recipient.get("name")
        if isinstance(value, str):
            cleaned = " ".join(value.split())
            if cleaned:
                return cleaned[:200]
    return f"Recipient #{index}"


def _safe_error(exc: Exception) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    return message[:500]
