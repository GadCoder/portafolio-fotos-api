from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from settings import settings

# Use database URL from settings (supports MySQL via env config)
SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL

print(f"URL: {SQLALCHEMY_DATABASE_URL}")

# MySQL connector doesn't need check_same_thread, SQLite does
if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
    )
else:
    engine = create_engine(SQLALCHEMY_DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
