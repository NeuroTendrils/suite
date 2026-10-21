"""Application entrypoint.

Copyright 2026 NeuroTendrils
SPDX-License-Identifier: AGPL-3.0-or-later
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from neurolearn_api import __version__
from neurolearn_api.config import settings
from neurolearn_api.db import init_db
from neurolearn_api.routers import auth, authoring, catalog, learning
from neurolearn_api.security_middleware import (
    BodySizeLimitMiddleware,
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
)

log = logging.getLogger("neurolearn")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    if settings.secret_is_ephemeral:
        log.warning(
            "NEUROLEARN_JWT_SECRET is unset — using a generated key. "
            "Every restart will sign users out. Set it before deploying."
        )
    yield


app = FastAPI(
    title="NeuroLearn API",
    version=__version__,
    summary="Accounts, community-authored lessons, and progress for NeuroLearn.",
    lifespan=lifespan,
)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(BodySizeLimitMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    # Explicit rather than "*". A wildcard here plus credentials is the
    # classic way to hand an attacker's page a working session.
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth.router)
app.include_router(authoring.router)
app.include_router(catalog.router)
app.include_router(learning.router)


@app.get("/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok", "version": __version__}
