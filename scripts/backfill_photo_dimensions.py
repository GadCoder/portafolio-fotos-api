"""Read legacy dimensions from R2 or public originals; preview unless --apply is supplied."""
import argparse
import io
import os
import tempfile
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

from botocore.exceptions import ClientError

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


def r2_dimensions(key):
    options = {"Bucket": os.environ["s3_bucket_name"], "Key": key}
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


def object_keys(photo_url):
    path = unquote(urlparse(photo_url).path).lstrip("/")
    bucket_prefix = os.environ["s3_bucket_name"] + "/"
    candidates = [object_key(photo_url), path]
    if path.startswith(bucket_prefix):
        candidates.append(path[len(bucket_prefix):])
    # A public URL prefix can also be part of the actual object key.
    return list(dict.fromkeys(candidates))


def public_dimensions(photo_url):
    parsed = urlparse(photo_url)
    allowed_hosts = {"portfolio.cdn.gadcoder.com"}
    configured_host = urlparse(os.getenv("s3_url", "")).hostname
    if configured_host:
        allowed_hosts.add(configured_host)
    if (parsed.scheme != "https" or parsed.hostname not in allowed_hosts
            or parsed.username is not None or parsed.password is not None
            or parsed.port not in (None, 443)):
        raise ValueError("Public original must use the configured HTTPS image host")
    # Use the exact original URL, including its legacy prefix and extension.
    request = Request(photo_url, headers={"User-Agent": "PortfolioPhotoMetadata/1.0"})
    with urlopen(request, timeout=30) as response:
        if int(response.headers.get("Content-Length", "0")) > MAX_BYTES:
            raise ValueError("Image exceeds 50 MB")
        with tempfile.SpooledTemporaryFile(max_size=1024 * 1024) as file:
            size = 0
            while chunk := response.read(64 * 1024):
                size += len(chunk)
                if size > MAX_BYTES:
                    raise ValueError("Image exceeds 50 MB")
                file.write(chunk)
            file.seek(0)
            return dimensions(file)


def stored_dimensions(photo_url):
    for key in object_keys(photo_url):
        try:
            return r2_dimensions(key)
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") not in {"NoSuchKey", "NotFound", "404"}:
                raise
    # Legacy URLs may point to public objects outside the currently configured bucket.
    # The frontend already uses these originals to resolve build-time dimensions.
    return public_dimensions(photo_url)


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
