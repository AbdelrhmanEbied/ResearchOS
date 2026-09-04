from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from passlib.hash import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.backend.auth.dependencies import get_current_user
from app.backend.auth.schemas import LoginRequest, SignupRequest, UserResponse
from app.backend.database.database import get_db
from app.backend.database.models import Session, User

router = APIRouter(prefix="/auth", tags=["Auth"])

SESSION_TTL_DAYS = 30


@router.post("/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def signup(body: SignupRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalars().first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    user = User(
        email=body.email,
        hashed_password=bcrypt.hash(body.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/login")
async def login(body: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalars().first()

    if user is None or not bcrypt.verify(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    session = Session(
        user_id=user.id,
        expires_at=datetime.now(UTC) + timedelta(days=SESSION_TTL_DAYS),
    )
    db.add(session)
    await db.commit()

    response.set_cookie(
        key="session_id",
        value=session.id,
        max_age=SESSION_TTL_DAYS * 24 * 3600,
        httponly=True,
        samesite="lax",
    )
    return {"message": "Logged in"}


@router.post("/logout")
async def logout(response: Response, session_id: str | None = Cookie(default=None, alias="session_id"), db: AsyncSession = Depends(get_db)):
    if session_id:
        result = await db.execute(select(Session).where(Session.id == session_id))
        session = result.scalars().first()
        if session:
            await db.delete(session)
            await db.commit()

    response.delete_cookie(key="session_id")
    return {"message": "Logged out"}


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)):
    return user
