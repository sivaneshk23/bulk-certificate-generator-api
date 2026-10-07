from celery import Celery
from sqlalchemy.exc import OperationalError

from app.core.config import settings
from app.services.job_service import process_job

celery_app = Celery(
    "bulk_certificate_generator",
    broker=settings.redis_url,
    backend=settings.redis_url,
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_track_started=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    broker_transport_options={"visibility_timeout": 10800},
    task_soft_time_limit=7200,
    task_time_limit=7500,
    task_ignore_result=False,
)


@celery_app.task(
    bind=True,
    autoretry_for=(ConnectionError, OperationalError),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def process_generation_job(self, job_id: str) -> str:
    del self
    process_job(job_id)
    return job_id
