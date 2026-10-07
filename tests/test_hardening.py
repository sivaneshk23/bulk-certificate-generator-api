from sqlalchemy import select

from app.db.models.certificate import Certificate
from tests.test_create_job import payload


def test_max_recipient_limit_is_enforced(client):
    data = payload()
    data["recipients"] = [
        {"name": f"Person {index}", "email": f"person{index}@example.com"}
        for index in range(101)
    ]
    response = client.post("/api/v1/generation-jobs", json=data)
    assert response.status_code == 422
    assert "at most 100 recipients" in response.json()["detail"]


def test_download_before_processing_returns_conflict(client, db):
    from app.schemas.job import GenerationJobCreate
    from app.services.job_service import create_job

    job = create_job(db, GenerationJobCreate.model_validate(payload()))
    certificate_id = db.scalar(
        select(Certificate.id).where(Certificate.job_id == job.id).limit(1)
    )
    assert certificate_id

    response = client.get(f"/api/v1/certificates/{certificate_id}/download")
    assert response.status_code == 409


def test_idempotency_key_returns_the_original_job(client):
    data = payload()
    data["idempotency_key"] = "request-key-001"
    first = client.post("/api/v1/generation-jobs", json=data)
    second = client.post("/api/v1/generation-jobs", json=data)

    assert first.status_code == 202
    assert second.status_code == 202
    assert second.json()["job_id"] == first.json()["job_id"]


def test_duplicate_recipients_are_isolated_as_validation_failures(client):
    data = payload()
    data["recipients"] = [
        {"name": "Alice Johnson", "email": "alice@example.com"},
        {"name": "Alice Johnson", "email": "alice@example.com"},
        {"name": "Bob Smith", "email": "bob@example.com"},
    ]
    response = client.post("/api/v1/generation-jobs", json=data)
    assert response.status_code == 202
    body = response.json()
    assert body["total"] == 3
    assert body["completed"] == 2
    assert body["failed"] == 1
    assert body["status"] == "completed_with_errors"


def test_completed_job_can_download_all_certificates_as_zip(client):
    response = client.post("/api/v1/generation-jobs", json=payload())
    job_id = response.json()["job_id"]

    archive = client.get(f"/api/v1/generation-jobs/{job_id}/download")
    assert archive.status_code == 200
    assert archive.headers["content-type"] == "application/zip"
    assert archive.content[:2] == b"PK"


def test_idempotency_header_returns_the_original_job(client):
    data = payload()
    first = client.post(
        "/api/v1/generation-jobs",
        json=data,
        headers={"Idempotency-Key": "header-key-001"},
    )
    second = client.post(
        "/api/v1/generation-jobs",
        json=data,
        headers={"Idempotency-Key": "header-key-001"},
    )

    assert first.status_code == 202
    assert second.status_code == 202
    assert second.json()["job_id"] == first.json()["job_id"]


def test_mismatched_idempotency_sources_are_rejected(client):
    data = payload()
    data["idempotency_key"] = "body-key-001"
    response = client.post(
        "/api/v1/generation-jobs",
        json=data,
        headers={"Idempotency-Key": "header-key-001"},
    )

    assert response.status_code == 422
    assert "does not match" in response.json()["detail"]


def test_invalid_idempotency_header_is_rejected(client):
    response = client.post(
        "/api/v1/generation-jobs",
        json=payload(),
        headers={"Idempotency-Key": "       "},
    )

    assert response.status_code == 422
    assert "Idempotency-Key" in response.json()["detail"]
