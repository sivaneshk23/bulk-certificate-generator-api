import pytest

from tests.test_create_job import payload

pytest.importorskip("celery")


def test_celery_task_executes_in_eager_mode(client, db, monkeypatch):
    from app.schemas.job import GenerationJobCreate
    from app.services.job_service import create_job
    from app.workers.tasks import celery_app, process_generation_job

    job = create_job(db, GenerationJobCreate.model_validate(payload()))
    monkeypatch.setitem(celery_app.conf, "task_always_eager", True)
    monkeypatch.setitem(celery_app.conf, "task_eager_propagates", True)

    result = process_generation_job.apply(args=(job.id,), throw=True)
    assert result.get() == job.id
