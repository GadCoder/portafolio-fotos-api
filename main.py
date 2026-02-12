from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from db.session import engine, Base
from apis.base import api_router


def create_tables():
    Base.metadata.create_all(bind=engine)


def include_router(app):
    app.include_router(api_router)


def add_middleware(app):
    # CORS: no wildcard with credentials - using empty origins list 
    # since this is a same-origin app (HTML templates served from same origin)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["https://portfolio.gadsw.dev", "https://portfolio-api.gadsw.dev"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
def start_application():
    app = FastAPI()
    create_tables()
    include_router(app)
    add_middleware(app)
    return app

app = start_application()



app.mount("/static", StaticFiles(directory="static"), name="static")
