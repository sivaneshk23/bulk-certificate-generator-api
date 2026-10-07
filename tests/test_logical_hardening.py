import sys
import types

from tests.test_create_job import payload


def test_same_idempotency_key_with_different_payload_is_rejected(client):
    data = payload()
    data["idempotency_key"] = "same-key-001"
    first = client.post("/api/v1/generation-jobs", json=data)
    assert first.status_code == 202

    changed = payload()
    changed["idempotency_key"] = "same-key-001"
    changed["certificate"]["course_name"] = "Different Course"
    response = client.post("/api/v1/generation-jobs", json=changed)
    assert response.status_code == 409
    assert "different generation request" in response.json()["detail"]


def test_enqueue_failure_marks_pending_recipients_failed(client, monkeypatch):

    def fail_enqueue(job_id: str) -> None:
        raise RuntimeError("broker unavailable")

    monkeypatch.setattr("app.api.routes.jobs.enqueue_job", fail_enqueue)
    response = client.post("/api/v1/generation-jobs", json=payload())
    assert response.status_code == 503


def test_celery_processing_mode_dispatches_to_task(monkeypatch):
    from app.core.config import settings
    from app.workers import dispatcher

    called: list[str] = []

    class FakeTask:
        def delay(self, job_id: str) -> None:
            called.append(job_id)

    monkeypatch.setattr(settings, "processing_mode", "celery")
    fake_tasks = types.SimpleNamespace(process_generation_job=FakeTask())
    monkeypatch.setitem(sys.modules, "app.workers.tasks", fake_tasks)
    dispatcher.enqueue_job("job-123")
    assert called == ["job-123"]
