"""API tests.

Copyright 2026 NeuroTendrils
SPDX-License-Identifier: AGPL-3.0-or-later
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from neurolearn_api.db import get_db
from neurolearn_api.main import app
from neurolearn_api.models import Base, Role, User
from neurolearn_api.routers.learning import current_streak, touch_streak
from neurolearn_api.security_middleware import reset_rate_limits, reset_revocations


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override
    with TestClient(app) as c:
        c.session_factory = Session
        yield c
    app.dependency_overrides.clear()


def register(client, email, name="Tester", password="correct-horse-battery"):
    r = client.post(
        "/auth/register",
        json={"email": email, "display_name": name, "password": password},
    )
    assert r.status_code == 201, r.text
    return r.json()["access_token"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def promote(client, email, role: Role):
    db = client.session_factory()
    user = db.query(User).filter(User.email == email).one()
    user.role = role
    db.commit()
    db.close()


def sample_blocks():
    return [
        {"type": "hook", "text": "How can a headset measure anything at all?"},
        {"type": "prose", "text": "Neurons move ions across the membrane."},
        {"type": "callout", "kind": "myth", "text": "EEG does not read thoughts."},
        {
            "type": "check",
            "pass_score": 0.7,
            "questions": [
                {
                    "id": "q1",
                    "prompt": "Why is one neuron too weak to detect at the scalp?",
                    "explain": "EEG needs synchronized population activity.",
                    "choices": [
                        {
                            "text": "Its field is tiny; many must fire together",
                            "correct": True,
                        },
                        {"text": "Neurons are not electrical"},
                    ],
                },
                {
                    "id": "q2",
                    "prompt": "What does the skull do to the signal?",
                    "explain": "Bone attenuates and spatially blurs the signal.",
                    "choices": [
                        {"text": "Attenuates and blurs it", "correct": True},
                        {"text": "Amplifies it to volts"},
                    ],
                },
            ],
        },
    ]


# ------------------------------------------------------------------- auth


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_first_user_becomes_admin_and_second_is_a_learner(client):
    a = register(client, "first@example.com")
    b = register(client, "second@example.com")
    assert client.get("/auth/me", headers=auth(a)).json()["role"] == "admin"
    assert client.get("/auth/me", headers=auth(b)).json()["role"] == "learner"


def test_duplicate_email_is_rejected(client):
    register(client, "dupe@example.com")
    r = client.post(
        "/auth/register",
        json={
            "email": "dupe@example.com",
            "display_name": "Xavier",
            "password": "another-good-one",
        },
    )
    assert r.status_code == 409


def test_short_password_is_rejected(client):
    r = client.post(
        "/auth/register",
        json={"email": "a@example.com", "display_name": "A", "password": "short"},
    )
    assert r.status_code == 422


def test_overlong_password_is_rejected_not_truncated(client):
    # bcrypt ignores bytes past 72; silently truncating would mean only the
    # first 72 characters ever matter.
    r = client.post(
        "/auth/register",
        json={"email": "a@example.com", "display_name": "A", "password": "x" * 200},
    )
    assert r.status_code == 422


def test_login_does_not_reveal_whether_an_account_exists(client):
    register(client, "real@example.com", password="correct-horse-battery")
    wrong_pw = client.post(
        "/auth/login", json={"email": "real@example.com", "password": "nope-nope-nope"}
    )
    no_user = client.post(
        "/auth/login", json={"email": "ghost@example.com", "password": "nope-nope-nope"}
    )
    assert wrong_pw.status_code == no_user.status_code == 401
    assert wrong_pw.json()["detail"] == no_user.json()["detail"]


def test_unauthenticated_request_is_401(client):
    assert client.get("/auth/me").status_code == 401


def test_garbage_token_is_401(client):
    assert client.get("/auth/me", headers=auth("not.a.jwt")).status_code == 401


# ------------------------------------------------------------------ roles


def test_learner_cannot_author(client):
    register(client, "admin@example.com")
    learner = register(client, "learner@example.com")
    r = client.post(
        "/authoring/units/whatever/lessons",
        headers=auth(learner),
        json={"slug": "x", "title": "X", "blocks": sample_blocks()},
    )
    assert r.status_code == 403


def test_role_change_takes_effect_without_reissuing_a_token(client):
    register(client, "admin@example.com")
    token = register(client, "author@example.com")
    promote(client, "author@example.com", Role.author)
    # Same token as before the promotion.
    r = client.get("/authoring/mine", headers=auth(token))
    assert r.status_code == 200


# ------------------------------------------------------- content validation


def _setup_unit(client):
    admin = register(client, "admin@example.com")
    course = client.post(
        "/courses", headers=auth(admin), json={"slug": "bci-foundations", "title": "BCI"}
    ).json()
    unit = client.post(
        f"/courses/{course['id']}/units",
        headers=auth(admin),
        json={"slug": "intro-01", "title": "Currents"},
    ).json()
    return admin, course, unit


@pytest.mark.parametrize(
    "blocks,fragment",
    [
        ([], "at least one block"),
        ([{"type": "prose", "text": "no check here"}], "at least one check"),
        ([{"type": "wat", "text": "hi"}], "unknown block type"),
        (
            [{"type": "prose", "text": "<script>alert(1)</script>"}],
            "HTML is not allowed",
        ),
        (
            [{"type": "sim", "sim_id": "not-registered", "goal": "g"}],
            "unknown simulation",
        ),
        (
            [{"type": "figure", "asset": "../../etc/passwd", "alt": "x"}],
            "traverse",
        ),
    ],
)
def test_invalid_content_is_rejected(client, blocks, fragment):
    admin, _course, unit = _setup_unit(client)
    r = client.post(
        f"/authoring/units/{unit['id']}/lessons",
        headers=auth(admin),
        json={"slug": "bad", "title": "Bad", "blocks": blocks},
    )
    assert r.status_code == 422
    assert fragment in str(r.json()["detail"]).lower() or fragment in str(r.json()["detail"])


def test_quiz_needs_exactly_one_correct_answer(client):
    admin, _course, unit = _setup_unit(client)
    blocks = [
        {
            "type": "check",
            "questions": [
                {
                    "id": "q1",
                    "prompt": "Pick one",
                    "explain": "because",
                    "choices": [{"text": "a", "correct": True}, {"text": "b", "correct": True}],
                }
            ],
        }
    ]
    r = client.post(
        f"/authoring/units/{unit['id']}/lessons",
        headers=auth(admin),
        json={"slug": "two-right", "title": "Two Right", "blocks": blocks},
    )
    assert r.status_code == 422
    assert "exactly one" in str(r.json()["detail"])


def test_question_without_explanation_is_rejected(client):
    admin, _course, unit = _setup_unit(client)
    blocks = [
        {
            "type": "check",
            "questions": [
                {
                    "id": "q1",
                    "prompt": "Pick one",
                    "choices": [{"text": "a", "correct": True}, {"text": "b"}],
                }
            ],
        }
    ]
    r = client.post(
        f"/authoring/units/{unit['id']}/lessons",
        headers=auth(admin),
        json={"slug": "no-explain", "title": "No Explain", "blocks": blocks},
    )
    assert r.status_code == 422


# --------------------------------------------------------- authoring flow


def test_full_authoring_lifecycle(client):
    admin, _course, unit = _setup_unit(client)
    author_token = register(client, "author@example.com", "Ada")
    promote(client, "author@example.com", Role.author)

    draft = client.post(
        f"/authoring/units/{unit['id']}/lessons",
        headers=auth(author_token),
        json={"slug": "brain-electricity", "title": "Currents", "blocks": sample_blocks()},
    ).json()
    assert draft["status"] == "draft" and draft["version"] == 1

    # Not visible to learners yet.
    assert client.get(f"/lessons/{draft['lesson_id']}").status_code == 404

    submitted = client.post(
        f"/authoring/versions/{draft['id']}/submit", headers=auth(author_token)
    ).json()
    assert submitted["status"] == "in_review"

    # Locked while under review.
    locked = client.patch(
        f"/authoring/versions/{draft['id']}",
        headers=auth(author_token),
        json={"title": "Sneaky edit"},
    )
    assert locked.status_code == 409

    queue = client.get("/authoring/queue", headers=auth(admin)).json()
    assert len(queue) == 1

    approved = client.post(
        f"/authoring/versions/{draft['id']}/review",
        headers=auth(admin),
        json={"decision": "approve", "notes": "good"},
    ).json()
    assert approved["status"] == "published"

    live = client.get(f"/lessons/{draft['lesson_id']}").json()
    assert live["title"] == "Currents"
    assert live["author_name"] == "Ada"


def test_author_cannot_review_their_own_lesson(client):
    admin, _course, unit = _setup_unit(client)
    # Admin authors it themselves, then tries to approve it.
    draft = client.post(
        f"/authoring/units/{unit['id']}/lessons",
        headers=auth(admin),
        json={"slug": "self", "title": "Self", "blocks": sample_blocks()},
    ).json()
    client.post(f"/authoring/versions/{draft['id']}/submit", headers=auth(admin))
    r = client.post(
        f"/authoring/versions/{draft['id']}/review",
        headers=auth(admin),
        json={"decision": "approve"},
    )
    assert r.status_code == 403


def test_second_open_draft_is_blocked(client):
    admin, _course, unit = _setup_unit(client)
    client.post(
        f"/authoring/units/{unit['id']}/lessons",
        headers=auth(admin),
        json={"slug": "dup", "title": "One", "blocks": sample_blocks()},
    )
    r = client.post(
        f"/authoring/units/{unit['id']}/lessons",
        headers=auth(admin),
        json={"slug": "dup", "title": "Two", "blocks": sample_blocks()},
    )
    assert r.status_code == 409


def test_publishing_a_new_version_archives_the_old_one(client):
    admin, _course, unit = _setup_unit(client)
    author = register(client, "author@example.com")
    promote(client, "author@example.com", Role.author)

    v1 = client.post(
        f"/authoring/units/{unit['id']}/lessons",
        headers=auth(author),
        json={"slug": "evolving", "title": "V1", "blocks": sample_blocks()},
    ).json()
    client.post(f"/authoring/versions/{v1['id']}/submit", headers=auth(author))
    client.post(
        f"/authoring/versions/{v1['id']}/review",
        headers=auth(admin),
        json={"decision": "approve"},
    )

    v2 = client.post(
        f"/authoring/units/{unit['id']}/lessons",
        headers=auth(author),
        json={"slug": "evolving", "title": "V2", "blocks": sample_blocks()},
    ).json()
    assert v2["version"] == 2
    client.post(f"/authoring/versions/{v2['id']}/submit", headers=auth(author))
    client.post(
        f"/authoring/versions/{v2['id']}/review",
        headers=auth(admin),
        json={"decision": "approve"},
    )

    live = client.get(f"/lessons/{v1['lesson_id']}").json()
    assert live["title"] == "V2" and live["version"] == 2


def test_rejected_lesson_can_be_withdrawn_and_edited(client):
    admin, _course, unit = _setup_unit(client)
    author = register(client, "author@example.com")
    promote(client, "author@example.com", Role.author)

    draft = client.post(
        f"/authoring/units/{unit['id']}/lessons",
        headers=auth(author),
        json={"slug": "retry", "title": "Draft", "blocks": sample_blocks()},
    ).json()
    client.post(f"/authoring/versions/{draft['id']}/submit", headers=auth(author))
    client.post(
        f"/authoring/versions/{draft['id']}/review",
        headers=auth(admin),
        json={"decision": "reject", "notes": "needs a myth callout"},
    )

    back = client.post(
        f"/authoring/versions/{draft['id']}/withdraw", headers=auth(author)
    ).json()
    assert back["status"] == "draft"

    edited = client.patch(
        f"/authoring/versions/{draft['id']}",
        headers=auth(author),
        json={"title": "Revised"},
    )
    assert edited.status_code == 200 and edited.json()["title"] == "Revised"


# ------------------------------------------------------------------ delivery


def _publish(client, admin, unit, slug="lesson-one"):
    author = register(client, f"{slug}@example.com")
    promote(client, f"{slug}@example.com", Role.author)
    draft = client.post(
        f"/authoring/units/{unit['id']}/lessons",
        headers=auth(author),
        json={"slug": slug, "title": "Currents", "blocks": sample_blocks()},
    ).json()
    client.post(f"/authoring/versions/{draft['id']}/submit", headers=auth(author))
    client.post(
        f"/authoring/versions/{draft['id']}/review",
        headers=auth(admin),
        json={"decision": "approve"},
    )
    return draft["lesson_id"]


def test_answers_are_never_sent_to_the_client(client):
    admin, _course, unit = _setup_unit(client)
    lesson_id = _publish(client, admin, unit)
    payload = client.get(f"/lessons/{lesson_id}").text
    assert "correct" not in payload
    assert "explain" not in payload


GOOD = {
    "items": [
        {"item_id": "q1", "chosen": "Its field is tiny; many must fire together"},
        {"item_id": "q2", "chosen": "Attenuates and blurs it"},
    ]
}
BAD = {
    "items": [
        {"item_id": "q1", "chosen": "Neurons are not electrical"},
        {"item_id": "q2", "chosen": "Amplifies it to volts"},
    ]
}


def test_grading_awards_xp_and_starts_a_streak(client):
    admin, _course, unit = _setup_unit(client)
    lesson_id = _publish(client, admin, unit)
    learner = register(client, "learner@example.com")

    r = client.post(
        f"/lessons/{lesson_id}/attempts", headers=auth(learner), json=GOOD
    ).json()
    assert r["score"] == 1.0 and r["passed"] is True
    # 20 for passing + 10 first-completion bonus
    assert r["xp_awarded"] == 30
    assert r["total_xp"] == 30
    assert r["streak_days"] == 1
    assert all(item["explain"] for item in r["results"])


def test_failing_awards_no_xp(client):
    admin, _course, unit = _setup_unit(client)
    lesson_id = _publish(client, admin, unit)
    learner = register(client, "learner@example.com")
    r = client.post(
        f"/lessons/{lesson_id}/attempts", headers=auth(learner), json=BAD
    ).json()
    assert r["passed"] is False and r["xp_awarded"] == 0


def test_replaying_a_lesson_does_not_farm_the_first_time_bonus(client):
    admin, _course, unit = _setup_unit(client)
    lesson_id = _publish(client, admin, unit)
    learner = register(client, "learner@example.com")

    first = client.post(
        f"/lessons/{lesson_id}/attempts", headers=auth(learner), json=GOOD
    ).json()
    again = client.post(
        f"/lessons/{lesson_id}/attempts", headers=auth(learner), json=GOOD
    ).json()
    assert first["xp_awarded"] == 30
    assert again["xp_awarded"] == 20  # pass only, no bonus


def test_skipping_questions_does_not_inflate_the_score(client):
    admin, _course, unit = _setup_unit(client)
    lesson_id = _publish(client, admin, unit)
    learner = register(client, "learner@example.com")
    r = client.post(
        f"/lessons/{lesson_id}/attempts",
        headers=auth(learner),
        json={"items": [GOOD["items"][0]]},
    ).json()
    assert r["score"] == 0.5 and r["passed"] is False


def test_completion_is_sticky_across_a_worse_retry(client):
    admin, course, unit = _setup_unit(client)
    lesson_id = _publish(client, admin, unit)
    learner = register(client, "learner@example.com")
    client.post(f"/lessons/{lesson_id}/attempts", headers=auth(learner), json=GOOD)
    client.post(f"/lessons/{lesson_id}/attempts", headers=auth(learner), json=BAD)

    prog = client.get(f"/courses/{course['id']}/progress", headers=auth(learner)).json()
    assert prog["completed_lessons"] == 1
    assert prog["lessons"][0]["best_score"] == 1.0
    assert prog["lessons"][0]["attempts"] == 2


def test_stats_endpoint(client):
    admin, _course, unit = _setup_unit(client)
    lesson_id = _publish(client, admin, unit)
    learner = register(client, "learner@example.com")
    client.post(f"/lessons/{lesson_id}/attempts", headers=auth(learner), json=GOOD)

    stats = client.get("/me/stats", headers=auth(learner)).json()
    assert stats["xp"] == 30
    assert stats["streak_days"] == 1
    assert stats["longest_streak"] == 1
    assert stats["practiced_today"] is True
    assert stats["lessons_completed"] == 1


def test_unknown_question_id_is_rejected(client):
    admin, _course, unit = _setup_unit(client)
    lesson_id = _publish(client, admin, unit)
    learner = register(client, "learner@example.com")
    r = client.post(
        f"/lessons/{lesson_id}/attempts",
        headers=auth(learner),
        json={"items": [{"item_id": "q99", "chosen": "whatever"}]},
    )
    assert r.status_code == 422


def test_unpublished_lessons_do_not_count_toward_progress(client):
    admin, course, unit = _setup_unit(client)
    _publish(client, admin, unit, slug="published-one")
    client.post(
        f"/authoring/units/{unit['id']}/lessons",
        headers=auth(admin),
        json={"slug": "never-shipped", "title": "WIP", "blocks": sample_blocks()},
    )
    learner = register(client, "learner@example.com")
    prog = client.get(f"/courses/{course['id']}/progress", headers=auth(learner)).json()
    assert prog["total_lessons"] == 1


# ------------------------------------------------------------------ streaks
# Streak arithmetic is pure, so test it directly rather than through HTTP —
# simulating "yesterday" over the API would mean faking the system clock.


def _user(streak=0, longest=0, last=None):
    return User(
        email="s@example.com",
        display_name="S",
        password_hash="x",
        streak_days=streak,
        longest_streak=longest,
        last_active_on=last,
    )


def test_streak_starts_at_one():
    u = _user()
    touch_streak(u, date(2026, 9, 13))
    assert u.streak_days == 1 and u.longest_streak == 1


def test_second_activity_same_day_does_not_double_count():
    today = date(2026, 9, 13)
    u = _user(streak=3, longest=3, last=today)
    touch_streak(u, today)
    assert u.streak_days == 3


def test_consecutive_day_increments():
    u = _user(streak=3, longest=3, last=date(2026, 9, 12))
    touch_streak(u, date(2026, 9, 13))
    assert u.streak_days == 4 and u.longest_streak == 4


def test_missed_day_resets_to_one_not_zero():
    # Today's work still counted. Showing 0 right after someone practised
    # reads as a bug, not as a penalty.
    u = _user(streak=9, longest=9, last=date(2026, 9, 10))
    touch_streak(u, date(2026, 9, 13))
    assert u.streak_days == 1
    assert u.longest_streak == 9  # personal best survives


def test_reading_a_stale_streak_returns_zero():
    # The stored column goes stale the moment a day passes. A read must
    # recompute or someone who quit last week still sees "7 day streak".
    u = _user(streak=7, longest=7, last=date(2026, 9, 5))
    assert current_streak(u, date(2026, 9, 13)) == 0


def test_reading_yesterday_still_shows_the_streak():
    # Not broken yet — they have the rest of today to keep it.
    u = _user(streak=7, longest=7, last=date(2026, 9, 12))
    assert current_streak(u, date(2026, 9, 13)) == 7


# ----------------------------------------------------------------- security


@pytest.fixture(autouse=True)
def _clean_security_state():
    reset_rate_limits()
    reset_revocations()
    yield
    reset_rate_limits()
    reset_revocations()


def test_login_is_rate_limited(client):
    register(client, "target@example.com", password="correct-horse-battery")
    codes = [
        client.post(
            "/auth/login",
            json={"email": "target@example.com", "password": "wrong-password-x"},
        ).status_code
        for _ in range(12)
    ]
    # Eight attempts allowed, then the door closes.
    assert 429 in codes
    assert codes.count(401) <= 8


def test_rate_limit_returns_retry_after(client):
    for _ in range(12):
        r = client.post(
            "/auth/login", json={"email": "x@example.com", "password": "nope-nope-nope"}
        )
        if r.status_code == 429:
            assert r.headers.get("Retry-After", "").isdigit()
            return
    raise AssertionError("limiter never engaged")


def test_logout_revokes_the_token(client):
    token = register(client, "bye@example.com")
    assert client.get("/auth/me", headers=auth(token)).status_code == 200
    assert client.post("/auth/logout", headers=auth(token)).status_code == 204
    # The token is still cryptographically valid; it must be refused anyway.
    assert client.get("/auth/me", headers=auth(token)).status_code == 401


def test_security_headers_are_present(client):
    h = client.get("/health").headers
    assert h["X-Content-Type-Options"] == "nosniff"
    assert h["X-Frame-Options"] == "DENY"
    assert "max-age=" in h["Strict-Transport-Security"]
    assert "frame-ancestors 'none'" in h["Content-Security-Policy"]


def test_oversized_body_is_rejected(client):
    r = client.post(
        "/auth/register",
        content=b"x" * 2_000_000,
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 413


def test_account_deletion_requires_the_password(client):
    token = register(client, "gone@example.com", password="correct-horse-battery")
    bad = client.request(
        "DELETE", "/auth/me", headers=auth(token), json={"password": "not-the-one"}
    )
    assert bad.status_code == 403
    assert client.get("/auth/me", headers=auth(token)).status_code == 200


def test_account_deletion_removes_the_user_and_their_data(client):
    admin, _course, unit = _setup_unit(client)
    lesson_id = _publish(client, admin, unit)
    token = register(client, "gone@example.com", password="correct-horse-battery")
    client.post(f"/lessons/{lesson_id}/attempts", headers=auth(token), json=GOOD)

    r = client.request(
        "DELETE",
        "/auth/me",
        headers=auth(token),
        json={"password": "correct-horse-battery"},
    )
    assert r.status_code == 204
    # Token revoked, and the credentials no longer work.
    assert client.get("/auth/me", headers=auth(token)).status_code == 401
    assert client.post(
        "/auth/login",
        json={"email": "gone@example.com", "password": "correct-horse-battery"},
    ).status_code == 401


def test_deleting_an_author_keeps_their_published_lesson(client):
    admin, _course, unit = _setup_unit(client)
    author = register(client, "writer@example.com", password="correct-horse-battery")
    promote(client, "writer@example.com", Role.author)
    draft = client.post(
        f"/authoring/units/{unit['id']}/lessons",
        headers=auth(author),
        json={"slug": "keeps", "title": "Kept", "blocks": sample_blocks()},
    ).json()
    client.post(f"/authoring/versions/{draft['id']}/submit", headers=auth(author))
    client.post(
        f"/authoring/versions/{draft['id']}/review",
        headers=auth(admin),
        json={"decision": "approve"},
    )

    client.request(
        "DELETE",
        "/auth/me",
        headers=auth(author),
        json={"password": "correct-horse-battery"},
    )

    # Deleting the author must not break learners mid-course.
    lesson = client.get(f"/lessons/{draft['lesson_id']}")
    assert lesson.status_code == 200
    assert lesson.json()["author_name"] == "Former contributor"
