"""Persist pending requests to rebuild the static gallery."""
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "20261015_02"
down_revision = "20261015_01"
branch_labels = None
depends_on = None


def upgrade():
    table = op.create_table(
        "gallery_publication",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("requested_revision", sa.Integer(), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.bulk_insert(table, [{"id": 1, "revision": 0, "requested_revision": 0,
                           "changed_at": datetime.now(timezone.utc)}])


def downgrade():
    op.drop_table("gallery_publication")
