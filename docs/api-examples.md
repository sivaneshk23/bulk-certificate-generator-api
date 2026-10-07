# API Examples

## 1. Create a bulk generation job

```http
POST /api/v1/generation-jobs
Content-Type: application/json

{
  "certificate": {
    "title": "Certificate of Completion",
    "course_name": "Backend Engineering",
    "completion_date": "2026-10-07",
    "issuer_name": "Example Institute",
    "issuer_designation": "Program Director"
  },
  "recipients": [
    {"name": "Alice Johnson", "email": "alice@example.com"},
    {"name": "Bob Smith", "email": "bob@example.com"},
    {"name": "சிவனேஷ் குமார்", "email": "sivanesh@example.com"}
  ]
}
```

Example response:

```json
{
  "job_id": "9b3b9a0d-...",
  "status": "queued",
  "total": 3,
  "completed": 0,
  "failed": 0,
  "processing": 0,
  "pending": 3,
  "progress_percent": 0.0,
  "created_at": "2026-10-07T15:00:00Z",
  "started_at": null,
  "completed_at": null,
  "error_summary": null
}
```

## 2. Check job status

```http
GET /api/v1/generation-jobs/<JOB_ID>
```

Example in-progress response:

```json
{
  "job_id": "9b3b9a0d-...",
  "status": "processing",
  "total": 3,
  "completed": 1,
  "failed": 0,
  "processing": 1,
  "pending": 1,
  "progress_percent": 33.33
}
```

## 3. List job certificates

```http
GET /api/v1/generation-jobs/<JOB_ID>/certificates?page=1&page_size=50
```

The response is paginated and includes each recipient's status, validation/generation error message, and download URL when available.

## 4. Get certificate metadata

```http
GET /api/v1/certificates/<CERTIFICATE_ID>
```

## 5. Download certificate PDF

```http
GET /api/v1/certificates/<CERTIFICATE_ID>/download
```

Successful retrieval:

```text
Content-Type: application/pdf
```

## 6. Request-level validation error

An empty recipient array is a request-level structural error:

```json
{
  "certificate": {"...": "..."},
  "recipients": []
}
```

The API returns HTTP 422.

## 7. Partial recipient validation

A single bad recipient does not reject the complete job.

```json
{
  "certificate": {"...": "..."},
  "recipients": [
    {"name": "Valid One", "email": "valid@example.com"},
    {"name": "Invalid Email", "email": "not-an-email"},
    {"name": "Valid Two", "email": "valid2@example.com"}
  ]
}
```

Expected final outcome:

```text
Valid One      -> completed
Invalid Email  -> failed (validation error)
Valid Two      -> completed
job status     -> completed_with_errors
progress       -> 100%
```

## 8. Rendering failure isolation

If one PDF generation throws an exception, the worker records the failed certificate and continues processing other recipients.

## 9. Idempotent job creation

Clients that may retry the same request can send an idempotency key:

```http
POST /api/v1/generation-jobs
Idempotency-Key: request-key-001
Content-Type: application/json
```

The same key can instead be supplied as `idempotency_key` in the JSON body. Repeating the same payload returns the existing job; reusing that key with different payload content returns HTTP 409.

## 10. Download all completed certificates

For a finished job:

```http
GET /api/v1/generation-jobs/<JOB_ID>/download
```

The response is a ZIP archive containing every completed PDF for the job. Failed certificates are not included.
