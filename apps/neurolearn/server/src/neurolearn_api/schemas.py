"""Request and response schemas.

Copyright 2026 NeuroTendrils
SPDX-License-Identifier: AGPL-3.0-or-later
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field

from neurolearn_api.models import LessonStatus, Role

# ------------------------------------------------------------------- auth


class RegisterRequest(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=2, max_length=80)
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class DeleteAccountRequest(BaseModel):
    """Deleting requires the password, not just a valid token."""

    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: str
    email: EmailStr
    display_name: str
    role: Role
    created_at: datetime

    model_config = {"from_attributes": True}


# ----------------------------------------------------------------- catalog


class CourseCreate(BaseModel):
    slug: str
    title: str = Field(min_length=2, max_length=160)
    description: str = ""


class UnitCreate(BaseModel):
    slug: str
    title: str = Field(min_length=2, max_length=160)
    section: str = "spark"
    position: int = 0


class LessonSummary(BaseModel):
    id: str
    slug: str
    position: int
    title: str | None = None
    est_minutes: int | None = None
    version: int | None = None
    has_published: bool = False


class UnitOut(BaseModel):
    id: str
    slug: str
    title: str
    section: str
    position: int
    lessons: list[LessonSummary] = []


class CourseOut(BaseModel):
    id: str
    slug: str
    title: str
    description: str
    units: list[UnitOut] = []


# --------------------------------------------------------------- authoring


class LessonDraftCreate(BaseModel):
    """Submit a new lesson, or a new version of an existing one."""

    slug: str
    title: str = Field(min_length=2, max_length=200)
    objective: str = ""
    est_minutes: int = Field(default=8, ge=1, le=60)
    blocks: list[dict[str, Any]]
    position: int = 0


class LessonDraftUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=200)
    objective: str | None = None
    est_minutes: int | None = Field(default=None, ge=1, le=60)
    blocks: list[dict[str, Any]] | None = None


class ReviewDecision(BaseModel):
    decision: str = Field(pattern="^(approve|reject)$")
    notes: str = ""


class LessonVersionOut(BaseModel):
    id: str
    lesson_id: str
    version: int
    title: str
    objective: str
    est_minutes: int
    status: LessonStatus
    author_id: str
    author_name: str | None = None
    created_at: datetime
    published_at: datetime | None = None

    model_config = {"from_attributes": True}


class LessonContentOut(LessonVersionOut):
    """Learner-facing view. Correct answers are stripped before this is built."""

    blocks: list[dict[str, Any]]


# ---------------------------------------------------------------- learning


class AttemptItem(BaseModel):
    item_id: str
    chosen: str


class AttemptSubmit(BaseModel):
    items: list[AttemptItem]


class AttemptResultItem(BaseModel):
    item_id: str
    chosen: str
    correct: bool
    explain: str


class AttemptResult(BaseModel):
    score: float
    passed: bool
    pass_score: float
    xp_awarded: int = 0
    total_xp: int = 0
    streak_days: int = 0
    results: list[AttemptResultItem]


class StatsOut(BaseModel):
    xp: int
    streak_days: int
    longest_streak: int
    daily_goal_xp: int
    practiced_today: bool
    lessons_completed: int
    member_since: date


class ProgressOut(BaseModel):
    lesson_id: str
    version_id: str
    completed: bool
    best_score: float
    attempts: int

    model_config = {"from_attributes": True}


class CourseProgressOut(BaseModel):
    course_id: str
    total_lessons: int
    completed_lessons: int
    percent: float
    lessons: list[ProgressOut] = []
