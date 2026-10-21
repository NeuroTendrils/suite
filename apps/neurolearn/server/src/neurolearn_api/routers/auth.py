"""Account endpoints.

Copyright 2026 NeuroTendrils
SPDX-License-Identifier: AGPL-3.0-or-later
"""

from __future__ import annotations

import uuid

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from neurolearn_api.config import settings
from neurolearn_api.db import get_db
from neurolearn_api.models import (
    Enrollment,
    LessonVersion,
    Progress,
    QuizAttempt,
    Role,
    User,
)
from neurolearn_api.schemas import (
    DeleteAccountRequest,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserOut,
)
from neurolearn_api.security import (
    PasswordError,
    create_access_token,
    get_current_user,
    hash_password,
    oauth2_scheme,
    verify_password,
)
from neurolearn_api.security_middleware import revoke

# Reserved address for re-attributing content from deleted accounts. Not a
# real mailbox — the row exists only so published lessons keep a valid author.
DELETED_AUTHOR_EMAIL = "deleted@invalid.neurotendrils"

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(body: RegisterRequest, db: Session = Depends(get_db)) -> TokenResponse:
    email = body.email.lower()
    existing = db.scalar(select(User).where(User.email == email))
    if existing is not None:
        # Registration reveals whether an address is taken; that is unavoidable
        # for a product with public author profiles. Login does not.
        raise HTTPException(status.HTTP_409_CONFLICT, "that email is already registered")

    try:
        password_hash = hash_password(body.password)
    except PasswordError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    # The first account to exist becomes the admin. Everyone after signs up as
    # a learner; authoring and moderation are granted deliberately.
    is_first = db.scalar(select(func.count()).select_from(User)) == 0

    user = User(
        email=email,
        display_name=body.display_name.strip(),
        password_hash=password_hash,
        role=Role.admin if is_first else Role.learner,
    )
    db.add(user)
    db.commit()
    return TokenResponse(access_token=create_access_token(user))


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    # One message for both failure modes so login cannot be used to enumerate
    # registered addresses.
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "incorrect email or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "this account is disabled")
    return TokenResponse(access_token=create_access_token(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.post("/logout", status_code=204)
def logout(
    token: str = Depends(oauth2_scheme),
    _user: User = Depends(get_current_user),
) -> None:
    """Revoke the presented token.

    Decoding again here is intentional: get_current_user does not hand back
    the raw claims, and we need the jti and exp to record the revocation.
    """
    claims = jwt.decode(
        token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
    )
    revoke(claims["jti"], float(claims["exp"]))


@router.delete("/me", status_code=204)
def delete_account(
    body: DeleteAccountRequest,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    """Permanently delete the account and everything attached to it.

    The App Store requires in-app account deletion (Guideline 5.1.1(v)), and
    it must actually delete rather than deactivate.

    The password is re-checked because a stolen token should not be enough to
    destroy someone's account.

    Lessons the user authored are kept but re-attributed, because deleting
    published content would break other learners' progress. Their name is
    replaced everywhere it appears.
    """
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "incorrect password")

    db.execute(delete(QuizAttempt).where(QuizAttempt.user_id == user.id))
    db.execute(delete(Progress).where(Progress.user_id == user.id))
    db.execute(delete(Enrollment).where(Enrollment.user_id == user.id))

    authored = db.scalars(
        select(LessonVersion).where(LessonVersion.author_id == user.id)
    ).all()
    if authored:
        ghost = db.scalar(select(User).where(User.email == DELETED_AUTHOR_EMAIL))
        if ghost is None:
            # The id is set explicitly rather than left to the column default:
            # SQLAlchemy applies defaults during flush, and reading the
            # attribute before that yields None, which then fails the NOT NULL
            # constraint on the reassignment below.
            ghost = User(
                id=uuid.uuid4().hex,
                email=DELETED_AUTHOR_EMAIL,
                display_name="Former contributor",
                password_hash="!",  # unusable — never matches a bcrypt check
                is_active=False,
            )
            db.add(ghost)
            db.flush()
        for version in authored:
            # Assign through the relationship, not the raw FK. Setting
            # author_id alone leaves the row in user.lessons, and deleting the
            # user then nulls the column straight back out.
            version.author = ghost

    claims = jwt.decode(
        token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
    )
    revoke(claims["jti"], float(claims["exp"]))

    db.delete(user)
    db.commit()
