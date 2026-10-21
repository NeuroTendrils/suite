"""Lesson content validation.

Copyright 2026 NeuroTendrils
SPDX-License-Identifier: AGPL-3.0-or-later

This module is the trust boundary for community-authored content. Anything a
member submits passes through here before it touches the database.

Rules that matter:

* **Allowlist, never denylist.** Unknown block types are rejected outright.
  A denylist of "dangerous" types fails the moment someone invents a new one.
* **No raw HTML, ever.** Prose is plain text with a tiny inline markup
  vocabulary the client renders itself. That removes script injection as a
  category rather than trying to sanitize it.
* **Simulations are referenced by id, not supplied.** A lesson can say
  "run the band playground"; it cannot ship code.
* **Pedagogical minimums are enforced.** A quiz needs at least two options
  and exactly one correct answer, and every question needs an explanation.
  Content that cannot teach is not a formatting problem, it is invalid.
"""

from __future__ import annotations

import re
from typing import Any

# Simulations the client knows how to run. Adding one here is a deliberate
# release decision, which is the point.
REGISTERED_SIMS = {
    "artifact-detective",
    "band-playground",
    "filter-playground",
    "closed-loop",
}

CALLOUT_KINDS = {"tip", "limit", "myth", "warning"}
BLOCK_TYPES = {"hook", "heading", "prose", "callout", "figure", "sim", "check"}

MAX_BLOCKS = 60
MAX_PROSE_CHARS = 4000
MAX_CHOICES = 6
MIN_CHOICES = 2

# Inline markup the renderer supports: **bold**, *italic*, `code`, [[glossary]].
_HTML_TAG = re.compile(r"<[^>]+>")
_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class ContentError(ValueError):
    """Raised with a path so the author knows which block to fix."""

    def __init__(self, path: str, message: str) -> None:
        super().__init__(f"{path}: {message}")
        self.path = path
        self.message = message


def _require(condition: bool, path: str, message: str) -> None:
    if not condition:
        raise ContentError(path, message)


def _text(value: Any, path: str, *, limit: int = MAX_PROSE_CHARS) -> str:
    _require(isinstance(value, str), path, "must be text")
    _require(value.strip() != "", path, "must not be empty")
    _require(len(value) <= limit, path, f"must be under {limit} characters")
    _require(
        _HTML_TAG.search(value) is None,
        path,
        "HTML is not allowed — use **bold**, *italic*, `code`, or [[glossary]]",
    )
    return value.strip()


def validate_slug(slug: str, path: str = "slug") -> str:
    _require(isinstance(slug, str) and bool(_SLUG.match(slug)), path,
             "must be lowercase words separated by hyphens")
    _require(len(slug) <= 80, path, "must be under 80 characters")
    return slug


# --------------------------------------------------------------- block types


def _validate_check(block: dict, path: str) -> dict:
    questions = block.get("questions")
    _require(isinstance(questions, list) and len(questions) > 0, f"{path}.questions",
             "a check needs at least one question")
    _require(len(questions) <= 12, f"{path}.questions", "at most 12 questions")

    pass_score = block.get("pass_score", 0.7)
    _require(isinstance(pass_score, (int, float)) and 0 < float(pass_score) <= 1,
             f"{path}.pass_score", "must be between 0 and 1")

    seen: set[str] = set()
    clean_questions = []
    for i, q in enumerate(questions):
        qp = f"{path}.questions[{i}]"
        _require(isinstance(q, dict), qp, "must be an object")

        qid = q.get("id")
        _require(isinstance(qid, str) and qid.strip() != "", f"{qp}.id", "is required")
        _require(qid not in seen, f"{qp}.id", f"duplicate question id {qid!r}")
        seen.add(qid)

        prompt = _text(q.get("prompt"), f"{qp}.prompt", limit=600)
        # An explanation is mandatory. A quiz that only marks you wrong is a
        # test; the explanation is what makes it teaching.
        explain = _text(q.get("explain"), f"{qp}.explain", limit=900)

        choices = q.get("choices")
        _require(isinstance(choices, list), f"{qp}.choices", "must be a list")
        _require(MIN_CHOICES <= len(choices) <= MAX_CHOICES, f"{qp}.choices",
                 f"needs between {MIN_CHOICES} and {MAX_CHOICES} options")

        clean_choices = []
        correct_count = 0
        for j, c in enumerate(choices):
            cp = f"{qp}.choices[{j}]"
            _require(isinstance(c, dict), cp, "must be an object")
            label = _text(c.get("text"), f"{cp}.text", limit=300)
            is_correct = bool(c.get("correct", False))
            correct_count += int(is_correct)
            clean_choices.append({"text": label, "correct": is_correct})

        _require(correct_count == 1, f"{qp}.choices",
                 f"exactly one option must be correct (found {correct_count})")

        clean_questions.append({
            "id": qid,
            "prompt": prompt,
            "explain": explain,
            "choices": clean_choices,
        })

    return {"type": "check", "pass_score": float(pass_score), "questions": clean_questions}


def _validate_block(block: Any, path: str) -> dict:
    _require(isinstance(block, dict), path, "must be an object")
    kind = block.get("type")
    _require(kind in BLOCK_TYPES, f"{path}.type",
             f"unknown block type {kind!r} — allowed: {', '.join(sorted(BLOCK_TYPES))}")

    if kind == "hook":
        return {"type": "hook", "text": _text(block.get("text"), f"{path}.text", limit=500)}

    if kind == "heading":
        return {"type": "heading", "text": _text(block.get("text"), f"{path}.text", limit=200)}

    if kind == "prose":
        return {"type": "prose", "text": _text(block.get("text"), f"{path}.text")}

    if kind == "callout":
        ckind = block.get("kind")
        _require(ckind in CALLOUT_KINDS, f"{path}.kind",
                 f"must be one of {', '.join(sorted(CALLOUT_KINDS))}")
        return {
            "type": "callout",
            "kind": ckind,
            "text": _text(block.get("text"), f"{path}.text", limit=1200),
        }

    if kind == "figure":
        asset = block.get("asset")
        _require(isinstance(asset, str) and asset.strip() != "", f"{path}.asset",
                 "is required")
        _require("://" not in asset and not asset.startswith("/"), f"{path}.asset",
                 "must be a pack-relative path, not a URL")
        _require(".." not in asset, f"{path}.asset", "must not traverse directories")
        # Alt text is not optional. A figure nobody can describe is not content.
        return {
            "type": "figure",
            "asset": asset,
            "alt": _text(block.get("alt"), f"{path}.alt", limit=300),
            "caption": block.get("caption", "") and
                       _text(block.get("caption"), f"{path}.caption", limit=400),
        }

    if kind == "sim":
        sim_id = block.get("sim_id")
        _require(sim_id in REGISTERED_SIMS, f"{path}.sim_id",
                 f"unknown simulation {sim_id!r} — registered: "
                 f"{', '.join(sorted(REGISTERED_SIMS))}")
        return {
            "type": "sim",
            "sim_id": sim_id,
            "goal": _text(block.get("goal"), f"{path}.goal", limit=300),
        }

    return _validate_check(block, path)


# ------------------------------------------------------------------ lesson


def validate_lesson_blocks(blocks: Any) -> list[dict]:
    """Validate and normalize a block list. Raises ContentError on the first problem."""
    _require(isinstance(blocks, list), "blocks", "must be a list")
    _require(len(blocks) > 0, "blocks", "a lesson needs at least one block")
    _require(len(blocks) <= MAX_BLOCKS, "blocks", f"at most {MAX_BLOCKS} blocks")

    clean = [_validate_block(b, f"blocks[{i}]") for i, b in enumerate(blocks)]

    # A lesson without a check cannot record mastery, so it cannot be published.
    _require(
        any(b["type"] == "check" for b in clean),
        "blocks",
        "a lesson needs at least one check so progress can be recorded",
    )
    return clean


def quiz_items(blocks: list[dict]) -> dict[str, str]:
    """Map question id -> correct choice text, for grading on the server.

    Correct answers never leave the server during a lesson; the client submits
    choices and receives results.
    """
    answers: dict[str, str] = {}
    for block in blocks:
        if block.get("type") != "check":
            continue
        for q in block["questions"]:
            for choice in q["choices"]:
                if choice["correct"]:
                    answers[q["id"]] = choice["text"]
    return answers


def strip_answers(blocks: list[dict]) -> list[dict]:
    """Public view of a lesson: identical, minus which option is correct."""
    out = []
    for block in blocks:
        if block.get("type") != "check":
            out.append(block)
            continue
        out.append({
            "type": "check",
            "pass_score": block["pass_score"],
            "questions": [
                {
                    "id": q["id"],
                    "prompt": q["prompt"],
                    "choices": [{"text": c["text"]} for c in q["choices"]],
                }
                for q in block["questions"]
            ],
        })
    return out
