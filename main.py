import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from fastapi.staticfiles import StaticFiles

from db.session import engine, Base
from apis.base import api_router

SESSION_SECRET = os.getenv("SESSION_SECRET")
if not SESSION_SECRET:
    raise RuntimeError("SESSION_SECRET must be set")
if not os.getenv("APP_USER") or not os.getenv("APP_PASSWORD_HASH"):
    raise RuntimeError("APP_USER and APP_PASSWORD_HASH must be set")


def create_tables():
    Base.metadata.create_all(bind=engine)


def include_router(app):
    app.include_router(api_router)


def add_middleware(app):
    app.add_middleware(
        SessionMiddleware,
        secret_key=SESSION_SECRET,
        session_cookie="portfolio_session",
        same_site="lax",
        https_only=os.getenv("COOKIE_SECURE", "true").lower() == "true",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
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
