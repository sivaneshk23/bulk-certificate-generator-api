import threading
import time

from tests.test_create_job import payload


def test_job_progress_is_updated_after_each_certificate(client, db, monkeypatch):
    from app.db.models.generation_job import GenerationJob
    from app.services import job_service

    data = payload()
    data["recipients"] = [
        {"name": f"Person {index}", "email": f"person{index}@example.com"}
        for index in range(1, 4)
    ]

    job = job_service.create_job(db, job_service.GenerationJobCreate.model_validate(data))
    original_generate = job_service.generate_certificate_pdf
    errors: list[BaseException] = []

    def slow_generate(*args, **kwargs):
        time.sleep(0.08)
        return original_generate(*args, **kwargs)

    monkeypatch.setattr(job_service, "generate_certificate_pdf", slow_generate)

    def run_job() -> None:
        try:
            job_service.process_job(job.id)
        except BaseException as exc:  # pragma: no cover - surfaced below
            errors.append(exc)

    worker = threading.Thread(target=run_job, daemon=True)
    worker.start()

    intermediate_seen = False
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and worker.is_alive():
        db.expire_all()
        current = db.get(GenerationJob, job.id)
        if current and 0 < current.completed_count < current.total_count:
            intermediate_seen = True
            break
        time.sleep(0.02)

    worker.join(timeout=10)
    assert not errors
    assert intermediate_seen, "intermediate progress was never persisted"

    db.expire_all()
    refreshed = db.get(GenerationJob, job.id)
    assert refreshed is not None
    assert refreshed.completed_count == 3
    assert refreshed.failed_count == 0
    assert refreshed.processing_count == 0
    assert refreshed.pending_count == 0
    assert refreshed.status.value == "completed"
