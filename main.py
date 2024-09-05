from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from db.session import engine, Base
from apis.base import api_router


def create_tables():
    Base.metadata.create_all(bind=engine)


def include_router(app):
    app.include_router(api_router)


def start_application():
    app = FastAPI()
    create_tables()
    include_router(app)
    return app


origins = [
    "http://localhost",
    "http://localhost:8080",
    "https://portfolio-api.gadsw.dev",
    "http://portfolio-api.gadsw.dev",
    "https://photos.gadcoder.com",
    "http://photos.gadcoder.com",
]

app = start_application()


app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")
