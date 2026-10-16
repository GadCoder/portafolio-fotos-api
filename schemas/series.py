from pydantic import BaseModel, ConfigDict, Field
from schemas.photo import Photo


class SeriesMetadata(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", str_strip_whitespace=True)
    slug: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    year: int | None = Field(None, ge=1800, le=2200)
    position: int | None = Field(None, ge=0)
    published: bool = False


class SeriesUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", str_strip_whitespace=True)
    slug: str | None = Field(None, min_length=1, max_length=100, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    title: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    year: int | None = Field(None, ge=1800, le=2200)
    position: int | None = Field(None, ge=0)
    published: bool | None = None


class PhotoIds(BaseModel):
    photo_ids: list[int] = Field(alias="photoIds")


class SeriesOrder(BaseModel):
    series_ids: list[int] = Field(alias="seriesIds")


class SeriesRead(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)
    id: int
    slug: str
    title: str
    description: str | None
    year: int | None
    position: int
    total_photos: int = Field(alias="totalPhotos")
    preview_photos: list[Photo] = Field(alias="previewPhotos")
    photos: list[Photo]


class AdminSeriesRead(SeriesRead):
    published: bool
