from typing import Annotated, List
from sqlalchemy.orm import Session
from fastapi import APIRouter, Form, Request, UploadFile, Depends, BackgroundTasks
from db.session import get_db, SessionLocal
from schemas.photo import Photo
from repository.photo import get_all_photos, upload_photo, delete_photo_from_db
from repository.user import authenticate_user
from repository.html import get_unauthorized_page, get_main_page


router = APIRouter()


@router.get("/get-all-photos/", response_model=List[Photo])
def get_all(db: Session = Depends(get_db)):
    photos = get_all_photos(db=db)
    return photos


@router.post("/upload-photos/")
async def upload_photos(
    user: Annotated[str, Form()],
    password: Annotated[str, Form()],
    request: Request,
    files: List[UploadFile],
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Upload photos endpoint. Returns HTML page on success/failure (not JSON)."""
    user_authenticated = authenticate_user(user=user, password=password)
    if not user_authenticated:
        return get_unauthorized_page(context={"request": request})

    for file in files:
        file_data = await file.read()
        filename = file.filename
        # Use independent DB session for background task to avoid using closed request-scoped session
        background_tasks.add_task(
            upload_photo_task, file=file_data, filename=filename
        )
    photos = get_all_photos(db=db)
    return get_main_page(
        context={
            "request": request,
            "existing_photos": photos,
        }
    )


def upload_photo_task(file: bytes, filename: str):
    """Background task with its own DB session."""
    db = SessionLocal()
    try:
        upload_photo(db=db, file=file, filename=filename)
    finally:
        db.close()


@router.delete("/delete-photo/{photo_id}")
def delete_photo(
    request: Request,
    photo_id: int,
    user: Annotated[str, Form()],
    password: Annotated[str, Form()],
    db: Session = Depends(get_db),
):
    """Delete photo endpoint. Credentials passed via request body, not URL path."""
    user_authenticated = authenticate_user(user=user, password=password)
    if not user_authenticated:
        return get_unauthorized_page(context={"request": request})
    return delete_photo_from_db(db=db, photo_id=photo_id)
