import threading
import time

from tests.test_create_job import payload


def test_same_job_cannot_be_processed_twice_concurrently(client, db, monkeypatch):
    from app.db.models.certificate import Certificate, CertificateStatus
    from app.db.models.generation_job import GenerationJob
    from app.services import job_service

    data = payload()
    data["recipients"] = [
        {"name": f"Person {index}", "email": f"person{index}@example.com"}
        for index in range(1, 5)
    ]
    job = job_service.create_job(db, job_service.GenerationJobCreate.model_validate(data))

    original_generate = job_service.generate_certificate_pdf

    def slow_generate(*args, **kwargs):
        time.sleep(0.04)
        return original_generate(*args, **kwargs)

    monkeypatch.setattr(job_service, "generate_certificate_pdf", slow_generate)

    errors: list[BaseException] = []

    def run_worker() -> None:
        try:
            job_service.process_job(job.id)
        except BaseException as exc:  # pragma: no cover - surfaced below
            errors.append(exc)

    first = threading.Thread(target=run_worker, daemon=True)
    second = threading.Thread(target=run_worker, daemon=True)
    first.start()
    second.start()
    first.join(timeout=10)
    second.join(timeout=10)

    assert not first.is_alive()
    assert not second.is_alive()
    assert not errors

    db.expire_all()
    refreshed = db.get(GenerationJob, job.id)
    rows = db.query(Certificate).filter(Certificate.job_id == job.id).all()
    assert refreshed is not None
    assert refreshed.completed_count == 4
    assert refreshed.failed_count == 0
    assert refreshed.processing_count == 0
    assert refreshed.pending_count == 0
    assert refreshed.status.value == "completed"
    assert all(row.status == CertificateStatus.COMPLETED for row in rows)
