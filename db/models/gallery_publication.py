from sqlalchemy import Column, DateTime, Integer

from db.session import Base


class GalleryPublication(Base):
    __tablename__ = "gallery_publication"

    id = Column(Integer, primary_key=True)
    revision = Column(Integer, nullable=False, default=0)
    requested_revision = Column(Integer, nullable=False, default=0)
    changed_at = Column(DateTime(timezone=True), nullable=False)
