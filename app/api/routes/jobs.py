import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models.certificate import Certificate, CertificateStatus
from app.db.models.generation_job import GenerationJob, JobStatus
from app.db.session import get_db
from app.schemas.job import (
    CertificateListResponse,
    CertificateResult,
    GenerationJobCreate,
    GenerationJobResponse,
)
from app.services.job_service import create_job, get_idempotent_job_or_raise, get_job
from app.workers.dispatcher import enqueue_job

router = APIRouter(prefix="/generation-jobs", tags=["Generation Jobs"])


def to_job_response(db: Session, job: GenerationJob) -> GenerationJobResponse:
    # Stored counters are updated transactionally by the worker. The status endpoint
    # therefore stays O(1) with respect to the number of recipients.
    processed = job.completed_count + job.failed_count
    progress = round((processed / job.total_count) * 100, 2) if job.total_count else 100.0
    return GenerationJobResponse(
        job_id=job.id,
        status=job.status,
        total=job.total_count,
        completed=job.completed_count,
        failed=job.failed_count,
        processing=job.processing_count,
        pending=job.pending_count,
        progress_percent=progress,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        error_summary=job.error_summary,
    )


@router.post("", response_model=GenerationJobResponse, status_code=status.HTTP_202_ACCEPTED)
def create_generation_job(
    payload: GenerationJobCreate,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
):
    if idempotency_key is not None:
        normalized_key = idempotency_key.strip()
        if not 8 <= len(normalized_key) <= 128:
            raise HTTPException(
                status_code=422,
                detail="Idempotency-Key must contain between 8 and 128 non-whitespace characters.",
            )
        if payload.idempotency_key and payload.idempotency_key != normalized_key:
            raise HTTPException(
                status_code=422,
                detail="The Idempotency-Key header does not match the JSON idempotency_key.",
            )
        payload = payload.model_copy(update={"idempotency_key": normalized_key})
    if len(payload.recipients) > settings.max_recipients_per_job:
        raise HTTPException(
            status_code=422,
            detail=f"A job may contain at most {settings.max_recipients_per_job} recipients.",
        )

    try:
        existing = get_idempotent_job_or_raise(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    job = existing or create_job(db, payload)
    if job.status in {JobStatus.COMPLETED, JobStatus.COMPLETED_WITH_ERRORS}:
        return to_job_response(db, job)

    if job.pending_count > 0:
        try:
            enqueue_job(job.id)
        except Exception as exc:
            job = get_job(db, job.id)
            if job:
                failed_now = job.pending_count + job.processing_count
                db.execute(
                    update(Certificate)
                    .where(
                        Certificate.job_id == job.id,
                        Certificate.status.in_(
                            [CertificateStatus.PENDING, CertificateStatus.PROCESSING]
                        ),
                    )
                    .values(
                        status=CertificateStatus.FAILED,
                        error_message="Generation worker could not be queued.",
                        completed_at=datetime.now(UTC),
                    )
                )
                job.failed_count += failed_now
                job.pending_count = 0
                job.processing_count = 0
                job.status = JobStatus.FAILED
                job.error_summary = "Generation worker could not be queued."
                job.completed_at = datetime.now(UTC)
                db.commit()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Generation service is temporarily unavailable.",
            ) from exc

    db.refresh(job)
    return to_job_response(db, job)


@router.get("/{job_id}", response_model=GenerationJobResponse)
def get_generation_job(job_id: str, db: Session = Depends(get_db)):
    job = get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Generation job not found.")
    return to_job_response(db, job)


@router.get("/{job_id}/certificates", response_model=CertificateListResponse)
def list_job_certificates(
    job_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    job = get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Generation job not found.")

    total = db.scalar(select(func.count(Certificate.id)).where(Certificate.job_id == job_id)) or 0
    rows = db.scalars(
        select(Certificate)
        .where(Certificate.job_id == job_id)
        .order_by(Certificate.created_at, Certificate.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    items = [
        CertificateResult(
            id=row.id,
            recipient_name=row.recipient_name,
            recipient_email=row.recipient_email,
            status=row.status,
            error_message=row.error_message,
            download_url=(
                f"/api/v1/certificates/{row.id}/download"
                if row.status == CertificateStatus.COMPLETED
                else None
            ),
            created_at=row.created_at,
            completed_at=row.completed_at,
        )
        for row in rows
    ]
    return CertificateListResponse(
        job_id=job_id,
        items=items,
        total=int(total),
        page=page,
        page_size=page_size,
    )


def _remove_file(path: str) -> None:
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass


@router.get("/{job_id}/download", response_class=FileResponse, response_model=None)
def download_job_archive(
    job_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    job = get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Generation job not found.")
    if job.status not in {JobStatus.COMPLETED, JobStatus.COMPLETED_WITH_ERRORS}:
        raise HTTPException(status_code=409, detail="The generation job is not finished yet.")

    storage_root = Path(settings.storage_dir).resolve()
    storage_root.mkdir(parents=True, exist_ok=True)
    completed_stmt = (
        select(Certificate)
        .where(
            Certificate.job_id == job_id,
            Certificate.status == CertificateStatus.COMPLETED,
        )
        .order_by(Certificate.created_at, Certificate.id)
    )
    completed_count = db.scalar(select(func.count(Certificate.id)).where(
        Certificate.job_id == job_id,
        Certificate.status == CertificateStatus.COMPLETED,
    )) or 0
    if completed_count == 0:
        raise HTTPException(status_code=404, detail="No completed certificates are available.")

    archive_file = tempfile.NamedTemporaryFile(
        prefix=f"certificates-{job_id}-",
        suffix=".zip",
        dir=storage_root,
        delete=False,
    )
    archive_path = Path(archive_file.name)
    archive_file.close()

    try:
        with zipfile.ZipFile(archive_path, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            added = 0
            for certificate in db.scalars(completed_stmt).yield_per(100):
                if not certificate.file_path:
                    continue
                file_path = Path(certificate.file_path).resolve()
                try:
                    relative = file_path.relative_to(storage_root)
                except ValueError as exc:
                    raise HTTPException(
                        status_code=500, detail="Certificate storage path is invalid."
                    ) from exc
                if not file_path.is_file():
                    raise HTTPException(
                        status_code=500,
                        detail=f"Generated certificate file is missing: {certificate.id}.",
                    )
                archive.write(file_path, arcname=str(relative))
                added += 1
            if added == 0:
                raise HTTPException(status_code=404, detail="No completed certificate files exist.")
    except Exception:
        archive_path.unlink(missing_ok=True)
        raise

    background_tasks.add_task(_remove_file, str(archive_path))
    return FileResponse(
        path=archive_path,
        media_type="application/zip",
        filename=f"certificates-{job_id}.zip",
    )
