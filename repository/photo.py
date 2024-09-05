import io
import os
import piexif
from typing import BinaryIO

from dotenv import load_dotenv
from PIL import Image, ImageOps

from fastapi import HTTPException
from sqlalchemy.orm import Session

from db.models.photo import Photo
from repository.s3_bucket import save_photo_on_bucket, delete_from_s3


load_dotenv()


def get_photo(db: Session, photo_id: int):
    return db.query(Photo).filter(Photo.id == photo_id).first()


def get_all_photos(db: Session):
    return db.query(Photo).all()


def add_photo_to_db(
    db: Session, photo_url: str, photo_name: str, photo_orientation: bool
):
    db_photo = Photo(
        is_horizontal=photo_orientation, photo_url=photo_url, name=photo_name
    )
    db.add(db_photo)
    db.commit()
    db.refresh(db_photo)


def get_webp_file_name(filename: str):
    return os.path.splitext(filename)[0] + ".webp"


def get_exif_orientation(img: Image):
    try:
        exif_data = img.info.get("exif")
        if exif_data:
            exif_dict = piexif.load(exif_data)
            orientation = exif_dict.get("0th", {}).get(
                piexif.ImageIFD.Orientation, None
            )
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
        print(f"Error rotating image: {e}")
        return None


def get_new_exif_info(img: Image):
    exif_dict = piexif.load(img.info["exif"])
    exif_dict["0th"][piexif.ImageIFD.Orientation] = 1
    new_exif_bytes = piexif.dump(exif_dict)
    return new_exif_bytes


def convert_to_webp(file_data: io.BytesIO, is_horizontal: bool):
    try:
        with Image.open(file_data) as img:
            exit_orientation = get_exif_orientation(img)
            image_needs_rotation = exit_orientation == 8 and not is_horizontal
            webp_stream = io.BytesIO()
            if image_needs_rotation:
                rotated_image = rotate_photo(img=img)
                new_exif_info = get_new_exif_info(img=rotated_image)
                rotated_image.save(
                    webp_stream, "WEBP", optimize=True, quality=85, exif=new_exif_info
                )
            else:
                img.save(webp_stream, "WEBP", optimize=True, quality=85)
            webp_stream.seek(0)
            return webp_stream
    except Exception as e:
        print(f"Error converting image: {e}")


def check_if_file_is_webp(filename: str):
    return filename.endswith(".webp")


def photo_is_horizontal(file_data: io.BytesIO) -> bool:
    try:
        with Image.open(file_data) as img:
            pil = ImageOps.exif_transpose(img)
            width, height = pil.size
            return width > height
    except Exception as e:
        print(f"Error: {e}")
        return None


def process_photo(file_data: io.BytesIO, filename: str):
    photo_orientation = photo_is_horizontal(file_data=file_data)
    if check_if_file_is_webp(filename=filename):
        photo_url = save_photo_on_bucket(file_data=file_data, filename=filename)
        return photo_url, photo_orientation, filename
    file_webp_name = get_webp_file_name(filename=filename)
    webp_file = convert_to_webp(file_data=file_data, is_horizontal=photo_orientation)
    photo_url = save_photo_on_bucket(file_data=webp_file, filename=filename)
    return photo_url, photo_orientation, file_webp_name


def upload_photo(db: Session, file: BinaryIO, filename: str):
    try:
        binary_stream = io.BytesIO(file)
        photo_url, photo_orientation, webp_name = process_photo(
            file_data=binary_stream, filename=filename
        )
        if photo_url is None:
            raise HTTPException(
                status_code=500, detail=f"Problem uploading file {filename}"
            )
        add_photo_to_db(
            db=db,
            photo_url=photo_url,
            photo_orientation=photo_orientation,
            photo_name=webp_name,
        )
    except Exception as e:
        print(f"Error uploading file {filename} {e}")
        raise HTTPException(
            status_code=500, detail=f"Problem uploading file {filename}"
        )


def delete_photo_from_db(db: Session, photo_id: int):
    photo_db = get_photo(db=db, photo_id=photo_id)
    if not photo_db:
        raise HTTPException(
            status_code=404, detail=f"Photo with id {photo_id} not founded"
        )
    delete_from_s3(filename=photo_db.name)
    db.delete(photo_db)
    db.commit()
    return {"status": f"Photo  with id {photo_id} deleted"}
