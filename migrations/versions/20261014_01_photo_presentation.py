"""Add optional editorial metadata and intrinsic image dimensions."""
import sqlalchemy as sa
from alembic import op

revision = "20261014_01"
down_revision = "20261010_01"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("photos", sa.Column("featured", sa.Boolean(), nullable=False, server_default=sa.false()))
    for name, column_type in (
        ("featured_layout", sa.String(16)),
        ("title", sa.String(255)),
        ("location", sa.String(255)),
        ("year", sa.Integer()),
        ("series_slug", sa.String(255)),
        ("width", sa.Integer()),
        ("height", sa.Integer()),
    ):
        op.add_column("photos", sa.Column(name, column_type, nullable=True))


def downgrade():
    with op.batch_alter_table("photos") as batch_op:
        for name in ("height", "width", "series_slug", "year", "location", "title", "featured_layout", "featured"):
            batch_op.drop_column(name)
