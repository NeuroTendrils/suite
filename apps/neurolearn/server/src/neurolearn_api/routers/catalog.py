"""Public catalog, lesson delivery, and progress.

Copyright 2026 NeuroTendrils
SPDX-License-Identifier: AGPL-3.0-or-later

Serves the published catalogue to the app. Read-only for learners — there are
no accounts on the learning side, so nothing here records who read what.

Lesson payloads include the correct answers, because the app grades on the
device and stores progress locally (see app/lib/data/progress_repository.dart).
A curious learner can read the answer key out of the response. That is the
accepted trade for keeping learning anonymous and offline-capable.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from neurolearn_api.content.validate import strip_answers, validate_slug
from neurolearn_api.db import get_db
from neurolearn_api.models import Course, Lesson, LessonVersion, Role, Unit, User
from neurolearn_api.schemas import (
    CourseCreate,
    CourseOut,
    LessonContentOut,
    LessonSummary,
    UnitCreate,
    UnitOut,
)
from neurolearn_api.security import require_role

router = APIRouter(tags=["catalog"])


# ----------------------------------------------------------------- catalog


@router.post("/courses", response_model=CourseOut, status_code=201)
def create_course(
    body: CourseCreate,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(Role.reviewer)),
) -> CourseOut:
    slug = validate_slug(body.slug)
    if db.scalar(select(Course).where(Course.slug == slug)):
        raise HTTPException(status.HTTP_409_CONFLICT, "that course slug is taken")
    course = Course(slug=slug, title=body.title, description=body.description)
    db.add(course)
    db.commit()
    db.refresh(course)
    return _course_out(course)


@router.post("/courses/{course_id}/units", response_model=UnitOut, status_code=201)
def create_unit(
    course_id: str,
    body: UnitCreate,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(Role.reviewer)),
) -> UnitOut:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "course not found")
    unit = Unit(
        course_id=course_id,
        slug=validate_slug(body.slug),
        title=body.title,
        section=body.section,
        position=body.position,
    )
    db.add(unit)
    db.commit()
    db.refresh(unit)
    return _unit_out(unit)


def _lesson_summary(lesson: Lesson) -> LessonSummary:
    live = lesson.published()
    return LessonSummary(
        id=lesson.id,
        slug=lesson.slug,
        position=lesson.position,
        title=live.title if live else None,
        est_minutes=live.est_minutes if live else None,
        version=live.version if live else None,
        has_published=live is not None,
    )


def _unit_out(unit: Unit) -> UnitOut:
    return UnitOut(
        id=unit.id,
        slug=unit.slug,
        title=unit.title,
        section=unit.section,
        position=unit.position,
        lessons=[_lesson_summary(lesson) for lesson in unit.lessons],
    )


def _course_out(course: Course) -> CourseOut:
    return CourseOut(
        id=course.id,
        slug=course.slug,
        title=course.title,
        description=course.description,
        units=[_unit_out(u) for u in course.units],
    )


@router.get("/courses", response_model=list[CourseOut])
def list_courses(db: Session = Depends(get_db)) -> list[CourseOut]:
    courses = db.scalars(select(Course).where(Course.is_public.is_(True))).all()
    return [_course_out(c) for c in courses]


@router.get("/courses/{slug}", response_model=CourseOut)
def get_course(slug: str, db: Session = Depends(get_db)) -> CourseOut:
    course = db.scalar(select(Course).where(Course.slug == slug))
    if course is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "course not found")
    return _course_out(course)


# ------------------------------------------------------------------ lesson


def _resolve_published(db: Session, lesson_id: str) -> LessonVersion:
    lesson = db.get(Lesson, lesson_id)
    if lesson is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "lesson not found")
    live = lesson.published()
    if live is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "this lesson has no published version yet"
        )
    return live


@router.get("/lessons/{lesson_id}", response_model=LessonContentOut)
def get_lesson(lesson_id: str, db: Session = Depends(get_db)) -> LessonContentOut:
    version = _resolve_published(db, lesson_id)
    return LessonContentOut(
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
        blocks=strip_answers(version.blocks),
    )
