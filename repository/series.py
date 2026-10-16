import re

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db.models.photo import Photo
from db.models.series import Series
from repository.gallery_publication import queue_gallery_publication
from schemas.photo import Photo as PhotoSchema


def ordered_photos(db: Session, series_id: int):
    return (db.query(Photo).filter(Photo.series_id == series_id)
            .order_by(Photo.series_position.asc().nullslast(), Photo.id.asc()).all())


def validate_published_series(db: Session, series: Series, *, photos=None):
    if not series.published:
        return
    photos = photos if photos is not None else ordered_photos(db, series.id)
    if len(photos) > 5:
        preview_count = sum(bool(photo.show_in_preview) for photo in photos)
        if not 1 <= preview_count <= 6:
            raise HTTPException(422, "A published series with more than five photos needs between one and six preview photos")


def _photo_data(photo):
    return PhotoSchema.model_validate(photo).model_dump(by_alias=True)


def _as_dict(db: Session, series: Series, *, admin=False):
    photos = ordered_photos(db, series.id)
    if series.published:
        validate_published_series(db, series, photos=photos)
    preview = sorted((p for p in photos if p.show_in_preview), key=lambda p: (p.preview_position is None, p.preview_position or 0, p.id))
    if len(photos) <= 5:
        preview = photos
    data = {
        "id": series.id, "slug": series.slug, "title": series.title,
        "description": series.description, "year": series.year, "position": series.position,
        "totalPhotos": len(photos), "previewPhotos": [_photo_data(p) for p in preview],
        "photos": [_photo_data(p) for p in photos],
    }
    if admin:
        data["published"] = series.published
    return data


def list_series(db: Session, *, admin=False):
    query = db.query(Series)
    if not admin:
        query = query.filter(Series.published.is_(True))
    return [_as_dict(db, s, admin=admin) for s in query.order_by(Series.position, Series.id).all()]


def get_series(db: Session, slug: str):
    series = db.query(Series).filter(Series.slug == slug, Series.published.is_(True)).first()
    if not series:
        raise HTTPException(404, "Series not found")
    return _as_dict(db, series)


def create_series(db: Session, values: dict):
    values = dict(values)
    if values.get("position") is None:
        max_position = db.query(func.max(Series.position)).scalar()
        values["position"] = (max_position if max_position is not None else -1) + 1
    _validate_slug(values["slug"])
    if db.query(Series).filter(Series.slug == values["slug"]).first():
        raise HTTPException(409, "Series slug already exists")
    series = Series(**values)
    db.add(series)
    try:
        db.flush()
        validate_published_series(db, series)
        queue_gallery_publication(db)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Series slug already exists") from exc
    db.refresh(series)
    return _as_dict(db, series, admin=True)


def update_series(db: Session, series_id: int, changes: dict):
    series = db.query(Series).filter(Series.id == series_id).with_for_update().first()
    if not series:
        raise HTTPException(404, "Series not found")
    if "slug" in changes:
        _validate_slug(changes["slug"])
        duplicate = db.query(Series).filter(Series.slug == changes["slug"], Series.id != series_id).first()
        if duplicate:
            raise HTTPException(409, "Series slug already exists")
    for key, value in changes.items():
        setattr(series, key, value)
    validate_published_series(db, series)
    # Keep the compatibility slug synchronized for every current member.
    db.query(Photo).filter(Photo.series_id == series_id).update({Photo.series_slug: series.slug}, synchronize_session=False)
    queue_gallery_publication(db)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Series slug already exists") from exc
    db.refresh(series)
    return _as_dict(db, series, admin=True)


def delete_series(db: Session, series_id: int):
    series = db.query(Series).filter(Series.id == series_id).with_for_update().first()
    if not series:
        raise HTTPException(404, "Series not found")
    db.query(Photo).filter(Photo.series_id == series_id).update({
        Photo.series_id: None, Photo.series_position: None, Photo.show_in_preview: False,
        Photo.preview_position: None, Photo.series_slug: None,
    }, synchronize_session=False)
    db.delete(series)
    queue_gallery_publication(db)
    db.commit()
    return {"status": "deleted"}


def reorder_series(db: Session, ids: list[int]):
    locked_series = db.query(Series).order_by(Series.id).with_for_update().all()
    all_ids = [series.id for series in locked_series]
    if len(ids) != len(set(ids)) or set(ids) != set(all_ids):
        raise HTTPException(422, "seriesIds must contain every series ID exactly once")
    for position, series_id in enumerate(ids):
        db.query(Series).filter(Series.id == series_id).update({Series.position: position}, synchronize_session=False)
    queue_gallery_publication(db)
    db.commit()
    return list_series(db, admin=True)


def replace_members(db: Session, series_id: int, photo_ids: list[int]):
    series = db.query(Series).filter(Series.id == series_id).with_for_update().first()
    if not series:
        raise HTTPException(404, "Series not found")
    if len(photo_ids) != len(set(photo_ids)):
        raise HTTPException(422, "photoIds must not contain duplicates")
    photos = db.query(Photo).filter(Photo.id.in_(photo_ids)).order_by(Photo.id).with_for_update().all() if photo_ids else []
    by_id = {p.id: p for p in photos}
    if set(by_id) != set(photo_ids):
        raise HTTPException(404, "One or more photos were not found")
    if any(p.series_id not in (None, series_id) for p in photos):
        raise HTTPException(409, "A photo is already assigned to another series")
    current = ordered_photos(db, series_id)
    retained = set(photo_ids)
    for photo in current:
        if photo.id not in retained:
            photo.series_id = None
            photo.series_slug = None
            photo.series_position = None
            photo.show_in_preview = False
            photo.preview_position = None
    for position, photo_id in enumerate(photo_ids):
        p = by_id[photo_id]
        p.series_id = series_id
        p.series_slug = series.slug
        p.series_position = position
        if p.id not in {x.id for x in current}:
            p.show_in_preview = False
            p.preview_position = None
    new_photos = [by_id[i] for i in photo_ids]
    validate_published_series(db, series, photos=new_photos)
    queue_gallery_publication(db)
    db.commit()
    return _as_dict(db, series, admin=True)


def replace_preview(db: Session, series_id: int, photo_ids: list[int]):
    series = db.query(Series).filter(Series.id == series_id).with_for_update().first()
    if not series:
        raise HTTPException(404, "Series not found")
    if len(photo_ids) > 6 or len(photo_ids) != len(set(photo_ids)):
        raise HTTPException(422, "Preview must contain at most six unique photo IDs")
    photos = {p.id: p for p in ordered_photos(db, series_id)}
    if any(pid not in photos for pid in photo_ids):
        raise HTTPException(422, "Preview photos must belong to this series")
    for p in photos.values():
        p.show_in_preview = p.id in photo_ids
        p.preview_position = photo_ids.index(p.id) if p.id in photo_ids else None
    validate_published_series(db, series)
    queue_gallery_publication(db)
    db.commit()
    return _as_dict(db, series, admin=True)


def sync_legacy_series_slug(db: Session, photo: Photo, slug: str | None):
    if slug is None:
        old_series = db.query(Series).filter(Series.id == photo.series_id).with_for_update().first() if photo.series_id is not None else None
        photo.series_id = None
        photo.series_slug = None
        photo.series_position = None
        photo.show_in_preview = False
        photo.preview_position = None
        db.flush()
        if old_series:
            validate_published_series(db, old_series)
        return
    series = db.query(Series).filter(Series.slug == slug).with_for_update().first()
    if series is None:
        raise HTTPException(422, "seriesSlug must reference an existing series")
    if photo.series_id not in (None, series.id):
        raise HTTPException(409, "Photo is already assigned to another series")
    photo.series_id = series.id
    photo.series_slug = series.slug
    if photo.series_position is None:
        max_position = db.query(func.max(Photo.series_position)).filter(Photo.series_id == series.id).scalar()
        photo.series_position = (max_position if max_position is not None else -1) + 1
    db.flush()
    validate_published_series(db, series)


def validate_delete_photo(db: Session, photo: Photo):
    if photo.series_id is None:
        return
    series = db.query(Series).filter(Series.id == photo.series_id).with_for_update().first()
    if not series or not series.published:
        return
    remaining = ordered_photos(db, series.id)
    remaining = [p for p in remaining if p.id != photo.id]
    validate_published_series(db, series, photos=remaining)


def _validate_slug(slug):
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug or ""):
        raise HTTPException(422, "Slug must be lowercase URL-safe text")
