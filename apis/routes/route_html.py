from typing import Annotated
from fastapi import APIRouter
from fastapi import Depends, Request, Form
from sqlalchemy.orm import Session
from db.session import get_db
from repository.html import get_login_page, get_main_page, get_unauthorized_page
from repository.user import authenticate_user
from repository.photo import get_all_photos


router = APIRouter()


@router.get("/login-page")
async def root(request: Request):
    return get_login_page(context={"request": request})


@router.post("/login-user/")
def login_user(
    user: Annotated[str, Form()],
    password: Annotated[str, Form()],
    request: Request,
    db: Session = Depends(get_db),
):
    user_authenticated = authenticate_user(user=user, password=password)
    if not user_authenticated:
        return get_unauthorized_page(context={"request": request})
    photos = get_all_photos(db=db)
    # FIX: Removed credentials from template context to prevent DOM exposure
    return get_main_page(
        context={
            "request": request,
            "existing_photos": photos,
        }
    )
