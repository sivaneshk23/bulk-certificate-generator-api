# Bulk Certificate Generator API

A robust FastAPI backend that accepts one bulk certificate-generation request, validates recipients independently, generates a single predefined PDF certificate design in the background, tracks durable per-recipient progress, isolates individual failures, and exposes generated certificates for retrieval.

This implementation is intentionally focused on the organization’s assignment requirements while using production-minded backend practices where they directly improve correctness, reliability, and explainability.

## Assignment alignment

The project directly implements every required assignment capability:

- Python + FastAPI
- PostgreSQL relational database
- One bulk generation request containing many recipients
- Per-recipient validation without discarding valid recipients
- One predefined certificate design
- Recipient-specific certificate information
- Durable job and certificate status
- Live progress/result tracking
- Generated certificate retrieval/download
- Individual certificate failure isolation
- Background processing with Celery + Redis
- Automated tests for all six mandatory areas
- Complete setup, run, test, request, retrieval, and design documentation

## Architecture

```text
                           +----------------------+
                           |       Client         |
                           +----------+-----------+
                                      |
                                      | REST/JSON
                                      v
                           +----------------------+
                           |       FastAPI        |
                           | Pydantic validation  |
                           +----------+-----------+
                                      |
                     +----------------+----------------+
                     |                                 |
                     v                                 v
             +---------------+                 +---------------+
             |   PostgreSQL  |                 |     Redis     |
             | jobs + certs  |                 | Celery broker |
             +-------+-------+                 +-------+-------+
                     ^                                 |
                     | status/progress                 |
                     |                                 v
                     |                         +---------------+
                     +-------------------------| Celery worker |
                                               +-------+-------+
                                                       |
                                                       v
                                               +---------------+
                                               |    ReportLab  |
                                               |   PDF output  |
                                               +-------+-------+
                                                       |
                                                       v
                                               +---------------+
                                               | Local storage |
                                               +---------------+
```

### Request lifecycle

1. FastAPI validates job-level fields.
2. Each recipient is validated independently.
3. A `generation_jobs` row is created and one `certificates` row is created for every submitted recipient.
4. Invalid recipients are immediately persisted as `failed`; valid recipients remain `pending`.
5. If valid recipients exist, the job is queued to Celery through Redis.
6. The worker processes valid recipients independently.
7. Each certificate is written to a deterministic UUID-based path.
8. Job progress is persisted after every recipient so API polling sees intermediate progress.
9. The completed certificate can be retrieved through the API.
10. A job ends as `completed`, `completed_with_errors`, or `failed` according to the final persisted state.

## Why this design?

The assignment explicitly allows either synchronous or background processing. Background processing is preferable for a bulk workload because PDF generation should not hold an HTTP connection open until every recipient is finished. Celery + Redis also provides a clean path to scale workers horizontally.

The application still supports `PROCESSING_MODE=sync` for deterministic unit tests and simple local debugging.

## Technology stack

- Python 3.12+
- FastAPI
- Pydantic v2
- SQLAlchemy 2.x
- PostgreSQL 16
- Alembic
- Celery 5.x
- Redis 7
- ReportLab
- Pytest
- Ruff
- Docker Compose
- GitHub Actions CI

## Prerequisites

### Docker route

- Docker Engine/Desktop with Compose

### Local route

- Python 3.12+
- PostgreSQL
- Redis
- Optional Noto Sans fonts for Tamil/other non-Latin script rendering
- Optional Noto Sans fonts for best non-Latin rendering. The Docker image installs the required Noto packages automatically; the application falls back gracefully when they are unavailable.

## Configuration

Copy `.env.example` to `.env` for local development.

| Variable | Purpose | Example |
|---|---|---|
| `DATABASE_URL` | SQLAlchemy database URL | `postgresql+psycopg://postgres:postgres@localhost:5432/certificates` |
| `REDIS_URL` | Celery broker/backend | `redis://localhost:6379/0` |
| `PROCESSING_MODE` | `celery` or `sync` | `celery` |
| `STORAGE_DIR` | Certificate output directory | `storage/certificates` |
| `MAX_RECIPIENTS_PER_JOB` | Maximum recipients in one request | `5000` |
| `FONT_REGULAR_PATH` | Optional explicit regular font path | empty for auto-discovery |
| `FONT_BOLD_PATH` | Optional explicit bold font path | empty for auto-discovery |
| `FONT_TAMIL_PATH` | Optional explicit Tamil font path | empty for auto-discovery |

Credentials must never be committed. `.env` is ignored by Git.

## Run with Docker Compose

```bash
docker compose up --build
```

Services:

- API: `http://localhost:8000`
- Swagger/OpenAPI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- Health endpoint: `http://localhost:8000/health`

The `migrate` service applies Alembic migrations exactly once before the API and worker start. PostgreSQL and Redis use health checks.

Stop the stack:

```bash
docker compose down
```

Remove development volumes:

```bash
docker compose down -v
```

## Local development

Create and activate a virtual environment:

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Linux/macOS:

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Configure PostgreSQL and Redis in `.env` and run:

```bash
alembic upgrade head
uvicorn app.main:app --reload
```

In another terminal, start the worker:

```bash
celery -A app.workers.tasks:celery_app worker --loglevel=INFO --concurrency=2
```

For deterministic local testing without infrastructure, use `PROCESSING_MODE=sync`.

## API endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Liveness check |
| POST | `/api/v1/generation-jobs` | Create one bulk generation job |
| GET | `/api/v1/generation-jobs/{job_id}` | Job status and live progress |
| GET | `/api/v1/generation-jobs/{job_id}/certificates` | Paginated certificate results |
| GET | `/api/v1/generation-jobs/{job_id}/download` | Download all completed certificates as ZIP |
| GET | `/api/v1/certificates/{certificate_id}` | Certificate metadata/status |
| GET | `/api/v1/certificates/{certificate_id}/download` | Download the generated PDF |

## Submit a bulk generation request

```bash
curl -X POST http://localhost:8000/api/v1/generation-jobs \
  -H "Content-Type: application/json" \
  -d '{
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
  }'
```

The API returns `202 Accepted` and a `job_id`.

## Job status and live progress

```bash
curl http://localhost:8000/api/v1/generation-jobs/<JOB_ID>
```

A response contains:

```json
{
  "job_id": "...",
  "status": "processing",
  "total": 3,
  "completed": 1,
  "failed": 0,
  "processing": 1,
  "pending": 1,
  "progress_percent": 33.33
}
```

`progress_percent` is:

```text
(completed + failed) / total * 100
```

A failure counts as processed because the worker has finished deciding the recipient's outcome.

## Per-recipient validation and partial validity

Recipient validation is intentionally item-level.

A request such as:

```text
Recipient 1 -> valid
Recipient 2 -> invalid email
Recipient 3 -> valid
```

creates all three certificate records. Recipient 2 is immediately recorded as `failed` with a validation message, while recipients 1 and 3 continue through normal generation.

This prevents one malformed recipient from unnecessarily discarding otherwise valid recipients in the same bulk request.

Request-level structural errors such as an empty `recipients` array still return HTTP 422.

## Retrieve generated certificates

List results with pagination:

```bash
curl "http://localhost:8000/api/v1/generation-jobs/<JOB_ID>/certificates?page=1&page_size=50"
```

Get certificate metadata:

```bash
curl http://localhost:8000/api/v1/certificates/<CERTIFICATE_ID>
```

Download the PDF:

```bash
curl -L \
  http://localhost:8000/api/v1/certificates/<CERTIFICATE_ID>/download \
  --output certificate.pdf
```

Successful retrieval uses `application/pdf`.

## Certificate generation

The assignment requires a single predefined template. This project uses one ReportLab design containing:

- certificate title
- recipient name
- course/event name
- completion date
- issuer name
- issuer designation when supplied
- unique certificate ID

The renderer is Unicode-aware. It auto-detects common Noto fonts for Latin/Tamil text and uses a built-in PDF CJK font for Chinese/Japanese/Korean glyphs. Docker installs the required Noto font packages. If a host does not have a Tamil font, generation remains operational and falls back to the configured regular font with a warning; Docker provides the full Tamil font support.

Recipient and course text are rendered as plain canvas text rather than user-controlled HTML/XML, so inputs such as `Maths <b>Advanced & Safe` are displayed literally instead of becoming ReportLab markup.

## Validation and failure handling

There are two distinct failure levels:

### Request-level failure

Examples:

- empty recipient list
- malformed JSON
- invalid certificate-level fields
- more than `MAX_RECIPIENTS_PER_JOB` recipients

These return a client error such as HTTP 422.

### Individual-recipient failure

Examples:

- invalid email
- missing name
- rendering failure
- unexpected per-recipient generation error

These are persisted on the affected certificate record and do not stop other valid recipients.

Example final job:

```text
10 submitted
8 completed
2 failed
0 pending
0 processing
progress = 100%
status = completed_with_errors
```

## Worker resilience

Certificate state is persisted in PostgreSQL. Celery uses late acknowledgements and rejects a task when a worker process is lost so the message can be re-delivered. A PostgreSQL advisory lock serializes processing for a given job, preventing duplicate workers from processing the same job concurrently. When a job is resumed, any certificates left in `processing` are reset to `pending` and can be safely attempted again using the same deterministic certificate ID/path. The broker visibility timeout is longer than the hard task limit to reduce premature redelivery.

## Storage and security

Files are stored beneath:

```text
storage/certificates/<job_id>/<certificate_id>.pdf
```

User-controlled recipient names never become filesystem paths.

The download route resolves and verifies the requested path remains beneath the configured storage root before serving the file.

Other practical safeguards include:

- environment-based configuration
- UUID identifiers
- recipient count limit
- safe client-facing errors
- no source-controlled secrets
- database-backed job state
- paginated certificate results
- idempotency keys for safe client retries
- optional duplicate-recipient rejection within a single request
- ZIP download for all completed certificates in a finished job

## Database and migrations

Apply migrations:

```bash
alembic upgrade head
```

The migrations create:

- `generation_jobs`
- `certificates`
- PostgreSQL enum types
- certificate/job indexes
- a request fingerprint used to detect idempotency-key reuse with different payloads

The migration explicitly creates PostgreSQL enum types once and reuses them when creating the table columns, avoiding duplicate-type errors on PostgreSQL.

## Testing

The test suite covers more than the six mandatory assignment areas:

1. creating a generation job
2. input validation
3. certificate generation
4. job status/progress
5. individual failure isolation
6. certificate retrieval/download
7. partial-validity bulk input
8. pagination
9. Unicode/Tamil/Chinese generation
10. markup-safe certificate data
11. live progress persistence
12. Alembic migration smoke test
13. maximum-recipient protection
14. download-before-ready conflict handling
15. idempotent job creation
16. duplicate-recipient isolation
17. bulk ZIP download
18. concurrent same-job processing protection
19. Celery eager task execution (when Celery is installed)
20. Strict idempotency-key payload matching
21. Queue failure state consistency
22. Celery dispatch routing

Run:

```bash
pytest -q
```

Lint:

```bash
ruff check .
```

Compile check:

```bash
python -m compileall -q app tests alembic
```

The GitHub Actions pipeline additionally performs a real PostgreSQL migration check and a Docker/Redis/Celery integration verification. The local sandbox used to prepare this ZIP may not have Docker, PostgreSQL, Redis, or Celery installed; those infrastructure checks are intentionally executed in CI when the repository is run by GitHub Actions.

## Design decisions

### FastAPI

Strong type-driven validation, automatic OpenAPI documentation, dependency injection, and low framework overhead make it a good fit for this focused API assignment.

### PostgreSQL

Provides durable relational storage for jobs, recipient records, state transitions, and progress counters.

### SQLAlchemy + Alembic

SQLAlchemy provides database abstraction and typed models. Alembic provides reproducible schema migrations.

### Celery + Redis

Background PDF generation avoids holding an HTTP request open for a large bulk job and provides a straightforward worker scaling path.

### Per-recipient rows

A single bulk job can contain mixed outcomes. One row per recipient makes each outcome independently observable and lets the worker isolate failures.

### ReportLab

Direct Python PDF generation keeps the implementation self-contained and avoids needing a browser renderer.

### Local file storage

Local filesystem storage is sufficient for the assignment and easy to inspect. A production deployment can replace it with durable object storage while keeping the database as metadata source of truth.

## Production considerations

A production system could add authentication/authorization, object storage, metrics, tracing, rate limiting, stronger dead-letter/retry policies, multi-tenant isolation, horizontal worker scaling, and operational alerting. These are deliberately not required for this assignment and are documented as evolution paths rather than unnecessary scope.

## Troubleshooting

If jobs stay queued:

```bash
docker compose logs redis
docker compose logs worker
```

Check migration state:

```bash
docker compose run --rm api alembic current
```

Check API logs:

```bash
docker compose logs api
```

A missing generated file returns a clean HTTP 404 rather than exposing a filesystem exception.

## Documentation

- [`docs/architecture.md`](docs/architecture.md)
- [`docs/api-examples.md`](docs/api-examples.md)
- [`docs/assignment-compliance.md`](docs/assignment-compliance.md)
- [`docs/interview-notes.md`](docs/interview-notes.md)
