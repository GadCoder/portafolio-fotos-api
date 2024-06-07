from pydantic import BaseModel


class PhotoBase(BaseModel):
    is_horizontal: bool
    photo_url: str
    name: str


class Photo(PhotoBase):
    id: int

    class Config:
        orm_mode = True
