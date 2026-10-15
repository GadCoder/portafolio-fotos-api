import logging
import os
import re
import tempfile
import uuid
import warnings
from typing import BinaryIO
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv
from PIL import Image, ImageOps, UnidentifiedImageError

from fastapi import HTTPException
from sqlalchemy.orm import Session

from db.models.photo import Photo
from db.session import SessionLocal
from repository.s3_bucket import save_photo_on_bucket, delete_from_s3
from repository.gallery_publication import queue_gallery_publication


load_dotenv()
logger = logging.getLogger(__name__)

SUPPORTED_IMAGE_FORMATS = ("JPEG", "PNG", "WEBP")
MAX_IMAGE_PIXEL_COUNT = int(os.getenv("IMAGE_MAX_PIXELS", "80000000"))
if MAX_IMAGE_PIXEL_COUNT < 1:
    raise RuntimeError("IMAGE_MAX_PIXELS must be a positive integer")
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXEL_COUNT


def get_photo(db: Session, photo_id: int):
    return db.query(Photo).filter(Photo.id == photo_id).first()


def get_all_photos(db: Session):
    return db.query(Photo).order_by(Photo.created_at.desc(), Photo.id.desc()).all()


def get_photo_page(db: Session, page: int, page_size: int):
    total = db.query(Photo).count()
    photos = (
        db.query(Photo)
        .order_by(Photo.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return photos, total


def add_photo_to_db(
    db: Session, photo_url: str, photo_name: str, photo_orientation: bool,
    width: int | None = None, height: int | None = None,
):
    db_photo = Photo(
        is_horizontal=photo_orientation, photo_url=photo_url, name=photo_name,
        width=width, height=height,
    )
    db.add(db_photo)
    queue_gallery_publication(db)
    db.commit()
    db.refresh(db_photo)


def get_webp_file_name(filename: str):
    original_stem = os.path.splitext(os.path.basename(filename))[0]
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "-", original_stem).strip(".-")
    safe_stem = (safe_stem or "photo")[:100]
    return f"{uuid.uuid4().hex}-{safe_stem}.webp"


def convert_to_webp(file_data: BinaryIO):
    """Validate and normalize one image, returning a spooled WebP and orientation."""
    file_data.seek(0)
    normalized_image = None
    output = None
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        try:
            with Image.open(file_data, formats=SUPPORTED_IMAGE_FORMATS) as image:
                image.verify()

            file_data.seek(0)
            with Image.open(file_data, formats=SUPPORTED_IMAGE_FORMATS) as image:
                if getattr(image, "n_frames", 1) != 1:
                    raise ValueError("Animated and multi-frame images are not supported")
                width, height = image.size
                if width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXEL_COUNT:
                    raise ValueError("Image dimensions exceed the supported limit")
                image.load()
                icc_profile = image.info.get("icc_profile")
                ImageOps.exif_transpose(image, in_place=True)
                photo_orientation = image.width > image.height
                has_alpha = "A" in image.getbands() or "transparency" in image.info
                if image.mode in ("RGB", "RGBA"):
                    normalized_image = image
                else:
                    normalized_image = image.convert("RGBA" if has_alpha else "RGB")

                output = tempfile.SpooledTemporaryFile(
                    max_size=8 * 1024 * 1024, mode="w+b"
                )
                save_options = {"quality": 85, "method": 6}
                if icc_profile and icc_profile[16:20] == b"RGB ":
                    save_options["icc_profile"] = icc_profile
                normalized_image.save(output, format="WEBP", **save_options)
            output.seek(0)
            result = output
            output = None
            return result, photo_orientation, normalized_image.width, normalized_image.height
        except (
            UnidentifiedImageError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
            OSError,
            ValueError,
        ) as exc:
            raise HTTPException(status_code=400, detail=f"Invalid or unsupported image: {exc}") from exc
        finally:
            if normalized_image is not None:
                normalized_image.close()
            if output is not None:
                output.close()


def upload_photo(file: BinaryIO, filename: str):
    stored_name = get_webp_file_name(filename)
    uploaded_to_bucket = False
    try:
        webp_file, photo_orientation, width, height = convert_to_webp(file_data=file)
        try:
            photo_url = save_photo_on_bucket(file_data=webp_file, filename=stored_name)
        finally:
            webp_file.close()
        if photo_url is None:
            raise HTTPException(
                status_code=500, detail=f"Problem uploading file {filename}"
            )
        uploaded_to_bucket = True
        with SessionLocal() as db:
            add_photo_to_db(
                db=db,
                photo_url=photo_url,
                photo_orientation=photo_orientation,
                photo_name=os.path.basename(filename)[:255],
                width=width,
                height=height,
            )
        return stored_name
    except HTTPException:
        if uploaded_to_bucket:
            delete_from_s3(filename=stored_name)
        raise
    except Exception as e:
        logger.exception(
            "Photo upload failed", extra={"photo_filename": filename}
        )
        if uploaded_to_bucket:
            delete_from_s3(filename=stored_name)
        raise HTTPException(
            status_code=500, detail=f"Problem uploading file {filename}"
        )


def update_photo_presentation(db: Session, photo_id: int, changes: dict):
    photo = get_photo(db, photo_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="Photo not found")
    for field, value in changes.items():
        setattr(photo, field, value)
    queue_gallery_publication(db)
    db.commit()
    db.refresh(photo)
    return photo


def delete_photo_from_db(db: Session, photo_id: int):
    photo_db = get_photo(db=db, photo_id=photo_id)
    if not photo_db:
        raise HTTPException(
            status_code=404, detail=f"Photo with id {photo_id} not founded"
        )
    bucket_name = os.getenv("s3_bucket_name", "")
    object_path = unquote(urlparse(photo_db.photo_url).path).lstrip("/")
    bucket_prefix = f"{bucket_name}/" if bucket_name else ""
    object_key = (
        object_path[len(bucket_prefix) :]
        if bucket_prefix and object_path.startswith(bucket_prefix)
        else photo_db.name
    )
    delete_from_s3(filename=object_key)
    db.delete(photo_db)
    queue_gallery_publication(db)
    db.commit()
    return {"status": f"Photo  with id {photo_id} deleted"}
