import logging
import os
from typing import BinaryIO

import boto3
from botocore.exceptions import NoCredentialsError

from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


def create_s3_client():
    aws_access_key_id = os.getenv("s3_key")
    aws_secret_access_key = os.getenv("s3_secret_key")
    cloudflare_endpoint = os.getenv("s3_endpoint")
    s3_client = boto3.client(
        "s3",
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        endpoint_url=cloudflare_endpoint,
    )
    return s3_client


s3_client = create_s3_client()


def save_photo_on_bucket(file_data: BinaryIO, filename: str):
    bucket_name = os.getenv("s3_bucket_name")
    s3_url = os.getenv("s3_url")
    logger.info(
        "Uploading photo to object storage", extra={"object_key": filename}
    )
    try:
        file_data.seek(0)
        s3_client.upload_fileobj(
            file_data,
            bucket_name,
            filename,
            ExtraArgs={
                "ContentType": "image/webp",
                "CacheControl": "public, max-age=31536000, immutable",
            },
        )
        logger.info("Photo uploaded", extra={"object_key": filename})
        return f"{s3_url.rstrip('/')}/{filename}"
    except FileNotFoundError:
        logger.exception(
            "Photo file was unavailable", extra={"object_key": filename}
        )
        return None
    except NoCredentialsError:
        logger.exception("Object storage credentials are unavailable")
        return None


def delete_from_s3(filename: str):
    bucket_name = os.getenv("s3_bucket_name")
    try:
        s3_client.delete_object(Bucket=bucket_name, Key=filename)
        logger.info(
            "Photo deleted from object storage", extra={"object_key": filename}
        )
    except Exception:
        logger.exception(
            "Photo deletion from object storage failed",
            extra={"object_key": filename},
        )
