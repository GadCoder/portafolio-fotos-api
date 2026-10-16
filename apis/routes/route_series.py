from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db.session import get_db
from repository.series import get_series, list_series
from schemas.series import SeriesRead

router = APIRouter(tags=["series"])


@router.get("/series/", response_model=list[SeriesRead])
def public_series(db: Session = Depends(get_db)):
    return list_series(db)


@router.get("/series/{slug}/", response_model=SeriesRead)
def public_series_detail(slug: str, db: Session = Depends(get_db)):
    return get_series(db, slug)
