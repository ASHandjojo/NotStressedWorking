"""
auth.py — JWT authentication scaffold.

Provides:
  create_access_token()  — sign a JWT containing a user identity claim
  decode_access_token()  — verify and decode a JWT, raise 401 on failure
  get_current_user()     — FastAPI dependency for protected routes
  POST /auth/register    — create a new user account
  POST /auth/login       — exchange credentials for an access token

TODO (before any real deployment):
  1. Replace plaintext password storage/comparison with bcrypt via passlib:
         from passlib.context import CryptContext
         pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
         hashed = pwd_context.hash(plain_password)
         pwd_context.verify(plain_password, hashed_password)
  2. Add refresh token logic: issue a short-lived access token + long-lived
     refresh token; store refresh tokens in DB so they can be revoked on logout.
  3. Rate-limit the /auth/login endpoint to prevent brute force attacks.
  4. Restrict token scope — include roles/permissions in the JWT payload.
  5. Use HTTPS in production — JWTs are only as safe as the transport layer.
"""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from sqlmodel import Session, select

from .config import get_settings
from .database import get_session
from .models import User

settings = get_settings()
router = APIRouter(prefix="/auth", tags=["auth"])

# Tells FastAPI where clients should POST to get a token (used by OpenAPI UI)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


# ── Token helpers ──────────────────────────────────────────────────────────────

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Sign and return a JWT containing `data`. Expiry defaults to settings value."""
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    to_encode["exp"] = expire
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def decode_access_token(token: str) -> dict:
    """Decode and verify a JWT. Raises HTTP 401 on any failure."""
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ── FastAPI dependency ─────────────────────────────────────────────────────────

# In-memory singleton for the single hardcoded user
_STATIC_USER = User(id=1, username="demo", hashed_password="")


def get_current_user(
    token: str = Depends(oauth2_scheme),
) -> User:
    """
    Dependency: validates the Bearer token against STATIC_TOKEN from .env.
    Returns the singleton in-memory demo user — no DB lookup required.
    """
    if not settings.static_token or token != settings.static_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _STATIC_USER


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.post("/register", status_code=201)
def register(
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_session),
):
    """
    Create a new user account.

    TODO: hash password with passlib bcrypt before storing.
          user.hashed_password = pwd_context.hash(form.password)
    """
    existing = db.exec(select(User).where(User.username == form.username)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already taken")

    # ⚠️ INSECURE STUB: storing plaintext password — replace with bcrypt hash
    user = User(username=form.username, hashed_password=form.password)
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"message": "User registered", "user_id": user.id}


@router.post("/login")
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_session),
):
    """
    Exchange credentials for a JWT access token.

    TODO: compare hashed password with passlib:
          if not pwd_context.verify(form.password, user.hashed_password): ...
    """
    user = db.exec(select(User).where(User.username == form.username)).first()

    # ⚠️ INSECURE STUB: plaintext comparison — replace with bcrypt verify
    if not user or user.hashed_password != form.password:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token({"sub": user.username})
    return {"access_token": token, "token_type": "bearer"}
