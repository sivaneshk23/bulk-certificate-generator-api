"""add request fingerprint for strict idempotency"""

import sqlalchemy as sa
from alembic import op

revision = "0002_idempotency_fingerprint"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "generation_jobs",
        sa.Column("request_fingerprint", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("generation_jobs", "request_fingerprint")
