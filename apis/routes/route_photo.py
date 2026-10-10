from typing import Annotated, List
from sqlalchemy.orm import Session
from fastapi import APIRouter, Form, Request, UploadFile, Depends, BackgroundTasks, Header, HTTPException
from db.session import get_db
from schemas.photo import Photo
from repository.photo import get_all_photos, upload_photo, delete_photo_from_db
from repository.user import valid_csrf_token
from repository.html import get_main_page


router = APIRouter()


@router.get("/get-all-photos/", response_model=List[Photo])
def get_all(db: Session = Depends(get_db)):
    photos = get_all_photos(db=db)
    return photos


@router.post("/upload-photos/")
async def upload_photos(
    request: Request,
    csrf_token: Annotated[str, Form()],
    files: List[UploadFile],
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    if not request.session.get("user"):
        raise HTTPException(status_code=401, detail="Authentication required")
    if not valid_csrf_token(request.session.get("csrf_token"), csrf_token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")

    for file in files:
        file_data = await file.read()
        filename = file.filename
        background_tasks.add_task(
            upload_photo, db=db, file=file_data, filename=filename
        )
    photos = get_all_photos(db=db)
    return get_main_page(
        context={
            "request": request,
            "csrf_token": request.session["csrf_token"],
            "existing_photos": photos,
        }
    )


@router.delete("/delete-photo/{photo_id}")
def delete_photo(
    request: Request,
    photo_id: int,
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    db: Session = Depends(get_db),
):
    if not request.session.get("user"):
        raise HTTPException(status_code=401, detail="Authentication required")
    if not valid_csrf_token(request.session.get("csrf_token"), csrf_token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")
    return delete_photo_from_db(db=db, photo_id=photo_id)
