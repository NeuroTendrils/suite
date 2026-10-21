"""Runtime configuration.

Copyright 2026 NeuroTendrils
SPDX-License-Identifier: AGPL-3.0-or-later
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field


@dataclass
class Settings:
    database_url: str = field(
        default_factory=lambda: os.getenv("NEUROLEARN_DATABASE_URL", "sqlite:///./neurolearn.db")
    )
    # A generated secret means every restart invalidates tokens. That is a safe
    # default for dev and an obvious failure in prod, which is what we want —
    # far better than shipping a hardcoded key someone forgets to change.
    jwt_secret: str = field(
        default_factory=lambda: os.getenv("NEUROLEARN_JWT_SECRET") or secrets.token_urlsafe(48)
    )
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = int(os.getenv("NEUROLEARN_TOKEN_MINUTES", "10080"))
    cors_origins: list[str] = field(
        default_factory=lambda: [
            o for o in os.getenv("NEUROLEARN_CORS", "http://localhost:5174").split(",") if o
        ]
    )

    @property
    def secret_is_ephemeral(self) -> bool:
        return os.getenv("NEUROLEARN_JWT_SECRET") is None


settings = Settings()
