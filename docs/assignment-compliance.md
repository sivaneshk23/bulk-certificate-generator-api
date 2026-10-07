# Assignment Compliance Matrix

This matrix maps every requirement stated in the supplied assignment PDF to the implementation.

| Assignment requirement | Implementation | Evidence |
|---|---|---|
| Build a backend API for certificate generation | FastAPI REST API | `app/main.py`, `app/api/routes/` |
| Accept a request containing a list of recipients | Single bulk `POST /api/v1/generation-jobs` | `app/api/routes/jobs.py` |
| Python | Python 3.12+ | `pyproject.toml` |
| Supported web framework | FastAPI | `app/main.py` |
| Relational database | PostgreSQL + SQLAlchemy | `app/db/`, `docker-compose.yml` |
| Accept certificate generation request | Job-creation endpoint | `app/api/routes/jobs.py` |
| Validate provided recipient data | Per-recipient Pydantic validation | `app/schemas/job.py`, `app/services/job_service.py` |
| Generate one certificate per valid recipient | ReportLab worker generation | `app/certificates/generator.py`, `app/services/job_service.py` |
| Use one predefined template | Exactly one ReportLab certificate layout | `app/certificates/generator.py` |
| Recipient-specific information | Name, course, date, issuer and ID rendered | `app/certificates/generator.py` |
| Track generation status | Job/certificate status enums in PostgreSQL | `app/db/models/` |
| Check progress/result | Job status endpoint + certificate results endpoint | `app/api/routes/jobs.py` |
| Retrieve generated certificates | Metadata + PDF download endpoints | `app/api/routes/certificates.py` |
| Support bulk generation | One request contains many recipients | `app/schemas/job.py` |
| Handle invalid recipient data appropriately | Invalid recipients become failed records while valid ones continue | `app/services/job_service.py`, `tests/test_validation.py` |
| One generation failure should not stop other valid recipients | Independent exception boundary per certificate | `app/services/job_service.py`, `tests/test_failure_isolation.py` |
| Job identifies successful/failed generations | Persistent counts + per-certificate status/error fields | `app/services/job_service.py`, `app/schemas/job.py` |
| Choose and document sync/background approach | Background Celery + Redis, sync test mode | `docs/architecture.md`, `README.md` |
| Test creating a generation job | Implemented | `tests/test_create_job.py` |
| Test input validation | Implemented, including partial-validity cases | `tests/test_validation.py` |
| Test certificate generation | Implemented | `tests/test_certificate_generation.py`, `tests/test_unicode_and_safety.py` |
| Test job status/progress | Implemented, including intermediate progress | `tests/test_job_status.py`, `tests/test_live_progress.py` |
| Test individual certificate failure | Implemented | `tests/test_failure_isolation.py` |
| Test certificate retrieval | Implemented | `tests/test_certificate_retrieval.py` |
| README setup | Included | `README.md` |
| README application run | Included | `README.md` |
| README test run | Included | `README.md` |
| README submit request | Included | `README.md`, `docs/api-examples.md` |
| README retrieve certificates | Included | `README.md`, `docs/api-examples.md` |
| README important design decisions | Included | `README.md`, `docs/architecture.md` |
| Interview readiness | Dedicated explanation notes | `docs/interview-notes.md` |

## Explicit scope decisions

The assignment allows additional libraries/tools but does not require authentication, frontend work, multiple templates, or cloud deployment. Those are not necessary to satisfy the stated requirements and are intentionally excluded from the submission scope.

## Reliability and optional improvements

The following are not required by the assignment but strengthen the implementation without changing its required behavior:

| Improvement | Implementation |
|---|---|
| Safe retry of job creation | Optional `idempotency_key` plus SHA-256 request fingerprint |
| Duplicate same-job recipients | Later exact duplicates are persisted as individual failed certificate records |
| Concurrent worker protection | PostgreSQL advisory lock per job; process-local lock for SQLite tests |
| Worker recovery | `processing` certificates are reconciled to `pending` when a job is resumed |
| Efficient progress | Persisted pending/processing/completed/failed counters avoid a `GROUP BY` query after every certificate |
| Pagination | Certificate list endpoint supports bounded page sizes |
| Bulk retrieval | Finished jobs can return all completed PDFs as a ZIP archive |
| Deployment verification | CI checks PostgreSQL migrations and runs a real Docker/Redis/Celery smoke test when repository infrastructure is available |
