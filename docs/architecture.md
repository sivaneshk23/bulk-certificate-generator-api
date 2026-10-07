# Architecture

## Overview

The service is a job-oriented REST API. One client request creates one durable generation job containing one certificate record per submitted recipient.

```text
Client
  |
  v
FastAPI / Pydantic
  |
  +------> PostgreSQL <------+
  |                           |
  +------> Redis -> Celery worker
                              |
                              v
                           ReportLab
                              |
                              v
                         Certificate PDF
                              |
                              v
                         Local storage
```

## Request lifecycle

1. FastAPI validates certificate-level fields.
2. The API accepts a list of recipient payloads as raw items so validation can happen independently per recipient.
3. The application validates each recipient with `RecipientInput`.
4. One `generation_jobs` row is created and one `certificates` row is created for every submitted recipient.
5. Invalid recipients are persisted immediately as `failed` with a useful validation message.
6. Valid recipients remain `pending` and are processed asynchronously in normal operation.
7. Each recipient enters `processing`, gets a deterministic output path, and is rendered by ReportLab.
8. Persistent counters are updated transactionally after each recipient, so polling clients see intermediate progress without a full-table aggregate query on every item.
9. The job is finalized as `completed`, `completed_with_errors`, or `failed`.
10. Completed certificates are retrievable through metadata, individual PDF download, or the optional job ZIP download.

## Why background processing?

The assignment explicitly permits synchronous or background processing. Background processing is the stronger fit for bulk work because PDF generation should not block an HTTP request for the duration of the complete job.

Tests use `PROCESSING_MODE=sync` for deterministic isolation. Production/Compose uses Celery + Redis.

## Concurrency and duplicate-worker protection

Celery may redeliver a task after retries or a worker loss. To prevent two workers from processing the same job at the same time, `process_job` acquires a PostgreSQL advisory lock derived from the job ID. SQLite tests use a process-local re-entrant lock.

This means a duplicate delivery waits for the first worker instead of resetting or overwriting another worker's in-flight state. A worker crash releases the PostgreSQL advisory lock automatically, allowing the redelivered task to recover the job.

## Failure isolation

Each recipient has its own database record and its own exception boundary inside the worker.

A renderer failure for recipient A updates only A:

```text
A -> failed
B -> completed
C -> completed
```

The worker continues to the next pending recipient. Final job status becomes `completed_with_errors` when at least one recipient failed but all submitted recipients have reached a terminal result.

## Partial validation

The request itself is structurally validated at the API boundary, while recipients are validated one-by-one.

This avoids the undesirable behavior where a single invalid recipient forces a complete 422 rejection and causes all otherwise valid recipients to be discarded.

Exact duplicate recipient pairs are treated as an individual validation failure rather than silently producing duplicate certificates.

## Progress model

Persistent state is authoritative.

```text
completed  = number of certificates with status=completed
failed     = number of certificates with status=failed
processing = number of certificates with status=processing
pending    = number of certificates with status=pending

progress = (completed + failed) / total * 100
```

The aggregate counters live on the parent job and are updated in the same database transaction that changes the individual certificate state. The worker performs one reconciliation pass when a job starts/resumes and then relies on transactional counter updates, avoiding a `GROUP BY` recount after every generated certificate.

## Worker recovery

The Celery task uses late acknowledgements and rejects a task if the worker process is lost. The broker visibility timeout is longer than the task hard limit.

When `process_job` starts again, certificates left in `processing` are reconciled back to `pending` before new work is claimed. A deterministic certificate UUID/path means a retry does not create a second random output file.

## Database

### `generation_jobs`

Stores:

- job ID
- overall status
- total recipient count
- pending count
- processing count
- completed count
- failed count
- optional idempotency key
- certificate metadata shared by the job
- timestamps
- error summary

### `certificates`

Stores:

- certificate ID
- job foreign key
- recipient name/email
- per-certificate status
- output path
- error message
- timestamps

Indexes support job/result retrieval and job/status filtering.

## Certificate rendering

There is exactly one predefined design as required by the assignment.

The renderer uses ReportLab and treats user-controlled strings as plain text, not HTML/XML. Common Noto fonts are detected automatically, with a built-in CJK PDF font for Chinese/Japanese/Korean characters. The Docker image supplies the Noto packages needed for multilingual rendering.

If a local machine lacks a Tamil font, the generator does not crash at module initialization; it logs a warning and falls back to the configured regular font. Production/Compose uses the Docker-provided Noto Tamil font for proper Tamil rendering.

## Storage

Development/assignment storage:

```text
storage/certificates/<job_id>/<certificate_id>.pdf
```

Recipient names are never inserted into filenames. Download requests are canonicalized and checked to remain inside the configured storage root.

## Pagination and bulk retrieval

The certificate-results endpoint uses bounded page-size parameters to avoid returning an arbitrarily large result set for a large job.

Finished jobs can also return all completed certificate files as a ZIP archive. ZIP creation still validates each file path against the storage root.

## Idempotency

Clients may supply an `idempotency_key` when creating a job. The key is stored together with a request fingerprint. A repeat of the same request returns the original job; reuse of the key with different payload content is rejected with HTTP 409. This is useful when a client retries after a network timeout without allowing accidental payload substitution.

## Scaling path

For larger production deployments:

1. Scale Celery workers horizontally.
2. Replace local storage with object storage.
3. Add metrics/tracing and queue monitoring.
4. Add authentication and authorization.
5. Consider explicit workload chunking if individual jobs become extremely large.
6. Add dead-letter handling and stronger retry policies based on operational requirements.

## Intentional scope

The assignment explicitly asks for one certificate template and does not require a template editor, multiple designs, frontend, Kubernetes, or cloud deployment. Those features are excluded deliberately so the required backend behavior remains straightforward to review and explain.
