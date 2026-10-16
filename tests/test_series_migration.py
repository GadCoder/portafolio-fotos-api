import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text


def test_series_migration_does_not_create_or_assign_series_from_legacy_slugs():
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
        assert all(row["series_id"] is None and row["series_position"] is None for row in rows)
        series = connection.execute(text("SELECT slug, published FROM series")).mappings().all()
        assert series == []
    engine.dispose()
