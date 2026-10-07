from tests.test_create_job import payload


def test_individual_certificate_failure_does_not_stop_other_recipients(client, monkeypatch):
    from app.services import job_service

    original = job_service.generate_certificate_pdf

    def fail_one(*args, **kwargs):
        if kwargs["recipient_name"] == "Bob Smith":
            raise RuntimeError("simulated renderer failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(job_service, "generate_certificate_pdf", fail_one)
    response = client.post("/api/v1/generation-jobs", json=payload())
    assert response.status_code == 202
    body = response.json()
    assert body["total"] == 2
    assert body["completed"] == 1
    assert body["failed"] == 1
    assert body["progress_percent"] == 100.0
    assert body["status"] == "completed_with_errors"

    results = client.get(f"/api/v1/generation-jobs/{body['job_id']}/certificates")
    assert results.status_code == 200
    items = results.json()["items"]
    assert {item["status"] for item in items} == {"completed", "failed"}
    failed = next(item for item in items if item["status"] == "failed")
    assert "simulated renderer failure" in failed["error_message"]
