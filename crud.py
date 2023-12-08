import os
import boto3
import shutil
from PIL import Image, ImageOps
from tempfile import NamedTemporaryFile
from dotenv import load_dotenv
import requests
from typing import List
from botocore.exceptions import NoCredentialsError
from sqlalchemy.orm import Session
from fastapi import File, HTTPException, UploadFile
from io import BytesIO

import models

load_dotenv()


def get_photo(db: Session, photo_id: int):
    return db.query(models.Photo).filter(models.Photo.id == photo_id).first()


def get_all_photos(db: Session):
    return db.query(models.Photo).all()


def create_s3_client():
    aws_access_key_id = os.getenv('s3_key')
    aws_secret_access_key = os.getenv('s3_secret_key')
    cloudflare_endpoint = os.getenv('s3_endpoint')

    s3 = boto3.client('s3', aws_access_key_id=aws_access_key_id,
                      aws_secret_access_key=aws_secret_access_key,
                      endpoint_url=cloudflare_endpoint)
    return s3


def save_photo_on_bucket(local_file_path, filename):
    s3 = create_s3_client()
    bucket_name = os.getenv('s3_bucket_name')
    s3_url = os.getenv('s3_url')

    try:
        s3.upload_file(local_file_path, bucket_name, filename)
        print("Upload Successful")
        s3_url = f"{s3_url}/{bucket_name}/{filename}"
        return s3_url
    except FileNotFoundError:
        print("The file was not found")
        return None
    except NoCredentialsError:
        print("Credentials not available")
        return None


def photo_is_horizontal(image: UploadFile):
    try:
        with Image.open(image) as img:
            pil = ImageOps.exif_transpose(img)
            width, height = pil.size
            print(f"Witdh: {width}")
            print(f"Height: {height}")
            return width > height
    except Exception as e:
        print(f"Error: {e}")
        return None


def add_photo_to_db(db: Session, photo_url: str, photo_name: str, photo_orientation: bool):
    db_photo = models.Photo(
        is_horizontal=photo_orientation, photo_url=photo_url, name=photo_name)
    db.add(db_photo)
    db.commit()
    db.refresh(db_photo)
    return db_photo


def convert_to_webp(input_path, output_path):
    try:
        # Open the input image
        with Image.open(input_path) as img:
            img = ImageOps.exif_transpose(img)
            # Save as WebP
            img.save(output_path, 'WEBP')
        print(f'Conversion successful. WebP image saved at: {output_path}')
    except Exception as e:
        print(f'Error converting image: {e}')


def get_webp_file_name(filename: str):
    return os.path.splitext(filename)[0] + '.webp'


def upload_photos(db: Session, files: List[UploadFile] = File(...)):
    db_files = []
    for file in files:
        with NamedTemporaryFile(delete=False) as temp_file:
            shutil.copyfileobj(file.file, temp_file)
            local_file_path = temp_file.name
            local_webp_path = get_webp_file_name(temp_file.name)
            photo_orientation = photo_is_horizontal(image=local_file_path)
            convert_to_webp(local_file_path, local_webp_path)
            webp_name = get_webp_file_name(file.filename)
            photo_url = save_photo_on_bucket(local_webp_path, webp_name)
            os.remove(local_file_path)
            os.remove(local_webp_path)
            if photo_url is None:
                raise HTTPException(
                    status_code=500, detail=f"Problem uploading file {file.filename}")
            db_photo = add_photo_to_db(
                db=db, photo_url=photo_url, photo_orientation=photo_orientation, photo_name=webp_name)
            db_files.append(db_photo)
    return db_files


def delete_from_s3(filename: str):
    s3 = create_s3_client()
    bucket_name = os.getenv('s3_bucket_name')
    try:
        # Delete the file
        s3.delete_object(Bucket=bucket_name, Key=filename)
        print(f"File deleted successfully: {filename}")
    except Exception as e:
        print(f"Error deleting file: {e}")


def delete_photo_from_db(db: Session, photo_id: int):
    photo_db = get_photo(db=db, photo_id=photo_id)
    if not photo_db:
        raise HTTPException(
            status_code=404, detail=f"Photo with id {photo_id} not founded")
    delete_from_s3(filename=photo_db.name)
    db.delete(photo_db)
    db.commit()
    return {
        "status": f"Photo  with id {photo_id} deleted"
    }


def authenticate_user(user: str, password: str):
    registered_user = os.getenv("user")
    registered_password = os.getenv("password")
    valid_credentials = user == registered_user and password == registered_password
    return valid_credentials



def get_photo_in_storage(photo_url: str):
    response = requests.get(photo_url)
    response.raise_for_status()  # Check if the request was successful
    img = Image.open(BytesIO(response.content))
    return img



def rotate_photo(photo: models.Photo):
    try:
        photo_file = get_photo_in_storage(photo_url=photo.photo_url)
        rotated_img = photo_file.rotate(90, expand=True)
        rotated_img.save(photo.name)
        delete_from_s3(photo.name)
        save_photo_on_bucket(photo.name, photo.name)
        os.remove(photo.name)
        return True
    except Exception as e:
        print(f'Error rotating image: {e}')
        return False


def fix_photos_orientation(db: Session):
    photos = get_all_photos(db=db)
    rotated_photos = []
    for photo in photos:
        saved_photo = get_photo_in_storage(photo.photo_url)
        saved_photo_width, saved_photo_height = saved_photo.size
        photo_is_rotated = saved_photo_width > saved_photo_height and not photo.is_horizontal
        if photo_is_rotated:
            if rotate_photo(photo):
                rotated_photos.append(photo)
            else:
                raise HTTPException(status_code=501, detail=f"Error rotating photo {photo.name}")


