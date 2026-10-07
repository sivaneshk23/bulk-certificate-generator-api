from tests.test_create_job import payload


def test_retrieving_generated_certificate(client):
    response = client.post("/api/v1/generation-jobs", json=payload())
    job_id = response.json()["job_id"]
    results = client.get(f"/api/v1/generation-jobs/{job_id}/certificates").json()
    certificate_id = next(x["id"] for x in results["items"] if x["status"] == "completed")

    metadata = client.get(f"/api/v1/certificates/{certificate_id}")
    assert metadata.status_code == 200
    assert metadata.json()["id"] == certificate_id
    assert metadata.json()["download_url"].endswith(f"/certificates/{certificate_id}/download")

    download = client.get(f"/api/v1/certificates/{certificate_id}/download")
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/pdf"
    assert download.content.startswith(b"%PDF")
    assert len(download.content) > 1000


def test_missing_certificate_is_404(client):
    response = client.get("/api/v1/certificates/does-not-exist")
    assert response.status_code == 404
