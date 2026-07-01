from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database.connection import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(100), nullable=True)
    business_name = Column(String(150), nullable=True)
    business_type = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    images = relationship("Image", back_populates="user")
    advertisements = relationship("Advertisement", back_populates="user")
    histories = relationship("History", back_populates="user")


class Image(Base):
    __tablename__ = "images"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    image_type = Column(String(50), nullable=False)
    original_filename = Column(String(255), nullable=True)
    stored_filename = Column(String(255), nullable=True)
    file_path = Column(String(500), nullable=True)
    image_url = Column(String(500), nullable=True)
    content_type = Column(String(100), nullable=True)
    file_size = Column(Integer, nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    user = relationship("User", back_populates="images")
    input_advertisements = relationship(
        "Advertisement",
        back_populates="input_image",
        foreign_keys="Advertisement.input_image_id",
    )
    output_advertisements = relationship(
        "Advertisement",
        back_populates="output_image",
        foreign_keys="Advertisement.output_image_id",
    )


class Advertisement(Base):
    __tablename__ = "advertisements"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    input_image_id = Column(Integer, ForeignKey("images.id"), nullable=True)
    output_image_id = Column(Integer, ForeignKey("images.id"), nullable=True)
    title = Column(String(255), nullable=True)
    ad_type = Column(String(50), nullable=False)
    prompt = Column(Text, nullable=False)
    generated_text = Column(Text, nullable=True)
    style = Column(String(100), nullable=True)
    tone = Column(String(100), nullable=True)
    target_audience = Column(String(150), nullable=True)
    status = Column(String(50), default="pending", nullable=False)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    user = relationship("User", back_populates="advertisements")
    input_image = relationship(
        "Image",
        back_populates="input_advertisements",
        foreign_keys=[input_image_id],
    )
    output_image = relationship(
        "Image",
        back_populates="output_advertisements",
        foreign_keys=[output_image_id],
    )
    histories = relationship("History", back_populates="advertisement")


class History(Base):
    __tablename__ = "histories"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    advertisement_id = Column(
        Integer,
        ForeignKey("advertisements.id"),
        nullable=True,
        index=True,
    )
    action_type = Column(String(80), nullable=False)
    request_data = Column(Text, nullable=True)
    response_data = Column(Text, nullable=True)
    status = Column(String(50), nullable=False)
    error_message = Column(Text, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    user = relationship("User", back_populates="histories")
    advertisement = relationship("Advertisement", back_populates="histories")
