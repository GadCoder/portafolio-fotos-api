from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from db.session import engine, Base
from apis.base import api_router


def create_tables():
    Base.metadata.create_all(bind=engine)


def include_router(app):
    app.include_router(api_router)

def add_cors(app):
    origins = ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def start_application():
    app = FastAPI()
    create_tables()
    include_router(app)
    add_cors(app)
    return app


app = start_application()

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount('/files', StaticFiles(directory='files'), name='files')
