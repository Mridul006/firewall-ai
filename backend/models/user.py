"""User and auth token models."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr
from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.db import Base


class User(Base):
    """SQLAlchemy ORM model for the users table."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(30), default="analyst", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default="now()"
    )


class UserCreate(BaseModel):
    """Request body for registering a new user."""

    email: EmailStr
    password: str


class UserResponse(BaseModel):
    """Response body representing a user, without the password hash."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    role: str
    created_at: datetime


class LoginRequest(BaseModel):
    """Request body for logging in with email and password."""

    email: EmailStr
    password: str


class Token(BaseModel):
    """Response body for a successful login — the JWT bearer token."""

    access_token: str
    token_type: str = "bearer"
