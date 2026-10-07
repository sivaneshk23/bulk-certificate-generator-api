# Final Verification

This document records the verification performed while preparing the submission ZIP.

## Local verification

The following checks passed in the preparation environment:

- Python compilation: `python -m compileall -q app tests alembic`
- Automated tests: **27 passed**
- Python source line-length check: **pass** for the configured 100-character limit
- Unicode PDF generation tests: pass, including Tamil/Chinese inputs and literal markup text
- Per-recipient failure isolation: pass
- Live/intermediate progress persistence: pass
- Same-job concurrency protection: pass in the local test environment
- Idempotency with identical payload: pass
- Idempotency-key reuse with different payload: returns HTTP 409
- Maximum-recipient validation: pass
- Download-before-ready conflict: pass
- Individual PDF download: pass
- Completed-job ZIP download: pass
- Worker-loss recovery logic: pass
- SQLite/Alembic migration smoke test: pass

## Environment-dependent checks

Two tests are intentionally marked as integration/environment-dependent:

1. `tests/test_celery_eager.py` requires the Celery package to be installed.
2. `tests/test_postgres_migration.py` requires `TEST_POSTGRES_URL` pointing to a live PostgreSQL instance.

The project declares Celery and PostgreSQL dependencies in `requirements.txt`, and `.github/workflows/ci.yml` provisions PostgreSQL, Redis, system fonts, and a Docker Compose stack for the corresponding CI checks.

## Assignment coverage

The implementation includes every mandatory item in the supplied assignment PDF:

- Python backend API
- FastAPI
- relational database
- bulk generation request
- recipient validation
- one predefined certificate template
- recipient-specific certificate output
- job status tracking
- progress/result retrieval
- generated certificate retrieval
- individual certificate failure isolation
- bulk-processing design and documented rationale
- all six mandatory test categories
- complete README setup/run/test/request/retrieval/design documentation
- interview-readiness documentation

Optional improvements were kept focused on reliability and usability: pagination, idempotency, duplicate-recipient handling, path-safety, worker recovery, and bulk ZIP retrieval.
