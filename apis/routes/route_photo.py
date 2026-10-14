import os
from typing import Annotated, List
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, Form, Header, HTTPException, Request, UploadFile
from starlette.concurrency import run_in_threadpool
from db.session import get_db
from schemas.photo import Photo, PhotoPresentationUpdate
from repository.photo import get_all_photos, upload_photo, delete_photo_from_db, update_photo_presentation
from repository.user import valid_csrf_token


router = APIRouter()
MAX_UPLOAD_SIZE = 50 * 1024 * 1024
MAX_UPLOAD_BATCH_SIZE = 90 * 1024 * 1024
MAX_UPLOAD_FILES = 20


def get_upload_filename(file: UploadFile) -> str:
    return os.path.basename(
        (file.filename or "unnamed image").replace("\\", "/")
    ) or "unnamed image"


def get_upload_size(file: UploadFile) -> int:
    if file.size is not None:
        return file.size
    file.file.seek(0, os.SEEK_END)
    size = file.file.tell()
    file.file.seek(0)
    return size


async def process_uploaded_file(file: UploadFile, filename: str):
    try:
        file.file.seek(0)
        stored_name = await run_in_threadpool(upload_photo, file.file, filename)
        return {"filename": filename, "stored_name": stored_name, "success": True}
    except HTTPException as exc:
        return {"filename": filename, "success": False, "error": exc.detail}


@router.get("/get-all-photos/", response_model=List[Photo])
def get_all(db: Session = Depends(get_db)):
    photos = get_all_photos(db=db)
    return photos


@router.post("/upload-photos/")
async def upload_photos(
    request: Request,
    csrf_token: Annotated[str, Form()],
    files: List[UploadFile],
):
    if not request.session.get("user"):
        raise HTTPException(status_code=401, detail="Authentication required")
    if not valid_csrf_token(request.session.get("csrf_token"), csrf_token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")
    if not files or len(files) > MAX_UPLOAD_FILES:
        raise HTTPException(
            status_code=400, detail=f"Choose between 1 and {MAX_UPLOAD_FILES} images"
        )

    file_sizes = [get_upload_size(file) for file in files]
    if sum(file_sizes) > MAX_UPLOAD_BATCH_SIZE:
        raise HTTPException(
            status_code=413,
            detail="Selected files exceed the 90 MB total upload limit",
        )

    results = []
    for file, file_size in zip(files, file_sizes):
        filename = get_upload_filename(file)
        if file_size > MAX_UPLOAD_SIZE:
            results.append(
                {
                    "filename": filename,
                    "success": False,
                    "error": "File exceeds the 50 MB limit",
                }
            )
            continue
        results.append(await process_uploaded_file(file, filename))
    return {"results": results}


@router.patch("/{photo_id}/presentation", response_model=Photo)
def update_presentation(
    photo_id: int,
    presentation: PhotoPresentationUpdate,
    request: Request,
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    db: Session = Depends(get_db),
):
    if not request.session.get("user"):
        raise HTTPException(status_code=401, detail="Authentication required")
    if not valid_csrf_token(request.session.get("csrf_token"), csrf_token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")
    return update_photo_presentation(db, photo_id, presentation.model_dump(exclude_unset=True))


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
