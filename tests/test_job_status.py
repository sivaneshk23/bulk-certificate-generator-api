from tests.test_create_job import payload


def test_job_status_and_progress(client):
    response = client.post("/api/v1/generation-jobs", json=payload())
    job_id = response.json()["job_id"]
    status_response = client.get(f"/api/v1/generation-jobs/{job_id}")
    assert status_response.status_code == 200
    body = status_response.json()
    assert body["total"] == 2
    assert body["completed"] == 2
    assert body["failed"] == 0
    assert body["processing"] == 0
    assert body["pending"] == 0
    assert body["progress_percent"] == 100.0


def test_certificate_list_supports_pagination(client):
    data = payload()
    data["recipients"] = [
        {"name": f"Person {index}", "email": f"person{index}@example.com"}
        for index in range(1, 6)
    ]
    response = client.post("/api/v1/generation-jobs", json=data)
    job_id = response.json()["job_id"]

    page = client.get(f"/api/v1/generation-jobs/{job_id}/certificates?page=2&page_size=2")
    assert page.status_code == 200
    body = page.json()
    assert body["total"] == 5
    assert body["page"] == 2
    assert body["page_size"] == 2
    assert len(body["items"]) == 2
