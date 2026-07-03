"""Authentication routes — register, login, and current-user lookup."""

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.db import get_db
from models.user import LoginRequest, Token, User, UserCreate, UserResponse

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    """Check a plaintext password against its bcrypt hash."""
    return bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("utf-8"))


def create_access_token(user_id: str) -> str:
    """Create a signed JWT for the given user id."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {"sub": user_id, "exp": expire}
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Resolve the bearer token into the authenticated user, or raise 401."""
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
    except jwt.InvalidTokenError as e:
        raise credentials_error from e

    user_id = payload.get("sub")
    if user_id is None:
        raise credentials_error

    try:
        result = await db.execute(select(User).where(User.id == user_id))
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Database error") from e

    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_error
    return user


@router.post(
    "/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED
)
async def register(body: UserCreate, db: AsyncSession = Depends(get_db)) -> User:
    """Create a new user account."""
    try:
        existing = await db.execute(select(User).where(User.email == body.email))
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(status_code=409, detail="Email already registered")

        user = User(email=body.email, hashed_password=hash_password(body.password))
        db.add(user)
        await db.commit()
        await db.refresh(user)
    except SQLAlchemyError as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Database error") from e

    return user


@router.post("/login", response_model=Token)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)) -> Token:
    """Authenticate with email/password and return a JWT bearer token."""
    try:
        result = await db.execute(select(User).where(User.email == body.email))
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Database error") from e

    user = result.scalar_one_or_none()
    if user is None or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    return Token(access_token=create_access_token(str(user.id)))


@router.get("/me", response_model=UserResponse)
async def read_current_user(current_user: User = Depends(get_current_user)) -> User:
    """Return the authenticated user's profile."""
    return current_user
