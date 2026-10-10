"""Add photo creation timestamps and backfill existing photos by ID.

Revision ID: 20261010_01
Revises:
Create Date: 2026-10-10
"""
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "20261010_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)

    if "photos" not in inspector.get_table_names():
        op.create_table(
            "photos",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("is_horizontal", sa.Boolean(), nullable=True),
            sa.Column("photo_url", sa.String(length=255), nullable=True),
            sa.Column("name", sa.String(length=255), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        return

    columns = {column["name"]: column for column in inspector.get_columns("photos")}
    if "created_at" not in columns:
        op.add_column(
            "photos", sa.Column("created_at", sa.DateTime(timezone=True), nullable=True)
        )

    photo_ids = bind.execute(
        sa.text("SELECT id FROM photos ORDER BY id ASC")
    ).scalars().all()
    photos = sa.table(
        "photos",
        sa.column("id", sa.Integer()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    timestamp = datetime.now(timezone.utc) - timedelta(seconds=max(len(photo_ids) - 1, 0))
    for photo_id in photo_ids:
        bind.execute(
            sa.update(photos)
            .where(photos.c.id == photo_id, photos.c.created_at.is_(None))
            .values(created_at=timestamp)
        )
        timestamp += timedelta(seconds=1)

    inspector = inspect(bind)
    created_at = next(
        column for column in inspector.get_columns("photos") if column["name"] == "created_at"
    )
    if created_at["nullable"]:
        with op.batch_alter_table("photos") as batch_op:
            batch_op.alter_column(
                "created_at",
                existing_type=sa.DateTime(timezone=True),
                nullable=False,
            )


def downgrade():
    inspector = inspect(op.get_bind())
    if "photos" in inspector.get_table_names() and any(
        column["name"] == "created_at" for column in inspector.get_columns("photos")
    ):
        with op.batch_alter_table("photos") as batch_op:
            batch_op.drop_column("created_at")
