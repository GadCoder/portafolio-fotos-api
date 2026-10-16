"""Add structured series membership and editorial ordering."""
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


def downgrade():
    op.drop_index("ix_photos_series_id", table_name="photos")
    with op.batch_alter_table("photos") as batch:
        batch.drop_constraint("fk_photos_series_id_series", type_="foreignkey")
        for column in ("preview_position", "show_in_preview", "series_position", "series_id"):
            batch.drop_column(column)
    op.drop_index("ix_series_slug", table_name="series")
    op.drop_table("series")
