from typing import Annotated
from fastapi import APIRouter
from fastapi import Depends, Request, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from db.session import get_db
from repository.html import get_login_page, get_main_page, get_unauthorized_page
from repository.user import authenticate_user, new_csrf_token, valid_csrf_token
from repository.photo import get_all_photos


router = APIRouter()


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
    db: Session = Depends(get_db),
):
    if not valid_csrf_token(request.session.get("csrf_token"), csrf_token):
        return get_unauthorized_page(context={"request": request})
    if not authenticate_user(user=user, password=password):
        return get_unauthorized_page(context={"request": request})
    request.session.clear()
    request.session["user"] = user
    request.session["csrf_token"] = new_csrf_token()
    photos = get_all_photos(db=db)
    return get_main_page(
        context={
            "request": request,
            "csrf_token": request.session["csrf_token"],
            "existing_photos": photos,
        }
    )


@router.post("/logout/")
def logout(request: Request, csrf_token: Annotated[str, Form()]):
    if not valid_csrf_token(request.session.get("csrf_token"), csrf_token):
        return get_unauthorized_page(context={"request": request})
    request.session.clear()
    return RedirectResponse(url="/login-page", status_code=303)
