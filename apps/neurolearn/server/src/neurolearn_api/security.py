"""Authentication and authorization.

Copyright 2026 NeuroTendrils
SPDX-License-Identifier: AGPL-3.0-or-later
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from neurolearn_api.config import settings
from neurolearn_api.db import get_db
from neurolearn_api.models import Role, User, role_allows
from neurolearn_api.security_middleware import is_revoked

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

# bcrypt is used directly rather than through passlib: passlib 1.7 is
# unmaintained and breaks against bcrypt 4.1+, and the API we need here is
# two functions wide.
#
# bcrypt silently truncates past 72 bytes, so a longer password would grant
# access with only its first 72 characters. Reject rather than truncate.
MAX_PASSWORD_BYTES = 72
MIN_PASSWORD_CHARS = 10


class PasswordError(ValueError):
    pass


def check_password_policy(password: str) -> None:
    if len(password) < MIN_PASSWORD_CHARS:
        raise PasswordError(
            f"password must be at least {MIN_PASSWORD_CHARS} characters"
        )
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise PasswordError(
            f"password must be at most {MAX_PASSWORD_BYTES} bytes"
        )


def hash_password(password: str) -> str:
    check_password_policy(password)
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("ascii"))
    except (ValueError, TypeError):
        # A malformed stored hash must read as "wrong password", never as an
        # unhandled 500 that tells an attacker something is different here.
        return False


def create_access_token(user: User) -> str:
    now = datetime.now(UTC)
    # jti gives each token an identity so it can be revoked on logout. Without
    # it, signing out is cosmetic — the token stays valid until it expires.
    payload = {
        "sub": user.id,
        "role": user.role.value,
        "jti": uuid.uuid4().hex,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _credentials_error(detail: str = "not authenticated") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    if not token:
        raise _credentials_error()
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
    except jwt.ExpiredSignatureError:
        raise _credentials_error("token expired") from None
    except jwt.PyJWTError:
        raise _credentials_error("invalid token") from None

    if is_revoked(payload.get("jti")):
        raise _credentials_error("token has been revoked")

    user = db.get(User, payload.get("sub"))
    if user is None or not user.is_active:
        raise _credentials_error("account is not active")
    # The role is re-read from the database rather than trusted from the token,
    # so revoking someone's reviewer rights takes effect on their next request
    # instead of whenever their token happens to expire.
    return user


def get_optional_user(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User | None:
    if not token:
        return None
    try:
        return get_current_user(token, db)
    except HTTPException:
        return None


def require_role(required: Role):
    """Dependency factory enforcing a minimum role."""

    def dependency(user: User = Depends(get_current_user)) -> User:
        if not role_allows(user.role, required):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"this action requires the {required.value} role",
            )
        return user

    return dependency
