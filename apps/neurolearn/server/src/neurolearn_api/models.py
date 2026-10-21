"""Database models.

Copyright 2026 NeuroTendrils
SPDX-License-Identifier: AGPL-3.0-or-later

Two decisions shape this schema:

1. **Lessons are versioned, and published versions are immutable.** Editing a
   published lesson creates a new draft version rather than mutating the one
   learners already worked through. Progress rows point at a specific version,
   so a learner's history stays meaningful after an author revises a lesson.

2. **Community content is untrusted until reviewed.** Anyone can author; only
   a reviewer can publish. The review decision is a row, not a flag, so the
   record of who approved what survives.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from enum import StrEnum

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Role(StrEnum):
    """Roles are cumulative: admin implies reviewer implies author implies learner.

    Everyone signs up as a learner. Authoring and moderation are granted.
    """

    learner = "learner"
    author = "author"
    reviewer = "reviewer"
    admin = "admin"


_RANK = {Role.learner: 0, Role.author: 1, Role.reviewer: 2, Role.admin: 3}


def role_allows(actual: Role, required: Role) -> bool:
    return _RANK[actual] >= _RANK[required]


class LessonStatus(StrEnum):
    draft = "draft"
    in_review = "in_review"
    published = "published"
    rejected = "rejected"
    archived = "archived"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.learner)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    # --- learning stats -------------------------------------------------
    xp: Mapped[int] = mapped_column(Integer, default=0)
    streak_days: Mapped[int] = mapped_column(Integer, default=0)
    longest_streak: Mapped[int] = mapped_column(Integer, default=0)
    # Date, not datetime: a streak is about calendar days, and storing an
    # instant invites off-by-one bugs when comparing "today" to "yesterday".
    last_active_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    daily_goal_xp: Mapped[int] = mapped_column(Integer, default=30)

    lessons: Mapped[list[LessonVersion]] = relationship(back_populates="author")


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    is_public: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    units: Mapped[list[Unit]] = relationship(
        back_populates="course", cascade="all, delete-orphan", order_by="Unit.position"
    )


class Unit(Base):
    __tablename__ = "units"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id"), index=True)
    slug: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(160))
    section: Mapped[str] = mapped_column(String(40), default="spark")
    position: Mapped[int] = mapped_column(Integer, default=0)

    course: Mapped[Course] = relationship(back_populates="units")
    lessons: Mapped[list[Lesson]] = relationship(
        back_populates="unit", cascade="all, delete-orphan", order_by="Lesson.position"
    )

    __table_args__ = (UniqueConstraint("course_id", "slug", name="uq_unit_slug"),)


class Lesson(Base):
    """Stable identity for a lesson. Content lives in LessonVersion."""

    __tablename__ = "lessons"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    unit_id: Mapped[str] = mapped_column(ForeignKey("units.id"), index=True)
    slug: Mapped[str] = mapped_column(String(80))
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    unit: Mapped[Unit] = relationship(back_populates="lessons")
    versions: Mapped[list[LessonVersion]] = relationship(
        back_populates="lesson",
        cascade="all, delete-orphan",
        order_by="LessonVersion.version",
    )

    __table_args__ = (UniqueConstraint("unit_id", "slug", name="uq_lesson_slug"),)

    def published(self) -> LessonVersion | None:
        """Highest published version, or None if nothing is live yet."""
        live = [v for v in self.versions if v.status is LessonStatus.published]
        return max(live, key=lambda v: v.version) if live else None


class LessonVersion(Base):
    __tablename__ = "lesson_versions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    lesson_id: Mapped[str] = mapped_column(ForeignKey("lessons.id"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)

    title: Mapped[str] = mapped_column(String(200))
    objective: Mapped[str] = mapped_column(Text, default="")
    est_minutes: Mapped[int] = mapped_column(Integer, default=8)
    # Compiled block list — validated by content.validate before it lands here.
    blocks: Mapped[list] = mapped_column(JSON, default=list)

    status: Mapped[LessonStatus] = mapped_column(
        Enum(LessonStatus), default=LessonStatus.draft, index=True
    )
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    lesson: Mapped[Lesson] = relationship(back_populates="versions")
    author: Mapped[User] = relationship(back_populates="lessons")
    reviews: Mapped[list[Review]] = relationship(
        back_populates="version", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("lesson_id", "version", name="uq_lesson_version"),
    )


class Review(Base):
    """A reviewer's decision. Kept as a row so the record survives."""

    __tablename__ = "reviews"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    version_id: Mapped[str] = mapped_column(ForeignKey("lesson_versions.id"), index=True)
    reviewer_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    decision: Mapped[str] = mapped_column(String(20))  # approve | reject
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    version: Mapped[LessonVersion] = relationship(back_populates="reviews")


class Enrollment(Base):
    __tablename__ = "enrollments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    __table_args__ = (UniqueConstraint("user_id", "course_id", name="uq_enrollment"),)


class Progress(Base):
    """One row per learner per lesson, pointing at the version they finished."""

    __tablename__ = "progress"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    lesson_id: Mapped[str] = mapped_column(ForeignKey("lessons.id"), index=True)
    version_id: Mapped[str] = mapped_column(ForeignKey("lesson_versions.id"))

    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    best_score: Mapped[float] = mapped_column(Float, default=0.0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    __table_args__ = (UniqueConstraint("user_id", "lesson_id", name="uq_progress"),)


class QuizAttempt(Base):
    """Every attempt is kept, not just the best.

    Item-level results are what make adaptive practice possible later: knowing
    a learner confuses EMG with line noise is worth more than knowing they
    scored 60%.
    """

    __tablename__ = "quiz_attempts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    version_id: Mapped[str] = mapped_column(ForeignKey("lesson_versions.id"), index=True)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    xp_awarded: Mapped[int] = mapped_column(Integer, default=0)
    items: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)
