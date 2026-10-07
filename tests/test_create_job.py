from datetime import date


def payload():
    return {
        "certificate": {
            "title": "Certificate of Completion",
            "course_name": "Backend Engineering",
            "completion_date": str(date(2026, 10, 7)),
            "issuer_name": "Example Institute",
            "issuer_designation": "Program Director",
        },
        "recipients": [
            {"name": "Alice Johnson", "email": "alice@example.com"},
            {"name": "Bob Smith", "email": "bob@example.com"},
        ],
    }


def test_creating_generation_job(client):
    response = client.post("/api/v1/generation-jobs", json=payload())
    assert response.status_code == 202
    body = response.json()
    assert body["job_id"]
    assert body["total"] == 2
    assert body["completed"] == 2
    assert body["failed"] == 0
    assert body["progress_percent"] == 100.0
    assert body["status"] == "completed"
