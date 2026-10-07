"""create generation jobs and certificates

Revision ID: 0001_initial
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

_JOB_VALUES = ("queued", "processing", "completed", "completed_with_errors", "failed")
_CERTIFICATE_VALUES = ("pending", "processing", "completed", "failed")


def _postgres_enum(bind, values: tuple[str, ...], name: str):
    from sqlalchemy.dialects.postgresql import ENUM

    ENUM(*values, name=name, create_type=False).create(bind, checkfirst=True)
    return ENUM(*values, name=name, create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        job_status = _postgres_enum(bind, _JOB_VALUES, "jobstatus")
        certificate_status = _postgres_enum(bind, _CERTIFICATE_VALUES, "certificatestatus")
    else:
        job_status = sa.Enum(*_JOB_VALUES, name="jobstatus", native_enum=False)
        certificate_status = sa.Enum(
            *_CERTIFICATE_VALUES, name="certificatestatus", native_enum=False
        )

    op.create_table(
        "generation_jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("status", job_status, nullable=False),
        sa.Column("total_count", sa.Integer(), nullable=False),
        sa.Column("pending_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processing_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("idempotency_key", sa.String(length=128)),
        sa.Column("certificate_title", sa.String(length=200), nullable=False),
        sa.Column("course_name", sa.String(length=200), nullable=False),
        sa.Column("completion_date", sa.Date(), nullable=False),
        sa.Column("issuer_name", sa.String(length=200), nullable=False),
        sa.Column("issuer_designation", sa.String(length=200)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("error_summary", sa.Text()),
    )
    op.create_index(
        "ix_generation_jobs_idempotency_key",
        "generation_jobs",
        ["idempotency_key"],
        unique=True,
    )
    op.create_table(
        "certificates",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "job_id",
            sa.String(length=36),
            sa.ForeignKey("generation_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("recipient_name", sa.String(length=200), nullable=False),
        sa.Column("recipient_email", sa.String(length=320)),
        sa.Column("status", certificate_status, nullable=False),
        sa.Column("file_path", sa.String(length=1000)),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_certificates_job_id", "certificates", ["job_id"])
    op.create_index("ix_certificates_job_status", "certificates", ["job_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_certificates_job_status", table_name="certificates")
    op.drop_index("ix_certificates_job_id", table_name="certificates")
    op.drop_table("certificates")
    op.drop_index("ix_generation_jobs_idempotency_key", table_name="generation_jobs")
    op.drop_table("generation_jobs")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import ENUM

        ENUM(*_CERTIFICATE_VALUES, name="certificatestatus", create_type=False).drop(
            bind, checkfirst=True
        )
        ENUM(*_JOB_VALUES, name="jobstatus", create_type=False).drop(bind, checkfirst=True)
