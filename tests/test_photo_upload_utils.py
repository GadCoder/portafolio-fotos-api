from io import BytesIO

from apis.photo_upload import get_upload_filename, get_upload_size


class FakeUpload:
    def __init__(self, filename: str, content: bytes):
        self.filename = filename
        self.file = BytesIO(content)
        self.size = None


def test_upload_helpers_normalize_filename_and_measure_without_consuming_file():
    upload = FakeUpload("../unsafe\\photo.jpg", b"image-data")

    assert get_upload_filename(upload) == "photo.jpg"
    assert get_upload_size(upload) == len(b"image-data")
    assert upload.file.tell() == 0
