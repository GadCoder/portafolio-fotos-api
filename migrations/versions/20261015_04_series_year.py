"""Move the portfolio year onto series records."""
import sqlalchemy as sa
from alembic import op


revision = "20261015_04"
down_revision = "20261015_03"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("series", sa.Column("year", sa.Integer(), nullable=True))
    op.drop_column("photos", "year")


def downgrade():
    op.add_column("photos", sa.Column("year", sa.Integer(), nullable=True))
    op.drop_column("series", "year")
