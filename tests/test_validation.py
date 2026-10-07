from tests.test_create_job import payload


def test_input_validation_rejects_empty_recipients(client):
    data = payload()
    data["recipients"] = []
    response = client.post("/api/v1/generation-jobs", json=data)
    assert response.status_code == 422


def test_partial_validation_keeps_valid_recipients_and_persists_invalid_ones(client):
    data = payload()
    data["recipients"] = [
        {"name": "Valid Person", "email": "valid@example.com"},
        {"name": "Bad Email", "email": "not-an-email"},
        {"email": "another@example.com"},
    ]

    response = client.post("/api/v1/generation-jobs", json=data)
    assert response.status_code == 202
    body = response.json()
    assert body["total"] == 3
    assert body["completed"] == 1
    assert body["failed"] == 2
    assert body["processing"] == 0
    assert body["pending"] == 0
    assert body["progress_percent"] == 100.0
    assert body["status"] == "completed_with_errors"

    results = client.get(f"/api/v1/generation-jobs/{body['job_id']}/certificates")
    assert results.status_code == 200
    items = results.json()["items"]
    assert len(items) == 3
    assert sum(item["status"] == "completed" for item in items) == 1
    assert sum(item["status"] == "failed" for item in items) == 2
    assert all(item["error_message"] for item in items if item["status"] == "failed")


def test_input_validation_rejects_non_object_recipient_without_blocking_valid_ones(client):
    data = payload()
    data["recipients"] = [
        {"name": "Valid Person", "email": "valid@example.com"},
        "not-an-object",
    ]
    response = client.post("/api/v1/generation-jobs", json=data)
    assert response.status_code == 202
    body = response.json()
    assert body["total"] == 2
    assert body["completed"] == 1
    assert body["failed"] == 1
    assert body["status"] == "completed_with_errors"
