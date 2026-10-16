import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text


def test_series_migration_backfills_only_safe_slugs_and_preserves_unassigned_rows():
    migration_path = Path(__file__).parents[1] / "migrations" / "versions" / "20261015_03_series.py"
    spec = importlib.util.spec_from_file_location("series_migration_under_test", migration_path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE photos (id INTEGER PRIMARY KEY, series_slug VARCHAR(255), created_at DATETIME NOT NULL)"))
        connection.execute(text("INSERT INTO photos (id, series_slug, created_at) VALUES (1, 'street-photo', '2026-01-03'), (2, 'street-photo', '2026-01-02'), (3, ' Bad Slug ', '2026-01-04'), (4, NULL, '2026-01-01')"))
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        rows = connection.execute(text("SELECT id, series_slug, series_id, series_position FROM photos ORDER BY id")).mappings().all()
        assert [row["series_slug"] for row in rows] == ["street-photo", "street-photo", " Bad Slug ", None]
        assert rows[0]["series_id"] == rows[1]["series_id"]
        assert rows[0]["series_position"] == 0
        assert rows[1]["series_position"] == 1
        assert rows[2]["series_id"] is None and rows[2]["series_position"] is None
        assert rows[3]["series_id"] is None and rows[3]["series_position"] is None
        series = connection.execute(text("SELECT slug, published FROM series")).mappings().all()
        assert series == [{"slug": "street-photo", "published": 0}]
    engine.dispose()
