from fastapi import APIRouter, Form, Request, UploadFile, Depends
from sqlalchemy.orm import Session
from typing import Annotated, List


from schemas.photo import Photo
from db.session import get_db

from repository.photo import get_all_photos, upload_photo, delete_photo_from_db
from repository.user import authenticate_user
from repository.html import get_unauthorized_page, get_main_page


router = APIRouter()


@router.get("/get-all-photos/", response_model=List[Photo])
def get_all(db: Session = Depends(get_db)):
    photos = get_all_photos(db=db)
    return photos


@router.post("/upload-photos/", response_model=List[Photo])
async def upload_photos(user: Annotated[str, Form()],
                        password: Annotated[str, Form()],
                        request: Request,
                        files: List[UploadFile], 
                        db: Session = Depends(get_db)):
    user_authenticated = authenticate_user(user=user, password=password)
    if not user_authenticated:
        return get_unauthorized_page(context={"request": request})
    
    for file in files:
        file_data = await file.read()
        filename = file.filename
        upload_photo(db=db, file=file_data, filename=filename)
    photos = get_all_photos(db=db)
    return get_main_page(context={ 
        "request": request, 
        "user": user, 
        "password": password, 
        "existing_photos": photos })


@router.delete("/delete-photo/{photo_id}")
def delete_photo(photo_id: int, db: Session = Depends(get_db)):
    return delete_photo_from_db(db=db, photo_id=photo_id)
