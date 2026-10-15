import os
from fastapi import UploadFile

MAX_UPLOAD_SIZE = 50 * 1024 * 1024
MAX_UPLOAD_BATCH_SIZE = 90 * 1024 * 1024
MAX_UPLOAD_FILES = 20


def get_upload_filename(file: UploadFile) -> str:
    return os.path.basename((file.filename or "unnamed image").replace("\\", "/")) or "unnamed image"


def get_upload_size(file: UploadFile) -> int:
    if file.size is not None:
        return file.size
    file.file.seek(0, os.SEEK_END)
    size = file.file.tell()
    file.file.seek(0)
    return size
