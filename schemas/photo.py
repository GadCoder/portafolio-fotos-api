from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PhotoPresentation(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    featured: bool = False
    featured_layout: Literal["wide", "contained"] | None = Field(None, alias="featuredLayout")
    title: str | None = Field(None, max_length=255)
    location: str | None = Field(None, max_length=255)
    series_slug: str | None = Field(None, alias="seriesSlug", max_length=255)


class PhotoPresentationUpdate(PhotoPresentation):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", str_strip_whitespace=True)


class PhotoBase(PhotoPresentation):
    is_horizontal: bool
    photo_url: str
    name: str
    width: int | None = None
    height: int | None = None
    series_id: int | None = Field(None, alias="seriesId")
    series_position: int | None = Field(None, alias="seriesPosition")
    show_in_preview: bool = Field(False, alias="showInPreview")
    preview_position: int | None = Field(None, alias="previewPosition")


class Photo(PhotoBase):
    id: int
    created_at: datetime
