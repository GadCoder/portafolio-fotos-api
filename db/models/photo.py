from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String

from db.session import Base


class Photo(Base):
    __tablename__ = "photos"

    id = Column(Integer, primary_key=True, index=True)
    is_horizontal = Column(Boolean)
    photo_url = Column(String(255))
    name = Column(String(255))
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    featured = Column(Boolean, nullable=False, default=False, server_default="false")
    featured_layout = Column(String(16), nullable=True)
    title = Column(String(255), nullable=True)
    location = Column(String(255), nullable=True)
    series_slug = Column(String(255), nullable=True)
    series_id = Column(Integer, ForeignKey("series.id", ondelete="SET NULL"), nullable=True, index=True)
    series_position = Column(Integer, nullable=True)
    show_in_preview = Column(Boolean, nullable=False, default=False, server_default="false")
    preview_position = Column(Integer, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
