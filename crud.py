import os
import boto3
import shutil
import piexif
from PIL import Image, ImageOps
from tempfile import NamedTemporaryFile
from dotenv import load_dotenv
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



def get_webp_file_name(filename: str):
    return os.path.splitext(filename)[0] + '.webp'


def get_exif_orientation(img: Image):
    try:
        exif_data = img.info.get('exif')
        if exif_data:
            exif_dict = piexif.load(exif_data)
            orientation = exif_dict.get("0th", {}).get(piexif.ImageIFD.Orientation, None)
            print(f"Orientation: {orientation}")
            return orientation
        else:
            print("No EXIF data found in the image.")
            return None
    except Exception as e:
        print(f"Error getting EXIF orientation: {e}")
        return None
    

def rotate_photo(img: Image):
    try:
        rotated_img = img.rotate(90, expand=True)
        return rotated_img
    except Exception as e:
        print(f'Error rotating image: {e}')
        return None


def convert_to_webp(input_path, output_path, is_horizontal):
    try:
        with Image.open(input_path) as img:
            exit_orientation = get_exif_orientation(img)
            image_rotated = False
            if exit_orientation == 8 and not is_horizontal:
                print("ROTATING")
                image_rotated = True
                img = rotate_photo(img=img)
            if image_rotated:
                exif_dict = piexif.load(img.info["exif"])
                exif_dict["0th"][piexif.ImageIFD.Orientation] = 1
                new_exif_bytes = piexif.dump(exif_dict)
                img.save(output_path, 'WEBP', exif=new_exif_bytes)
            else:
                img.save(output_path, 'WEBP')
        print(f'Conversion successful. WebP image saved at: {output_path}')
    except Exception as e:
        print(f'Error converting image: {e}')


def upload_photos(db: Session, files: List[UploadFile] = File(...)):
    db_files = []
    for file in files:
        try:
            with NamedTemporaryFile(delete=False) as temp_file:
                shutil.copyfileobj(file.file, temp_file)
                local_file_path = temp_file.name
                local_webp_path = get_webp_file_name(temp_file.name)
                photo_orientation = photo_is_horizontal(image=local_file_path)
                convert_to_webp(local_file_path, local_webp_path, is_horizontal=photo_orientation)
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
        except Exception as e:
            print(f'Error uploading file {file.filename} {e}')
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

