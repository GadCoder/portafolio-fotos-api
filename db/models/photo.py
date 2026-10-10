from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String

from db.session import Base


class Photo(Base):
    __tablename__ = "photos"

    id = Column(Integer, primary_key=True, index=True)
    is_horizontal = Column(Boolean)
    photo_url = Column(String(255))
    name = Column(String(255))
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
