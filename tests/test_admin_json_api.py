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
os.environ.setdefault("APP_ENV", "test")
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
    logout = http.post("/admin/api/logout", headers={"X-CSRF-Token": session.json()["csrf_token"]})
    assert logout.status_code == 204
    assert logout.content == b""
    cookie = logout.headers["set-cookie"].lower()
    assert "portfolio_admin_session=" in cookie and "max-age=0" in cookie and "path=/" in cookie
    assert http.get("/admin/api/session").json()["authenticated"] is False
    with client[1]() as db:
        assert db.query(AdminSession).count() == 0


def test_photos_requires_authentication(client):
    assert client[0].get("/admin/api/photos").status_code == 401


def test_admin_mutations_require_authentication(client):
    http = client[0]
    assert http.post("/admin/api/photos/upload", files=[("files", ("a.jpg", b"x", "image/jpeg"))]).status_code == 401
    assert http.delete("/admin/api/photos/1").status_code == 401
    assert http.patch("/admin/api/photos/1/presentation", json={"title": "x"}).status_code == 401


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


def test_upload_success_calls_repository_and_returns_success(client, monkeypatch):
    import apis.routes.route_admin_api as admin_api
    calls = []
    def save(file, name):
        calls.append((file.read(), name))
        return {"photo_url": "https://example.test/saved.jpg", "name": name, "width": 1, "height": 1, "is_horizontal": True}
    monkeypatch.setattr(admin_api, "upload_photo", save)
    http = client[0]
    csrf = def_login(http).json()["csrf_token"]
    response = http.post("/admin/api/photos/upload", files=[("files", ("valid.jpg", b"valid-test-image", "image/jpeg"))], headers={"X-CSRF-Token": csrf})
    assert response.status_code == 200
    result = response.json()["results"][0]
    assert len(calls) == 1 and calls[0] == (b"valid-test-image", "valid.jpg")
    assert result["success"] is True
    assert result["filename"] == "valid.jpg"


def test_upload_per_file_and_batch_limits(client):
    from apis.routes.route_photo import MAX_UPLOAD_BATCH_SIZE, MAX_UPLOAD_FILES, MAX_UPLOAD_SIZE
    http = client[0]
    csrf = def_login(http).json()["csrf_token"]
    headers = {"X-CSRF-Token": csrf}
    too_large = http.post("/admin/api/photos/upload", files=[("files", ("large.jpg", b"x" * (MAX_UPLOAD_SIZE + 1), "image/jpeg"))], headers=headers)
    assert too_large.status_code == 200
    assert too_large.json()["results"][0]["success"] is False
    assert "error" in too_large.json()["results"][0]
    batch = http.post("/admin/api/photos/upload", files=[("files", (f"{i}.jpg", b"x" * (MAX_UPLOAD_BATCH_SIZE // 2 + 1), "image/jpeg")) for i in range(2)], headers=headers)
    assert batch.status_code == 413
    assert set(batch.json()) == {"detail"}
    count = http.post("/admin/api/photos/upload", files=[("files", (f"{i}.jpg", b"x", "image/jpeg")) for i in range(MAX_UPLOAD_FILES + 1)], headers=headers)
    assert count.status_code == 400
    assert set(count.json()) == {"detail"}


def test_production_frontend_cors_origin_allowed_without_wildcard(client):
    origin = "https://portfolio.gadcoder.com"
    preflight = client[0].options("/admin/api/photos", headers={"Origin": origin, "Access-Control-Request-Method": "GET"})
    assert preflight.headers.get("access-control-allow-origin") == origin
    assert preflight.headers.get("access-control-allow-origin") != "*"
    response = client[0].get("/admin/api/session", headers={"Origin": origin})
    assert response.headers.get("access-control-allow-origin") == origin
    assert response.headers.get("access-control-allow-origin") != "*"


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

def test_unexpected_upload_failure_is_reported_per_file_and_batch_continues(client, monkeypatch):
    import apis.routes.route_admin_api as admin_api
    calls = []
    def save(file, name):
        calls.append(name)
        if name == "broken.jpg":
            raise RuntimeError("sensitive backend detail")
        return {"photo_url": "https://example.test/ok.jpg"}
    monkeypatch.setattr(admin_api, "upload_photo", save)
    http = client[0]
    csrf = def_login(http).json()["csrf_token"]
    response = http.post("/admin/api/photos/upload", files=[
        ("files", ("broken.jpg", b"broken", "image/jpeg")),
        ("files", ("ok.jpg", b"ok", "image/jpeg")),
    ], headers={"X-CSRF-Token": csrf})
    assert response.status_code == 200
    results = response.json()["results"]
    assert [item["success"] for item in results] == [False, True]
    assert results[0]["filename"] == "broken.jpg"
    assert "sensitive backend detail" not in response.text
    assert calls == ["broken.jpg", "ok.jpg"]


def test_cookie_secure_is_forced_outside_explicit_dev_or_test(monkeypatch):
    import apis.routes.route_admin_api as admin_api
    monkeypatch.setenv("COOKIE_SECURE", "false")
    monkeypatch.setenv("APP_ENV", "production")
    assert admin_api._secure_cookie_setting() is True
    monkeypatch.setenv("APP_ENV", "test")
    assert admin_api._secure_cookie_setting() is False
    monkeypatch.setenv("APP_ENV", "dev")
    assert admin_api._secure_cookie_setting() is False


def test_cookie_secure_defaults_true(monkeypatch):
    import apis.routes.route_admin_api as admin_api
    monkeypatch.delenv("COOKIE_SECURE", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    assert admin_api._secure_cookie_setting() is True
