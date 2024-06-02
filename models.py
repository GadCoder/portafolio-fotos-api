from sqlalchemy import Boolean, Column, Integer, String

from database import Base


class Photo(Base):
    __tablename__ = "photos"

    id = Column(Integer, primary_key=True, index=True)
    is_horizontal = Column(Boolean)
    photo_url = Column(String(255))
    name = Column(String(255))
