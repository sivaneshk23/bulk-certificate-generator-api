from app.core.config import settings
from app.services.job_service import process_job


def enqueue_job(job_id: str) -> None:
    if settings.processing_mode.lower() == "sync":
        process_job(job_id)
        return

    from app.workers.tasks import process_generation_job
    process_generation_job.delay(job_id)
