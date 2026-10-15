import base64
import hashlib
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("SESSION_SECRET", "test-session-secret-with-sufficient-length")
os.environ.setdefault("APP_USER", "admin")
os.environ.setdefault(
    "APP_PASSWORD_HASH",
    "pbkdf2_sha256$10000$testsalt$" + base64.urlsafe_b64encode(
        hashlib.pbkdf2_hmac("sha256", b"correct-password", b"testsalt", 10000)
    ).decode(),
)
os.environ["COOKIE_SECURE"] = "false"

from db.session import Base, get_db
from db.models.photo import Photo
from db.models.admin_session import AdminSession
from main import app


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(engine)

    def override_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        yield test_client, TestingSession
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_anonymous_session_has_login_csrf(client):
    response = client[0].get("/admin/api/session")
    assert response.status_code == 200
    assert response.json()["authenticated"] is False
    assert response.json()["csrf_token"]


def test_login_rejects_missing_csrf(client):
    assert client[0].post("/admin/api/login", json={"user": "admin", "password": "correct-password"}).status_code == 403


def test_valid_login_returns_secure_contract_and_logout_revokes(client):
    http = client[0]
    csrf = http.get("/admin/api/session").json()["csrf_token"]
    login = http.post("/admin/api/login", json={"user": "admin", "password": "correct-password"}, headers={"X-CSRF-Token": csrf})
    assert login.status_code == 200
    assert login.cookies.get("portfolio_admin_session")
    assert "httponly" in login.headers["set-cookie"].lower()
    session = http.get("/admin/api/session")
    assert session.json()["authenticated"] is True
    assert session.json()["csrf_token"] != csrf
    assert http.post("/admin/api/logout", headers={"X-CSRF-Token": session.json()["csrf_token"]}).status_code == 204
    assert http.get("/admin/api/session").json()["authenticated"] is False


def test_photos_requires_authentication(client):
    assert client[0].get("/admin/api/photos").status_code == 401


def test_photo_list_returns_canonical_photo_shape(client):
    http, factory = client
    csrf = http.get("/admin/api/session").json()["csrf_token"]
    http.post("/admin/api/login", json={"user": "admin", "password": "correct-password"}, headers={"X-CSRF-Token": csrf})
    with factory() as db:
        db.add(Photo(is_horizontal=True, photo_url="https://example.test/a.webp", name="a.webp", width=120, height=80))
        db.commit()
    response = http.get("/admin/api/photos")
    assert response.status_code == 200
    assert set(response.json()[0]) == {"id", "is_horizontal", "photo_url", "name", "width", "height", "featured", "featuredLayout", "title", "location", "year", "seriesSlug", "created_at"}


def test_invalid_login_is_401(client):
    http = client[0]
    csrf = http.get("/admin/api/session").json()["csrf_token"]
    response = http.post("/admin/api/login", json={"user": "admin", "password": "wrong"}, headers={"X-CSRF-Token": csrf})
    assert response.status_code == 401


def def_login(http):
    csrf = http.get("/admin/api/session").json()["csrf_token"]
    return http.post("/admin/api/login", json={"user": "admin", "password": "correct-password"}, headers={"X-CSRF-Token": csrf})


def test_mutation_requires_csrf_even_when_header_missing(client):
    http = client[0]
    def_login(http)
    assert http.delete("/admin/api/photos/10").status_code == 403


def test_session_cookie_is_not_stored_as_raw_bearer(client):
    http, factory = client
    login = def_login(http)
    raw_token = login.cookies["portfolio_admin_session"]
    cookie = login.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "path=/" in cookie
    assert "max-age=28800" in cookie
    with factory() as db:
        row = db.query(AdminSession).one()
        assert row.token_hash != raw_token
        assert len(row.token_hash) == 64
        assert row.expires_at > row.created_at


def test_expired_session_is_rejected_and_removed(client):
    from datetime import timedelta
    from db.models.admin_session import AdminSession
    http, factory = client
    def_login(http)
    with factory() as db:
        row = db.query(AdminSession).one()
        row.expires_at = row.created_at - timedelta(seconds=1)
        db.commit()
    assert http.get("/admin/api/photos").status_code == 401
    with factory() as db:
        assert db.query(AdminSession).count() == 0


def test_login_csrf_must_match_anonymous_cookie(client):
    http = client[0]
    http.get("/admin/api/session")
    assert http.post("/admin/api/login", json={"user": "admin", "password": "correct-password"}, headers={"X-CSRF-Token": "not-the-cookie"}).status_code == 403


def test_presentation_patch_requires_valid_csrf_and_returns_photo(client):
    http, factory = client
    csrf = def_login(http).json()["csrf_token"]
    with factory() as db:
        photo = Photo(is_horizontal=True, photo_url="https://example.test/a.webp", name="a.webp", width=120, height=80)
        db.add(photo)
        db.commit()
        photo_id = photo.id
    assert http.patch(f"/admin/api/photos/{photo_id}/presentation", json={"title": "New"}).status_code == 403
    response = http.patch(f"/admin/api/photos/{photo_id}/presentation", json={"title": "New", "featured": True}, headers={"X-CSRF-Token": csrf})
    assert response.status_code == 200
    assert response.json()["title"] == "New"
    assert response.json()["featured"] is True


def test_upload_rejects_bad_image_with_safe_filename(client):
    http = client[0]
    csrf = def_login(http).json()["csrf_token"]
    response = http.post("/admin/api/photos/upload", files=[("files", ("../bad\\image.jpg", b"not an image", "image/jpeg"))], headers={"X-CSRF-Token": csrf})
    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["filename"] == "image.jpg"
    assert result["success"] is False
    assert "error" in result


def test_delete_missing_photo_returns_not_found(client):
    http = client[0]
    csrf = def_login(http).json()["csrf_token"]
    response = http.delete("/admin/api/photos/999", headers={"X-CSRF-Token": csrf})
    assert response.status_code == 404


def test_untrusted_origin_cannot_mutate(client):
    http = client[0]
    csrf = def_login(http).json()["csrf_token"]
    response = http.delete("/admin/api/photos/999", headers={"X-CSRF-Token": csrf, "Origin": "https://attacker.example"})
    assert response.status_code == 403

