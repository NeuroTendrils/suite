"""Community authoring and review.

Copyright 2026 NeuroTendrils
SPDX-License-Identifier: AGPL-3.0-or-later

The workflow, and why it is shaped this way:

    draft ──submit──> in_review ──approve──> published
      ^                   │
      └────── reject ─────┘

An author edits freely while a version is a draft. Once submitted it locks,
because a reviewer needs to be looking at the same thing they are approving.
Publishing a new version supersedes the old one rather than overwriting it, so
a learner who worked through version 2 still has a coherent history after
version 3 goes live.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from neurolearn_api.content.validate import (
    ContentError,
    validate_lesson_blocks,
    validate_slug,
)
from neurolearn_api.db import get_db
from neurolearn_api.models import (
    Lesson,
    LessonStatus,
    LessonVersion,
    Review,
    Role,
    Unit,
    User,
)
from neurolearn_api.schemas import (
    LessonDraftCreate,
    LessonDraftUpdate,
    LessonVersionOut,
    ReviewDecision,
)
from neurolearn_api.security import get_current_user, require_role

router = APIRouter(prefix="/authoring", tags=["authoring"])


def _out(version: LessonVersion) -> LessonVersionOut:
    return LessonVersionOut(
        id=version.id,
        lesson_id=version.lesson_id,
        version=version.version,
        title=version.title,
        objective=version.objective,
        est_minutes=version.est_minutes,
        status=version.status,
        author_id=version.author_id,
        author_name=version.author.display_name if version.author else None,
        created_at=version.created_at,
        published_at=version.published_at,
    )


def _load_version(db: Session, version_id: str) -> LessonVersion:
    version = db.get(LessonVersion, version_id)
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "lesson version not found")
    return version


def _validate(blocks: list) -> list[dict]:
    try:
        return validate_lesson_blocks(blocks)
    except ContentError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {"path": exc.path, "message": exc.message},
        ) from exc


@router.post(
    "/units/{unit_id}/lessons",
    response_model=LessonVersionOut,
    status_code=201,
)
def create_draft(
    unit_id: str,
    body: LessonDraftCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.author)),
) -> LessonVersionOut:
    """Create a lesson, or add a new draft version to an existing one."""
    unit = db.get(Unit, unit_id)
    if unit is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unit not found")

    try:
        slug = validate_slug(body.slug)
    except ContentError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    blocks = _validate(body.blocks)

    lesson = db.scalar(
        select(Lesson).where(Lesson.unit_id == unit_id, Lesson.slug == slug)
    )
    if lesson is None:
        lesson = Lesson(unit_id=unit_id, slug=slug, position=body.position)
        db.add(lesson)
        db.flush()
        next_version = 1
    else:
        # An author may not start a second draft while one is already open;
        # that produces two competing "latest" versions and a confusing queue.
        open_draft = [
            v
            for v in lesson.versions
            if v.status in (LessonStatus.draft, LessonStatus.in_review)
        ]
        if open_draft:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"version {open_draft[0].version} is still open — "
                "edit or withdraw it before starting another",
            )
        next_version = max((v.version for v in lesson.versions), default=0) + 1

    version = LessonVersion(
        lesson_id=lesson.id,
        version=next_version,
        title=body.title,
        objective=body.objective,
        est_minutes=body.est_minutes,
        blocks=blocks,
        status=LessonStatus.draft,
        author_id=user.id,
    )
    db.add(version)
    db.commit()
    db.refresh(version)
    return _out(version)


@router.patch("/versions/{version_id}", response_model=LessonVersionOut)
def update_draft(
    version_id: str,
    body: LessonDraftUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.author)),
) -> LessonVersionOut:
    version = _load_version(db, version_id)

    if version.author_id != user.id and user.role != Role.admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "this is not your draft")
    if version.status is not LessonStatus.draft:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"a {version.status.value} version cannot be edited — "
            "publish a new version instead",
        )

    if body.blocks is not None:
        version.blocks = _validate(body.blocks)
    if body.title is not None:
        version.title = body.title
    if body.objective is not None:
        version.objective = body.objective
    if body.est_minutes is not None:
        version.est_minutes = body.est_minutes

    db.commit()
    db.refresh(version)
    return _out(version)


@router.post("/versions/{version_id}/submit", response_model=LessonVersionOut)
def submit_for_review(
    version_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.author)),
) -> LessonVersionOut:
    version = _load_version(db, version_id)
    if version.author_id != user.id and user.role != Role.admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "this is not your draft")
    if version.status is not LessonStatus.draft:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"already {version.status.value}"
        )

    # Re-validate at the boundary. Content could have been written by an older
    # build whose rules were looser.
    version.blocks = _validate(version.blocks)
    version.status = LessonStatus.in_review
    db.commit()
    db.refresh(version)
    return _out(version)


@router.get("/queue", response_model=list[LessonVersionOut])
def review_queue(
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(Role.reviewer)),
) -> list[LessonVersionOut]:
    versions = db.scalars(
        select(LessonVersion)
        .where(LessonVersion.status == LessonStatus.in_review)
        .order_by(LessonVersion.created_at)
    ).all()
    return [_out(v) for v in versions]


@router.post("/versions/{version_id}/review", response_model=LessonVersionOut)
def review(
    version_id: str,
    body: ReviewDecision,
    db: Session = Depends(get_db),
    reviewer: User = Depends(require_role(Role.reviewer)),
) -> LessonVersionOut:
    version = _load_version(db, version_id)
    if version.status is not LessonStatus.in_review:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"only a version in review can be decided (this one is {version.status.value})",
        )
    # Reviewing your own submission defeats the point of review.
    if version.author_id == reviewer.id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "an author cannot review their own lesson"
        )

    db.add(
        Review(
            version_id=version.id,
            reviewer_id=reviewer.id,
            decision=body.decision,
            notes=body.notes,
        )
    )

    if body.decision == "approve":
        # Supersede whatever was live. The old version stays in the table.
        for other in version.lesson.versions:
            if other.id != version.id and other.status is LessonStatus.published:
                other.status = LessonStatus.archived
        version.status = LessonStatus.published
        version.published_at = datetime.now(UTC)
    else:
        version.status = LessonStatus.rejected

    db.commit()
    db.refresh(version)
    return _out(version)


@router.post("/versions/{version_id}/withdraw", response_model=LessonVersionOut)
def withdraw(
    version_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.author)),
) -> LessonVersionOut:
    """Pull a submission back out of the queue, or reopen a rejected one."""
    version = _load_version(db, version_id)
    if version.author_id != user.id and user.role != Role.admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "this is not your draft")
    if version.status not in (LessonStatus.in_review, LessonStatus.rejected):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "only a submitted or rejected version can be withdrawn",
        )
    version.status = LessonStatus.draft
    db.commit()
    db.refresh(version)
    return _out(version)


@router.get("/mine", response_model=list[LessonVersionOut])
def my_lessons(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[LessonVersionOut]:
    versions = db.scalars(
        select(LessonVersion)
        .where(LessonVersion.author_id == user.id)
        .order_by(LessonVersion.created_at.desc())
    ).all()
    return [_out(v) for v in versions]
