from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.models.gallery_publication import GalleryPublication
from repository import gallery_publication as publishing


@pytest.fixture
def publication_db(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    GalleryPublication.__table__.create(engine)
    sessions = sessionmaker(bind=engine)
    now = datetime.now(timezone.utc)
    with sessions() as db:
        db.add(GalleryPublication(id=1, revision=0, requested_revision=0, changed_at=now))
        db.commit()
    monkeypatch.setattr(publishing, "SessionLocal", sessions)
    return sessions, now


def test_queue_participates_in_photo_transaction(publication_db):
    sessions, _ = publication_db
    with sessions() as db:
        publishing.queue_gallery_publication(db)
        db.rollback()
    with sessions() as db:
        assert db.get(GalleryPublication, 1).revision == 0
        publishing.queue_gallery_publication(db)
        db.commit()
    with sessions() as db:
        assert db.get(GalleryPublication, 1).revision == 1


def test_burst_waits_then_requests_one_build(publication_db, monkeypatch):
    sessions, now = publication_db
    hook = Mock()
    monkeypatch.setattr(publishing.cloudflare_pages, "trigger_deploy", hook)
    with sessions() as db:
        publishing.queue_gallery_publication(db)
        publishing.queue_gallery_publication(db)
        db.commit()
    publishing.publish_pending_gallery(now=now + timedelta(seconds=1))
    hook.assert_not_called()
    publishing.publish_pending_gallery(now=now + timedelta(seconds=20))
    publishing.publish_pending_gallery(now=now + timedelta(seconds=30))
    assert hook.call_count == 1
    with sessions() as db:
        assert db.get(GalleryPublication, 1).requested_revision == 2


def test_failure_remains_pending_and_new_edits_are_not_lost(publication_db, monkeypatch):
    sessions, now = publication_db
    with sessions() as db:
        publishing.queue_gallery_publication(db)
        db.commit()
    monkeypatch.setattr(publishing.cloudflare_pages, "trigger_deploy", Mock(side_effect=OSError("connection lost")))
    with pytest.raises(OSError):
        publishing.publish_pending_gallery(now=now + timedelta(seconds=20))
    with sessions() as db:
        assert db.get(GalleryPublication, 1).requested_revision == 0

    def hook(*args, **kwargs):
        with sessions() as db:
            publishing.queue_gallery_publication(db)
            db.commit()

    monkeypatch.setattr(publishing.cloudflare_pages, "trigger_deploy", hook)
    publishing.publish_pending_gallery(now=now + timedelta(seconds=20))
    with sessions() as db:
        state = db.get(GalleryPublication, 1)
        assert state.revision == 2
        assert state.requested_revision == 1


def test_manual_publish_acknowledges_pending_edits_and_can_rebuild_unchanged_gallery(publication_db, monkeypatch):
    sessions, now = publication_db
    hook = Mock()
    monkeypatch.setattr(publishing.cloudflare_pages, "trigger_deploy", hook)
    with sessions() as db:
        publishing.queue_gallery_publication(db)
        db.commit()
    publishing.request_gallery_publication()
    with sessions() as db:
        assert db.get(GalleryPublication, 1).requested_revision == 1
    publishing.publish_pending_gallery(now=now + timedelta(seconds=30))
    assert hook.call_count == 1
    publishing.request_gallery_publication()
    assert hook.call_count == 2


def test_invalid_configuration_disables_automatic_publishing(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_PAGES_DEPLOY_HOOK_URL", "https://other.example/secret")
    assert publishing.cloudflare_pages.is_deploy_configured() is False
