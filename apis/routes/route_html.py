from typing import Annotated
from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from db.session import get_db
from repository.html import get_login_page, get_main_page, get_photo_edit_page, get_unauthorized_page
from repository.user import authenticate_user, new_csrf_token, valid_csrf_token
from repository.photo import get_photo, get_photo_page


router = APIRouter()
ADMIN_PAGE_SIZE = 24


def render_admin_page(request: Request, db: Session, page: int):
    photos, total_photos = get_photo_page(
        db=db, page=page, page_size=ADMIN_PAGE_SIZE
    )
    total_pages = max(1, (total_photos + ADMIN_PAGE_SIZE - 1) // ADMIN_PAGE_SIZE)
    page = min(page, total_pages)
    if not photos and page > 1:
        page = total_pages
        photos, total_photos = get_photo_page(
            db=db, page=page, page_size=ADMIN_PAGE_SIZE
        )
    return get_main_page(
        context={
            "request": request,
            "csrf_token": request.session["csrf_token"],
            "existing_photos": photos,
            "page": page,
            "total_pages": total_pages,
            "total_photos": total_photos,
        }
    )


@router.get("/login-page")
async def root(request: Request):
    request.session.setdefault("csrf_token", new_csrf_token())
    return get_login_page(context={"request": request, "csrf_token": request.session["csrf_token"]})


@router.post("/login-user/")
def login_user(
    user: Annotated[str, Form()],
    password: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()],
    request: Request,
):
    if not valid_csrf_token(request.session.get("csrf_token"), csrf_token):
        return get_unauthorized_page(context={"request": request})
    if not authenticate_user(user=user, password=password):
        return get_unauthorized_page(context={"request": request})
    request.session.clear()
    request.session["user"] = user
    request.session["csrf_token"] = new_csrf_token()
    return RedirectResponse(url="/admin-page", status_code=303)


@router.get("/admin-page")
def admin_page(
    request: Request,
    page: Annotated[int, Query(ge=1)] = 1,
    db: Session = Depends(get_db),
):
    if not request.session.get("user"):
        return RedirectResponse(url="/login-page", status_code=303)
    return render_admin_page(request=request, db=db, page=page)


@router.get("/admin-page/photos/{photo_id}/edit")
def photo_edit_page(
    request: Request,
    photo_id: int,
    page: Annotated[int, Query(ge=1)] = 1,
    db: Session = Depends(get_db),
):
    if not request.session.get("user"):
        return RedirectResponse(url="/login-page", status_code=303)
    photo = get_photo(db, photo_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="Photo not found")
    return get_photo_edit_page(context={
        "request": request,
        "photo": photo,
        "page": page,
        "csrf_token": request.session["csrf_token"],
    })


@router.post("/logout/")
def logout(request: Request, csrf_token: Annotated[str, Form()]):
    if not valid_csrf_token(request.session.get("csrf_token"), csrf_token):
        return get_unauthorized_page(context={"request": request})
    request.session.clear()
    return RedirectResponse(url="/login-page", status_code=303)
