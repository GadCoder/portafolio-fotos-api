import os
import shutil

import piexif
from PIL import Image, ImageOps
from dotenv import load_dotenv
from typing import BinaryIO

from fastapi import  HTTPException, UploadFile
from sqlalchemy.orm import Session

from db.models.photo import Photo

from repository.s3_bucket import save_photo_on_bucket, delete_from_s3


load_dotenv()


def get_photo(db: Session, photo_id: int):
    return db.query(Photo).filter(Photo.id == photo_id).first()


def get_all_photos(db: Session):
    return db.query(Photo).all()


def photo_is_horizontal(image: UploadFile):
    try:
        with Image.open(image) as img:
            pil = ImageOps.exif_transpose(img)
            width, height = pil.size
            return width > height
    except Exception as e:
        print(f"Error: {e}")
        return None


def add_photo_to_db(db: Session, photo_url: str, photo_name: str, photo_orientation: bool):
    db_photo = Photo(
        is_horizontal=photo_orientation, photo_url=photo_url, name=photo_name)
    db.add(db_photo)
    db.commit()
    db.refresh(db_photo)


def get_webp_file_name(filename: str):
    return os.path.splitext(filename)[0] + '.webp'


def get_exif_orientation(img: Image):
    try:
        exif_data = img.info.get('exif')
        if exif_data:
            exif_dict = piexif.load(exif_data)
            orientation = exif_dict.get("0th", {}).get(piexif.ImageIFD.Orientation, None)
            return orientation
        else:
            print("No EXIF data found in the image.")
            return None
    except Exception as e:
        print(f"Error getting EXIF orientation: {e}")
        return None
    

def rotate_photo(img: Image) -> Image:
    try:
        rotated_img = img.rotate(90, expand=True)
        return rotated_img
    except Exception as e:
        print(f'Error rotating image: {e}')
        return None



def get_new_exif_info(img: Image):
    exif_dict = piexif.load(img.info["exif"])
    exif_dict["0th"][piexif.ImageIFD.Orientation] = 1
    new_exif_bytes = piexif.dump(exif_dict)
    return new_exif_bytes


def convert_to_webp(input_path, output_path, is_horizontal):
    try:
        with Image.open(input_path) as img:
            exit_orientation = get_exif_orientation(img)
            image_needs_rotation = exit_orientation == 8 and not is_horizontal
            if image_needs_rotation:
                print("ROTATING")
                img = rotate_photo(img=img)
                new_exif_info = get_new_exif_info(img)
                img.save(output_path, 'WEBP', exif=new_exif_info)
            else:
                img.save(output_path, 'WEBP')
        print(f'Conversion successful. WebP image saved at: {output_path}')
    except Exception as e:
        print(f'Error converting image: {e}')


def save_photo_locally(filename: str, local_webp_path: str, local_file_path: str, photo_is_horizontal: bool):
    convert_to_webp(local_file_path, local_webp_path, is_horizontal=photo_is_horizontal)
    webp_name = get_webp_file_name(filename)
    return webp_name


def check_if_file_is_webp(filename: str):
    return filename.endswith('.webp')


def process_photo(file_path: str, filename: str):
    photo_orientation = photo_is_horizontal(image=file_path)
    if check_if_file_is_webp(filename=filename):
        photo_url = save_photo_on_bucket(local_file_path=file_path, filename=filename)
        return photo_url, photo_orientation, filename

    local_webp_path = get_webp_file_name(filename=file_path)
    photo_orientation = photo_is_horizontal(image=file_path)
    webp_name = save_photo_locally(filename, local_webp_path=local_webp_path,
                                    local_file_path= file_path,
                                    photo_is_horizontal=photo_orientation)
    photo_url = save_photo_on_bucket(local_webp_path, webp_name)
    photo_url = ""
    os.remove(local_webp_path)
    os.remove(file_path)
    return photo_url, photo_orientation, webp_name


def upload_photo(db: Session, file_data: BinaryIO, filename: str):
    try:
        file_path = f"files/{filename}"
        with open(file_path, 'w+b') as file:
            shutil.copyfileobj(file_data, file)
        photo_url, photo_orientation, webp_name = process_photo(file_path= file_path, filename=filename)
        if photo_url is None:
            raise HTTPException(
                status_code=500, detail=f"Problem uploading file {file.filename}")
        add_photo_to_db(db=db, 
                        photo_url=photo_url, 
                        photo_orientation=photo_orientation,
                        photo_name=webp_name)
    except Exception as e:
        print(f'Error uploading file {file.filename} {e}')
        raise HTTPException(
            status_code=500, detail=f"Problem uploading file {file.filename}")


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

