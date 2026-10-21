"""Learner-facing endpoints: attempts, XP, streaks, progress.

Copyright 2026 NeuroTendrils
SPDX-License-Identifier: AGPL-3.0-or-later

Grading happens here, on the server. Correct answers are stripped from every
lesson payload the client receives, so a learner cannot read the key out of the
network tab. That matters beyond cheating: once the client reports its own
score, streaks and XP stop meaning anything, and the item-level data — which is
what makes adaptive practice possible later — becomes untrustworthy.
"""

from __future__ import annotations

from datetime import UTC, date, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from neurolearn_api.content.validate import quiz_items
from neurolearn_api.db import get_db
from neurolearn_api.models import (
    Course,
    Enrollment,
    Lesson,
    LessonStatus,
    LessonVersion,
    Progress,
    QuizAttempt,
    User,
)
from neurolearn_api.schemas import (
    AttemptResult,
    AttemptResultItem,
    AttemptSubmit,
    CourseProgressOut,
    ProgressOut,
    StatsOut,
)
from neurolearn_api.security import get_current_user

router = APIRouter(tags=["learning"])

# XP is deliberately modest and flat. Large or variable rewards turn a lesson
# into a slot machine; the goal is a reason to come back tomorrow, not a
# dopamine loop.
XP_PASS = 20
XP_FIRST_TIME_BONUS = 10


def _today() -> date:
    return date.today()


def touch_streak(user: User, on: date | None = None) -> None:
    """Advance the streak for a day of activity.

    Rules, and why:

    * Same day twice does nothing. A streak counts days, not sessions.
    * Yesterday → today increments.
    * A gap of two or more days resets to 1, not 0 — today still counted,
      and showing someone a zero after they just did work reads as a bug.
    """
    on = on or _today()
    last = user.last_active_on

    if last == on:
        return
    if last is not None and last == on - timedelta(days=1):
        user.streak_days += 1
    else:
        user.streak_days = 1

    user.last_active_on = on
    user.longest_streak = max(user.longest_streak or 0, user.streak_days)


def current_streak(user: User, on: date | None = None) -> int:
    """The streak as of today, without mutating anything.

    A stored streak goes stale the moment a day passes without activity, so
    reads must recompute rather than trust the column. Otherwise someone who
    stops for a week still sees "7 day streak" until they next submit.
    """
    on = on or _today()
    last = user.last_active_on
    if last is None:
        return 0
    if last == on or last == on - timedelta(days=1):
        return user.streak_days
    return 0


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


@router.post("/lessons/{lesson_id}/attempts", response_model=AttemptResult)
def submit_attempt(
    lesson_id: str,
    body: AttemptSubmit,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AttemptResult:
    version = _resolve_published(db, lesson_id)
    answers = quiz_items(version.blocks)
    if not answers:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "this lesson has no gradable questions"
        )

    explanations = {
        q["id"]: q["explain"]
        for block in version.blocks
        if block.get("type") == "check"
        for q in block["questions"]
    }
    pass_score = next(
        (b["pass_score"] for b in version.blocks if b.get("type") == "check"), 0.7
    )

    results: list[AttemptResultItem] = []
    for item in body.items:
        if item.item_id not in answers:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"unknown question {item.item_id!r}",
            )
        results.append(
            AttemptResultItem(
                item_id=item.item_id,
                chosen=item.chosen,
                correct=item.chosen == answers[item.item_id],
                explain=explanations.get(item.item_id, ""),
            )
        )

    # Unanswered questions count as wrong. Scoring only what was submitted
    # would let someone pass by answering one question and skipping the rest.
    score = sum(1 for r in results if r.correct) / len(answers)
    passed = score >= pass_score

    progress = db.scalar(
        select(Progress).where(
            Progress.user_id == user.id, Progress.lesson_id == lesson_id
        )
    )
    first_completion = passed and (progress is None or not progress.completed)

    if progress is None:
        # SQLAlchemy applies `default=` at flush, so a fresh object still holds
        # None. Initialise explicitly rather than relying on flush ordering.
        progress = Progress(
            user_id=user.id,
            lesson_id=lesson_id,
            version_id=version.id,
            completed=False,
            best_score=0.0,
            attempts=0,
        )
        db.add(progress)

    progress.attempts += 1
    progress.version_id = version.id
    progress.best_score = max(progress.best_score, score)
    # Completion is sticky: passing once keeps the lesson complete even if a
    # later attempt scores worse. Retries should never feel punishing.
    progress.completed = progress.completed or passed

    # XP is only awarded for a pass, and the bonus only the first time. Without
    # that, replaying one easy lesson would be the fastest way to farm XP.
    xp = 0
    if passed:
        xp = XP_PASS + (XP_FIRST_TIME_BONUS if first_completion else 0)
        user.xp = (user.xp or 0) + xp
        touch_streak(user)

    db.add(
        QuizAttempt(
            user_id=user.id,
            version_id=version.id,
            score=score,
            passed=passed,
            xp_awarded=xp,
            items=[r.model_dump() for r in results],
        )
    )
    db.commit()

    return AttemptResult(
        score=score,
        passed=passed,
        pass_score=pass_score,
        xp_awarded=xp,
        total_xp=user.xp,
        streak_days=current_streak(user),
        results=results,
    )


@router.get("/me/stats", response_model=StatsOut)
def my_stats(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> StatsOut:
    lessons_done = db.scalar(
        select(func.count())
        .select_from(Progress)
        .where(Progress.user_id == user.id, Progress.completed.is_(True))
    )
    streak = current_streak(user)
    return StatsOut(
        xp=user.xp or 0,
        streak_days=streak,
        longest_streak=user.longest_streak or 0,
        daily_goal_xp=user.daily_goal_xp or 30,
        # A streak the learner has not yet protected today is the thing the UI
        # needs to nudge about, so say it plainly rather than making the client
        # derive it from a date.
        practiced_today=user.last_active_on == _today(),
        lessons_completed=lessons_done or 0,
        member_since=user.created_at.replace(tzinfo=UTC).date()
        if user.created_at
        else _today(),
    )


@router.post("/courses/{course_id}/enroll", status_code=201)
def enroll(
    course_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    if db.get(Course, course_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "course not found")
    existing = db.scalar(
        select(Enrollment).where(
            Enrollment.user_id == user.id, Enrollment.course_id == course_id
        )
    )
    if existing is None:
        db.add(Enrollment(user_id=user.id, course_id=course_id))
        db.commit()
    return {"course_id": course_id, "enrolled": True}


@router.get("/courses/{course_id}/progress", response_model=CourseProgressOut)
def course_progress(
    course_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CourseProgressOut:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "course not found")

    # Only lessons with a published version count toward the denominator, so a
    # half-written unit does not make everyone's progress bar look broken.
    lesson_ids = [
        lesson.id
        for unit in course.units
        for lesson in unit.lessons
        if any(v.status is LessonStatus.published for v in lesson.versions)
    ]
    rows = (
        db.scalars(
            select(Progress).where(
                Progress.user_id == user.id, Progress.lesson_id.in_(lesson_ids)
            )
        ).all()
        if lesson_ids
        else []
    )

    completed = sum(1 for r in rows if r.completed)
    total = len(lesson_ids)
    return CourseProgressOut(
        course_id=course_id,
        total_lessons=total,
        completed_lessons=completed,
        percent=round(completed / total * 100, 1) if total else 0.0,
        lessons=[ProgressOut.model_validate(r) for r in rows],
    )
