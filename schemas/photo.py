from datetime import datetime

from pydantic import BaseModel


class PhotoBase(BaseModel):
    is_horizontal: bool
    photo_url: str
    name: str


class Photo(PhotoBase):
    id: int
    created_at: datetime

    class Config:
        orm_mode = True
