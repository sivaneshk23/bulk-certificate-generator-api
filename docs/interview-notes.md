# Interview Notes

## Why FastAPI?

FastAPI gives typed request/response models, dependency injection, automatic OpenAPI documentation, and low framework overhead. It is a clean fit for a focused backend API.

## Why PostgreSQL?

The assignment requires a relational database. PostgreSQL provides durable transactional state for jobs, recipients, status updates, and progress counters.

## Why SQLAlchemy + Alembic?

SQLAlchemy separates persistence logic from the API layer and Alembic makes the schema reproducible across environments.

## Why Celery + Redis?

Generating many PDFs is background work. Redis provides the broker/backend and Celery provides worker execution. The API persists the job before queueing the work.

## Why per-recipient records?

A single bulk job can have mixed outcomes. Independent certificate rows make each result observable and prevent one failure from hiding successful work.

## How does partial validation work?

The request is structurally valid as long as the recipients collection exists and is non-empty. Individual recipient payloads are validated one by one. Invalid recipients are stored as `failed` records with the validation reason; valid recipients continue.

## How does failure isolation work?

Each certificate generation runs inside its own exception boundary. An exception changes only that certificate to `failed`; processing continues for the rest of the job.

## How is live progress calculated?

The worker persists certificate state and parent-job counters after each item. Progress is:

`(completed + failed) / total * 100`

`processing` and `pending` are exposed separately so clients can understand the current state.

## How is concurrent duplicate processing prevented?

Each job gets a PostgreSQL advisory lock derived from its job ID. If Celery redelivers the same job while another worker is still processing it, the second worker waits for the lock instead of racing with the first worker. SQLite tests use a local re-entrant lock.

## How is worker recovery handled?

Celery uses late acknowledgements and rejects tasks when a worker process is lost. On job resume, certificates left in `processing` are reset to `pending`. The deterministic certificate ID means a retry writes to the same output path rather than generating a new random file.

## How is path traversal prevented?

Recipient names never form filesystem paths. UUID certificate IDs are used for filenames. The download endpoints resolve requested paths and verify that they remain below the configured storage root.

## How is the PostgreSQL enum migration made safe?

The migration explicitly creates each PostgreSQL enum type once with `checkfirst=True`, then uses the same named type with `create_type=False` for table columns. This avoids the duplicate `CREATE TYPE` failure that can occur when SQLAlchemy attempts to create the enum a second time during table creation.

## Why use Unicode-aware PDF rendering?

Certificate names may contain multilingual data. The renderer uses available Noto fonts for Latin/Tamil and a built-in CJK PDF font for Chinese/Japanese/Korean characters. Docker installs the Noto packages needed for full multilingual rendering. If a host lacks a Tamil font, the application degrades without crashing instead of treating a missing font as a startup failure.

## Why plain canvas text instead of HTML/XML?

The certificate template is fixed. There is no reason to parse user-controlled strings as markup. Drawing strings directly prevents inputs such as `<b>` or `&` from being interpreted as ReportLab markup.

## Why local storage?

The assignment does not require cloud storage. Local files keep the implementation simple and inspectable. In production, storage can be replaced by S3-compatible object storage while keeping the database as metadata source of truth.

## How does idempotency work?

The creation request accepts an optional `idempotency_key`. The database has a unique index and the job stores a SHA-256 request fingerprint. Reusing a key with the same payload returns the existing job; reusing it with different payload content returns HTTP 409. The database uniqueness constraint also protects against concurrent retry requests.

## How would this handle 100,000 recipients?

Use stronger admission limits, explicit workload chunking, horizontal worker scaling, object storage, database batching, queue monitoring, and possibly one queue task per certificate or smaller logical batch. A single HTTP request should still create a durable parent job rather than generating all files synchronously.

## How would authentication be added?

Add OAuth2/JWT or another identity provider, then scope each job/certificate query to the authenticated principal or tenant. Authentication is intentionally outside the assignment requirements.

## Why no template editor or multiple templates?

The assignment explicitly asks for one predefined certificate template and says a template editor/multiple designs are unnecessary. Adding them would expand scope without improving compliance.

## Why no frontend?

This is a backend assignment. The REST/OpenAPI interface is sufficient for demonstration and evaluation.
