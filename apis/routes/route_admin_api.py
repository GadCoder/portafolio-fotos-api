import hmac
import os
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from db.session import get_db
from apis.config import portfolio_origins
from apis.photo_upload import (
    MAX_UPLOAD_BATCH_SIZE,
    MAX_UPLOAD_FILES,
    MAX_UPLOAD_SIZE,
    get_upload_filename,
    get_upload_size,
)
from repository.admin_session import (
    create_admin_session,
    get_active_admin_session,
    revoke_admin_session,
)
from schemas.photo import Photo, PhotoPresentationUpdate
from repository.photo import get_all_photos, update_photo_presentation, delete_photo_from_db, upload_photo
from repository.user import authenticate_user, new_csrf_token, valid_csrf_token

router = APIRouter(prefix="/admin/api", tags=["admin-api"])
COOKIE = "portfolio_admin_session"
PREAUTH_COOKIE = "portfolio_admin_login_csrf"
MAX_AGE = max(60, min(int(os.getenv("ADMIN_SESSION_MAX_AGE", "28800")), 604800))
def _secure_cookie_setting() -> bool:
    requested = os.getenv("COOKIE_SECURE", "true").strip().lower() == "true"
    environment = os.getenv("APP_ENV", "").strip().lower()
    if environment not in {"local", "dev", "development", "test", "testing"}:
        return True
    return requested


SECURE = _secure_cookie_setting()

class LoginBody(BaseModel):
    user: str
    password: str


def _origin_check(request: Request):
    origin = request.headers.get("origin")
    if origin:
        host = request.headers.get("host", "")
        expected = f"https://{host}" if request.url.scheme == "https" else f"http://{host}"
        trusted_origins = set(portfolio_origins())
        if not hmac.compare_digest(origin.rstrip("/"), expected) and origin.rstrip("/") not in trusted_origins:
            raise HTTPException(403, "Cross-origin request rejected")
    elif request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(403, "Cross-origin request rejected")


def _active(request: Request, db: Session):
    return get_active_admin_session(db, request.cookies.get(COOKIE))


def _require(request, db, csrf=None, *, state_changing=False):
    row = _active(request, db)
    if row is None:
        raise HTTPException(401, "Authentication required")
    if state_changing:
        _origin_check(request)
        if not valid_csrf_token(row.csrf_token, csrf):
            raise HTTPException(403, "Invalid CSRF token")
    return row


@router.get("/session")
def session_info(request: Request, response: Response, db: Session = Depends(get_db)):
    row = _active(request, db)
    if row:
        return {"authenticated": True, "user": row.user, "csrf_token": row.csrf_token}
    token = new_csrf_token()
    response.set_cookie(PREAUTH_COOKIE, token, max_age=300, httponly=True, secure=SECURE, samesite="lax", path="/")
    return {"authenticated": False, "csrf_token": token}


@router.post("/login")
def login(body: LoginBody, request: Request, response: Response, csrf: Annotated[str | None, Header(alias="X-CSRF-Token")] = None, db: Session = Depends(get_db)):
    _origin_check(request)
    preauth = request.cookies.get(PREAUTH_COOKIE)
    if not valid_csrf_token(preauth, csrf):
        raise HTTPException(403, "Invalid CSRF token")
    if not authenticate_user(body.user, body.password):
        raise HTTPException(401, "Invalid credentials")
    token, session = create_admin_session(
        db, body.user, max_age_seconds=MAX_AGE
    )
    response.set_cookie(COOKIE, token, max_age=MAX_AGE, httponly=True, secure=SECURE, samesite="lax", path="/")
    response.delete_cookie(PREAUTH_COOKIE, path="/")
    return {"authenticated": True, "user": body.user, "csrf_token": session.csrf_token}


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, csrf: Annotated[str | None, Header(alias="X-CSRF-Token")] = None, db: Session = Depends(get_db)):
    row = _require(request, db, csrf, state_changing=True)
    revoke_admin_session(db, row)
    response.delete_cookie(COOKIE, path="/", secure=SECURE, httponly=True, samesite="lax")


@router.get("/photos", response_model=list[Photo])
def photos(request: Request, db: Session = Depends(get_db)):
    _require(request, db)
    return get_all_photos(db=db)


@router.post("/photos/upload")
async def upload(request: Request, files: list[UploadFile], csrf: Annotated[str | None, Header(alias="X-CSRF-Token")] = None, db: Session = Depends(get_db)):
    _require(request, db, csrf, state_changing=True)
    if not files or len(files) > MAX_UPLOAD_FILES:
        raise HTTPException(400, f"Choose between 1 and {MAX_UPLOAD_FILES} images")
    sizes = [get_upload_size(f) for f in files]
    if sum(sizes) > MAX_UPLOAD_BATCH_SIZE:
        raise HTTPException(413, "Selected files exceed the 90 MB total upload limit")
    results = []
    for file, size in zip(files, sizes):
        name = get_upload_filename(file)
        if size > MAX_UPLOAD_SIZE:
            results.append({"filename": name, "success": False, "error": "File exceeds the 50 MB limit"})
        else:
            try:
                file.file.seek(0)
                stored = await run_in_threadpool(upload_photo, file.file, name)
                results.append({"filename": name, "stored_name": stored, "success": True})
            except HTTPException as exc:
                results.append({"filename": name, "success": False, "error": exc.detail})
            except Exception:
                results.append({"filename": name, "success": False, "error": "Upload failed"})
    return {"results": results}


@router.patch("/photos/{photo_id}/presentation", response_model=Photo)
def presentation(photo_id: int, data: PhotoPresentationUpdate, request: Request, csrf: Annotated[str | None, Header(alias="X-CSRF-Token")] = None, db: Session = Depends(get_db)):
    _require(request, db, csrf, state_changing=True)
    return update_photo_presentation(db, photo_id, data.model_dump(exclude_unset=True))


@router.delete("/photos/{photo_id}")
def delete(photo_id: int, request: Request, csrf: Annotated[str | None, Header(alias="X-CSRF-Token")] = None, db: Session = Depends(get_db)):
    _require(request, db, csrf, state_changing=True)
    return delete_photo_from_db(db=db, photo_id=photo_id)
