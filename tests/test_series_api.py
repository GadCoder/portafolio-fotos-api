import base64
import hashlib
import os
import re
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("SESSION_SECRET", "test-session-secret-with-sufficient-length")
os.environ.setdefault("APP_USER", "admin")
os.environ.setdefault("APP_PASSWORD_HASH", "pbkdf2_sha256$10000$testsalt$" + base64.urlsafe_b64encode(hashlib.pbkdf2_hmac("sha256", b"correct-password", b"testsalt", 10000)).decode())
os.environ.setdefault("APP_ENV", "test")
os.environ["COOKIE_SECURE"] = "false"

from db.session import Base, get_db
from db.models.photo import Photo
from db.models.gallery_publication import GalleryPublication
from db.models.series import Series
from main import app


@pytest.fixture
def series_client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(engine)
    with factory() as db:
        db.add(GalleryPublication(id=1, revision=0, requested_revision=0, changed_at=datetime.now(timezone.utc)))
        db.commit()

    def override_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as http:
        yield http, factory
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


def login(http):
    csrf = http.get("/admin/api/session").json()["csrf_token"]
    return http.post("/admin/api/login", json={"user": "admin", "password": "correct-password"}, headers={"X-CSRF-Token": csrf}).json()["csrf_token"]


def legacy_login(http):
    page = http.get("/login-page")
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
    http.post("/login-user/", data={"user": "admin", "password": "correct-password", "csrf_token": csrf})
    return re.search(r'name="csrf_token" value="([^"]+)"', http.get("/admin-page").text).group(1)


def add_photos(factory, n):
    with factory() as db:
        photos = [Photo(is_horizontal=True, photo_url=f"https://example.test/{i}.webp", name=f"{i}.webp") for i in range(n)]
        db.add_all(photos)
        db.commit()
        return [p.id for p in photos]


def test_public_series_filter_drafts_and_ordered_detail(series_client):
    http, _ = series_client
    csrf = login(http)
    draft = http.post("/admin/api/series", json={"slug": "draft", "title": "Draft", "position": 0}, headers={"X-CSRF-Token": csrf}).json()
    public = http.post("/admin/api/series", json={"slug": "public", "title": "Public", "position": 1, "published": True}, headers={"X-CSRF-Token": csrf})
    assert public.status_code == 200
    assert [s["slug"] for s in http.get("/series/").json()] == ["public"]
    assert http.get("/series/draft/").status_code == 404
    assert http.get("/series/public/").json()["id"] == public.json()["id"]
    assert http.get("/admin/api/series").json()[0]["published"] is False


def test_membership_preview_publication_and_legacy_slug_consistency(series_client):
    http, factory = series_client
    csrf = login(http)
    ids = add_photos(factory, 7)
    series = http.post("/admin/api/series", json={"slug": "street", "title": "Street", "position": 0}, headers={"X-CSRF-Token": csrf}).json()
    sid = series["id"]
    headers = {"X-CSRF-Token": csrf}
    assert http.put(f"/admin/api/series/{sid}/photos", json={"photoIds": ids}, headers=headers).status_code == 200
    assert http.patch(f"/admin/api/series/{sid}", json={"published": True}, headers=headers).status_code == 422
    assert http.put(f"/admin/api/series/{sid}/preview", json={"photoIds": ids[:5]}, headers=headers).status_code == 200
    assert http.patch(f"/admin/api/series/{sid}", json={"published": True}, headers=headers).status_code == 200
    detail = http.get("/series/street/").json()
    assert [p["id"] for p in detail["photos"]] == ids
    assert [p["id"] for p in detail["previewPhotos"]] == ids[:5]
    assert detail["photos"][0]["seriesId"] == sid
    with factory() as db:
        photo = db.get(Photo, ids[0])
        assert photo.series_slug == "street"
    # Legacy photo endpoint must preserve the relationship and reject invalid slugs.
    legacy_csrf = legacy_login(http)
    legacy_headers = {"X-CSRF-Token": legacy_csrf}
    assert http.patch(f"/photo/{ids[0]}/presentation", json={"seriesSlug": "missing"}, headers=legacy_headers).status_code == 422
    assert http.patch(f"/photo/{ids[0]}/presentation", json={"seriesSlug": None}, headers=legacy_headers).status_code == 200
    with factory() as db:
        photo = db.get(Photo, ids[0])
        assert photo.series_id is None and photo.series_slug is None


def test_membership_rejects_stealing_preview_limit_and_duplicate_order(series_client):
    http, factory = series_client
    csrf = login(http)
    ids = add_photos(factory, 7)
    headers = {"X-CSRF-Token": csrf}
    first = http.post("/admin/api/series", json={"slug": "one", "title": "One", "position": 0}, headers=headers).json()
    second = http.post("/admin/api/series", json={"slug": "two", "title": "Two", "position": 1}, headers=headers).json()
    assert http.put(f"/admin/api/series/{first['id']}/photos", json={"photoIds": ids[:6]}, headers=headers).status_code == 200
    assert http.put(f"/admin/api/series/{first['id']}/preview", json={"photoIds": ids[:6]}, headers=headers).status_code == 422
    assert http.put(f"/admin/api/series/{second['id']}/photos", json={"photoIds": [ids[0]]}, headers=headers).status_code == 409
    assert http.put("/admin/api/series/order", json={"seriesIds": [first["id"], first["id"]]}, headers=headers).status_code == 422


def test_delete_detaches_photos_without_assets_orphans(series_client, monkeypatch):
    http, factory = series_client
    import repository.photo as photo_repository
    deleted_assets = []
    monkeypatch.setattr(photo_repository, "delete_from_s3", lambda filename: deleted_assets.append(filename))
    csrf = login(http)
    ids = add_photos(factory, 2)
    series = http.post("/admin/api/series", json={"slug": "safe", "title": "Safe", "position": 0}, headers={"X-CSRF-Token": csrf}).json()
    http.put(f"/admin/api/series/{series['id']}/photos", json={"photoIds": ids}, headers={"X-CSRF-Token": csrf})
    assert http.delete(f"/admin/api/series/{series['id']}", headers={"X-CSRF-Token": csrf}).status_code == 200
    with factory() as db:
        assert db.query(Photo).count() == 2
        assert db.query(Photo).filter(Photo.series_id.is_not(None)).count() == 0
    assert deleted_assets == []


def test_series_mutations_require_auth_and_csrf(series_client):
    http, _ = series_client
    assert http.post("/admin/api/series", json={"slug": "x", "title": "X", "position": 0}).status_code == 401
    csrf = login(http)
    assert http.post("/admin/api/series", json={"slug": "x", "title": "X", "position": 0}).status_code == 403


@pytest.mark.parametrize("count", range(8))
def test_preview_payload_for_zero_through_seven_photos(series_client, count):
    http, factory = series_client
    csrf = login(http)
    ids = add_photos(factory, count)
    series = http.post("/admin/api/series", json={"slug": "count-check", "title": "Count", "published": False}, headers={"X-CSRF-Token": csrf}).json()
    sid = series["id"]
    headers = {"X-CSRF-Token": csrf}
    assert http.put(f"/admin/api/series/{sid}/photos", json={"photoIds": ids}, headers=headers).status_code == 200
    chosen = ids[:3]
    assert http.put(f"/admin/api/series/{sid}/preview", json={"photoIds": chosen}, headers=headers).status_code == 200
    assert http.patch(f"/admin/api/series/{sid}", json={"published": True}, headers=headers).status_code == 200
    payload = http.get("/series/count-check/").json()
    expected = ids if count <= 5 else chosen
    assert [photo["id"] for photo in payload["previewPhotos"]] == expected
    assert [photo["id"] for photo in payload["photos"]] == ids


def test_publication_revision_changes_only_for_committed_public_edits(series_client):
    http, factory = series_client
    csrf = login(http)
    headers = {"X-CSRF-Token": csrf}

    def revision():
        with factory() as db:
            return db.get(GalleryPublication, 1).revision

    before = revision()
    created = http.post("/admin/api/series", json={"slug": "revision-test", "title": "Revision"}, headers=headers)
    sid = created.json()["id"]
    assert revision() == before + 1
    ids = add_photos(factory, 7)
    base = revision()
    assert http.put(f"/admin/api/series/{sid}/photos", json={"photoIds": ids}, headers=headers).status_code == 200
    assert revision() == base + 1
    base = revision()
    assert http.put(f"/admin/api/series/{sid}/preview", json={"photoIds": ids[:6]}, headers=headers).status_code == 422
    assert revision() == base
    assert http.put(f"/admin/api/series/{sid}/preview", json={"photoIds": ids[:2]}, headers=headers).status_code == 200
    assert revision() == base + 1
    base = revision()
    assert http.patch(f"/admin/api/series/{sid}", json={"published": True}, headers=headers).status_code == 200
    assert revision() == base + 1
    base = revision()
    assert http.patch(f"/admin/api/series/{sid}", json={"title": "Revised"}, headers=headers).status_code == 200
    assert revision() == base + 1
    base = revision()
    assert http.put("/admin/api/series/order", json={"seriesIds": [sid]}, headers=headers).status_code == 200
    assert revision() == base + 1
    base = revision()
    assert http.patch(f"/admin/api/photos/{ids[0]}/presentation", json={"featured": True}, headers=headers).status_code == 200
    assert revision() == base + 1
    base = revision()
    assert http.delete(f"/admin/api/series/{sid}", headers=headers).status_code == 200
    assert revision() == base + 1


def test_removing_only_preview_from_published_large_series_is_rejected(series_client, monkeypatch):
    http, factory = series_client
    import repository.photo as photo_repository
    deleted_assets = []
    monkeypatch.setattr(photo_repository, "delete_from_s3", lambda filename: deleted_assets.append(filename))
    csrf = login(http)
    ids = add_photos(factory, 7)
    headers = {"X-CSRF-Token": csrf}
    sid = http.post("/admin/api/series", json={"slug": "single-preview", "title": "Single"}, headers=headers).json()["id"]
    assert http.put(f"/admin/api/series/{sid}/photos", json={"photoIds": ids}, headers=headers).status_code == 200
    assert http.put(f"/admin/api/series/{sid}/preview", json={"photoIds": [ids[0]]}, headers=headers).status_code == 200
    assert http.patch(f"/admin/api/series/{sid}", json={"published": True}, headers=headers).status_code == 200
    legacy_csrf = legacy_login(http)
    assert http.patch(f"/photo/{ids[0]}/presentation", json={"seriesSlug": None}, headers={"X-CSRF-Token": legacy_csrf}).status_code == 422
    assert http.delete(f"/admin/api/photos/{ids[0]}", headers=headers).status_code == 422
    assert deleted_assets == []
    with factory() as db:
        photo = db.get(Photo, ids[0])
        assert photo is not None and photo.series_id == sid and photo.show_in_preview is True


def test_series_and_photo_reorder_round_trip(series_client):
    http, factory = series_client
    csrf = login(http)
    headers = {"X-CSRF-Token": csrf}
    first = http.post("/admin/api/series", json={"slug": "first", "title": "First"}, headers=headers).json()
    second = http.post("/admin/api/series", json={"slug": "second", "title": "Second"}, headers=headers).json()
    third = http.post("/admin/api/series", json={"slug": "third", "title": "Third"}, headers=headers).json()
    ids = add_photos(factory, 3)
    assert http.put(f"/admin/api/series/{first['id']}/photos", json={"photoIds": list(reversed(ids))}, headers=headers).status_code == 200
    assert http.put("/admin/api/series/order", json={"seriesIds": [third["id"], second["id"], first["id"]]}, headers=headers).status_code == 200
    assert [item["id"] for item in http.get("/admin/api/series").json()] == [third["id"], second["id"], first["id"]]
    assert [item["id"] for item in http.get("/admin/api/series").json()[2]["photos"]] == list(reversed(ids))


def test_metadata_nulls_slug_collision_and_malformed_ids(series_client):
    http, factory = series_client
    csrf = login(http)
    headers = {"X-CSRF-Token": csrf}
    first = http.post("/admin/api/series", json={"slug": "collision", "title": "Collision"}, headers=headers).json()
    second_response = http.post("/admin/api/series", json={"slug": "collision", "title": "Duplicate"}, headers=headers)
    assert second_response.status_code == 409
    sid = first["id"]
    with factory() as db:
        revision_before_invalid_metadata = db.get(GalleryPublication, 1).revision
    for field in ("slug", "title", "position", "published"):
        assert http.patch(f"/admin/api/series/{sid}", json={field: None}, headers=headers).status_code == 422
    with factory() as db:
        assert db.get(GalleryPublication, 1).revision == revision_before_invalid_metadata
    ids = add_photos(factory, 2)
    assert http.put(f"/admin/api/series/{sid}/photos", json={"photoIds": [ids[0], 999999]}, headers=headers).status_code == 404
    assert http.put(f"/admin/api/series/{sid}/photos", json={"photoIds": [ids[0], ids[0]]}, headers=headers).status_code == 422
    other = http.post("/admin/api/series", json={"slug": "other", "title": "Other"}, headers=headers).json()
    assert http.put(f"/admin/api/series/{other['id']}/preview", json={"photoIds": [ids[0]]}, headers=headers).status_code == 422
    assert http.put(f"/admin/api/series/{sid}/preview", json={"photoIds": [ids[0], ids[1], 999999]}, headers=headers).status_code == 422
