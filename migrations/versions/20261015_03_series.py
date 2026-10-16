"""Add structured series membership and editorial ordering."""
import re
import logging

import sqlalchemy as sa
from alembic import op

revision = "20261015_03"
down_revision = "20261015_02"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "series",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("published", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("slug", name="uq_series_slug"),
    )
    op.create_index("ix_series_slug", "series", ["slug"], unique=False)
    op.add_column("photos", sa.Column("series_id", sa.Integer(), nullable=True))
    op.add_column("photos", sa.Column("series_position", sa.Integer(), nullable=True))
    op.add_column("photos", sa.Column("show_in_preview", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("photos", sa.Column("preview_position", sa.Integer(), nullable=True))
    with op.batch_alter_table("photos") as batch:
        batch.create_foreign_key("fk_photos_series_id_series", "series", ["series_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_photos_series_id", "photos", ["series_id"], unique=False)

    bind = op.get_bind()
    now = sa.text("CURRENT_TIMESTAMP")
    values = bind.execute(sa.text("SELECT DISTINCT series_slug FROM photos WHERE series_slug IS NOT NULL AND trim(series_slug) <> '' ORDER BY series_slug")).scalars().all()
    # Only URL-safe legacy identifiers can be mapped without changing existing URLs.
    safe = [slug for slug in values if re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug) and len(slug) <= 100]
    review = [slug for slug in values if slug not in safe]
    if review:
        logging.getLogger("alembic.runtime.migration").warning(
            "Series migration left %d legacy series_slug value(s) unmapped for manual review: %s",
            len(review), ", ".join(repr(value) for value in review[:20]),
        )
    series_table = sa.table("series", sa.column("id", sa.Integer()), sa.column("slug", sa.String()), sa.column("title", sa.String()), sa.column("description", sa.Text()), sa.column("position", sa.Integer()), sa.column("published", sa.Boolean()), sa.column("created_at", sa.DateTime()), sa.column("updated_at", sa.DateTime()))
    for position, slug in enumerate(safe):
        bind.execute(series_table.insert().values(slug=slug, title=slug.replace("-", " ").title(), position=position, published=False, created_at=now, updated_at=now))
    if safe:
        placeholders = ",".join(f":slug{i}" for i in range(len(safe)))
        params = {f"slug{i}": slug for i, slug in enumerate(safe)}
        bind.execute(sa.text(f"UPDATE photos SET series_id = (SELECT id FROM series WHERE series.slug = photos.series_slug), series_position = (SELECT count(*) FROM photos p2 WHERE p2.series_slug = photos.series_slug AND (p2.created_at > photos.created_at OR (p2.created_at = photos.created_at AND p2.id > photos.id))) WHERE series_slug IN ({placeholders})"), params)


def downgrade():
    op.drop_index("ix_photos_series_id", table_name="photos")
    with op.batch_alter_table("photos") as batch:
        batch.drop_constraint("fk_photos_series_id_series", type_="foreignkey")
        for column in ("preview_position", "show_in_preview", "series_position", "series_id"):
            batch.drop_column(column)
    op.drop_index("ix_series_slug", table_name="series")
    op.drop_table("series")
