# ================================================================
# NexusCare — utils/security.py
# Password hashing (bcrypt) and JWT token creation/verification.
# ================================================================

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from jose import ExpiredSignatureError, JWTError, jwt

from app.config import settings
from app.utils.exceptions import TokenExpiredError, UnauthorizedError

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------
# PASSWORD HASHING
# ----------------------------------------------------------------

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# ----------------------------------------------------------------
# JWT
# ----------------------------------------------------------------

def create_access_token(subject: dict, expires_minutes: Optional[int] = None) -> str:
    minutes = expires_minutes if expires_minutes is not None else settings.access_token_expire_minutes
    expire = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    payload = {**subject, "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except ExpiredSignatureError:
        raise TokenExpiredError()
    except JWTError:
        raise UnauthorizedError()
