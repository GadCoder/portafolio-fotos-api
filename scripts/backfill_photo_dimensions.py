"""Read legacy dimensions from object storage; preview unless --apply is supplied."""
import argparse
import io
import os
import tempfile
from urllib.parse import unquote, urlparse

from PIL import Image
from sqlalchemy import or_

from db.models.photo import Photo
from db.session import SessionLocal
from repository.gallery_publication import queue_gallery_publication
from repository.s3_bucket import s3_client

MAX_BYTES = 50 * 1024 * 1024
HEADER_BYTES = 256 * 1024


def object_key(photo_url):
    path = unquote(urlparse(photo_url).path).lstrip("/")
    base = unquote(urlparse(os.getenv("s3_url", "")).path).strip("/")
    bucket = os.environ["s3_bucket_name"]
    for prefix in (base, bucket):
        if prefix and path.startswith(prefix + "/"):
            return path[len(prefix) + 1:]
    return path


def dimensions(file):
    with Image.open(file) as image:
        width, height = image.size
        if image.getexif().get(274, 1) in (5, 6, 7, 8):
            width, height = height, width
        if width <= 0 or height <= 0:
            raise ValueError("Invalid dimensions")
        return width, height


def stored_dimensions(photo_url):
    options = {"Bucket": os.environ["s3_bucket_name"], "Key": object_key(photo_url)}
    response = s3_client.get_object(**options, Range=f"bytes=0-{HEADER_BYTES - 1}")
    try:
        header = response["Body"].read(HEADER_BYTES)
    finally:
        response["Body"].close()
    try:
        return dimensions(io.BytesIO(header))
    except (OSError, ValueError):
        # WebP and some other formats require the complete file to inspect metadata.
        response = s3_client.get_object(**options)
        body = response["Body"]
        try:
            if response.get("ContentLength", 0) > MAX_BYTES:
                raise ValueError("Image exceeds 50 MB")
            with tempfile.SpooledTemporaryFile(max_size=1024 * 1024) as file:
                size = 0
                for chunk in body.iter_chunks(64 * 1024):
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise ValueError("Image exceeds 50 MB")
                    file.write(chunk)
                file.seek(0)
                return dimensions(file)
        finally:
            body.close()


def backfill(*, apply=False):
    failures = 0
    updated = 0
    with SessionLocal() as db:
        photos = db.query(Photo).filter(or_(
            Photo.width.is_(None), Photo.height.is_(None), Photo.width <= 0, Photo.height <= 0,
        )).order_by(Photo.id).all()
        for photo in photos:
            try:
                width, height = stored_dimensions(photo.photo_url)
            except Exception as error:
                failures += 1
                print(f"Photo {photo.id}: could not read dimensions ({type(error).__name__})", flush=True)
                continue
            print(f"Photo {photo.id}: {width} × {height}", flush=True)
            if apply:
                photo.width, photo.height = width, height
                photo.is_horizontal = width > height
            updated += 1
        if apply and updated:
            queue_gallery_publication(db)
            db.commit()
    print(f"{'Updated' if apply else 'Would update'} {updated}; failed {failures}.")
    return 1 if failures else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Save dimensions and queue a portfolio rebuild")
    args = parser.parse_args()
    raise SystemExit(backfill(apply=args.apply))
