from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, Request, Form
from sqlalchemy.orm import Session
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from crud import upload_photos, get_all_photos, authenticate_user, delete_photo_from_db
from database import SessionLocal, engine
import models
import schemas
from typing import Annotated, List

models.Base.metadata.create_all(bind=engine)


app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

# Dependency


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/")
async def root(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login/")
def login_user(user: Annotated[str, Form()], password: Annotated[str, Form()], request: Request, db: Session = Depends(get_db)):
    user_authenticated = authenticate_user(user=user, password=password)
    if not user_authenticated:
        return templates.TemplateResponse("unauthorized.html", {"request": request})
    photos = get_all_photos(db=db)

    return templates.TemplateResponse("index.html", {
        "request": request,
        "user": user,
        "password": password,
        "existing_photos": photos
    })


@app.get("/get-all-photos/", response_model=List[schemas.Photo])
def get_all(db: Session = Depends(get_db)):
    photos = get_all_photos(db=db)
    return photos


@app.post("/upload-photos/", response_model=List[schemas.Photo])
async def upload_photo(user: Annotated[str, Form()], password: Annotated[str, Form()], request: Request, files: List[UploadFile] = File(...),  db: Session = Depends(get_db)):
    user_authenticated = authenticate_user(user=user, password=password)
    if not user_authenticated:
        return templates.TemplateResponse("unauthorized.html", {"request": request})

    upload_photos(db=db, files=files)
    photos = get_all_photos(db=db)
    return templates.TemplateResponse("index.html", {
        "request": request,
        "user": user,
        "password": password,
        "existing_photos": photos
    })


@app.delete("/delete-photo/{photo_id}")
def delete_photo(photo_id: int, db: Session = Depends(get_db)):
    return delete_photo_from_db(db=db, photo_id=photo_id)
