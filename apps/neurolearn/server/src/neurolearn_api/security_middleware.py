"""Security middleware and abuse controls.

Copyright 2026 NeuroTendrils
SPDX-License-Identifier: AGPL-3.0-or-later

Covers the gaps that matter most for a public, internet-facing API:

* Login brute force. Without a limiter, an unauthenticated attacker can try
  passwords as fast as the network allows.
* Token revocation. A plain JWT is valid until it expires, so "log out" does
  nothing server-side and a stolen token stays live for its full lifetime.
* Response headers a browser needs to behave defensively.

Deliberately NOT solved here, so nobody mistakes this file for completeness:

* The rate limiter is in-process. Two workers means two independent buckets,
  and a restart clears them. Move to Redis before running more than one
  instance — this is a real limitation, not a placeholder comment.
* The revocation list is also in-process, same caveat.
* No CAPTCHA, no device fingerprinting, no anomaly detection.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass

from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

# ------------------------------------------------------------ rate limiting


@dataclass(frozen=True)
class Limit:
    times: int
    seconds: int


# Login is the expensive one to get wrong. Registration is limited too, or a
# script can fill the users table overnight.
LIMITS: dict[str, Limit] = {
    "/auth/login": Limit(times=8, seconds=300),
    "/auth/register": Limit(times=5, seconds=3600),
    "/auth/password-reset": Limit(times=3, seconds=3600),
}

_hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)


def client_key(request: Request) -> str:
    """Identify the caller for limiting purposes.

    Behind a load balancer the socket address is the balancer, so the real
    client comes from X-Forwarded-For. Only the first entry is trusted, and
    only because the proxy is expected to overwrite the header — if yours
    appends instead, this is spoofable and must be changed.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def check_rate_limit(request: Request) -> None:
    limit = LIMITS.get(request.url.path)
    if limit is None:
        return

    key = (request.url.path, client_key(request))
    now = time.monotonic()
    bucket = _hits[key]

    while bucket and now - bucket[0] > limit.seconds:
        bucket.popleft()

    if len(bucket) >= limit.times:
        retry_after = int(limit.seconds - (now - bucket[0])) + 1
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "too many attempts — try again later",
            headers={"Retry-After": str(retry_after)},
        )
    bucket.append(now)


def reset_rate_limits() -> None:
    """Clear all buckets. For tests only."""
    _hits.clear()


# -------------------------------------------------------- token revocation


_revoked: dict[str, float] = {}


def revoke(jti: str, expires_at: float) -> None:
    """Mark a token dead until it would have expired anyway."""
    _revoked[jti] = expires_at
    _sweep()


def is_revoked(jti: str | None) -> bool:
    if jti is None:
        # Tokens issued before revocation existed have no jti. Treat them as
        # valid rather than locking everyone out on deploy; they age out.
        return False
    return jti in _revoked


def _sweep() -> None:
    """Drop entries past their natural expiry so the map cannot grow forever."""
    now = time.time()
    for jti, exp in list(_revoked.items()):
        if exp < now:
            del _revoked[jti]


def reset_revocations() -> None:
    """For tests only."""
    _revoked.clear()


# -------------------------------------------------------------- middleware


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Headers that tell a browser to behave defensively.

    This is an API, so the CSP is restrictive by design — nothing here should
    ever be rendered as a page. The docs endpoints are exempt because Swagger
    loads its own scripts and styles.
    """

    DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=(), interest-cohort=()"
        )
        # Tell browsers to refuse plain HTTP for a year. Only meaningful once
        # TLS is actually terminated in front of this.
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )

        if not request.url.path.startswith(self.DOCS_PATHS):
            response.headers["Content-Security-Policy"] = (
                "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
            )
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        try:
            check_rate_limit(request)
        except HTTPException as exc:
            from starlette.responses import JSONResponse

            return JSONResponse(
                {"detail": exc.detail},
                status_code=exc.status_code,
                headers=exc.headers or {},
            )
        return await call_next(request)


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject oversized bodies before they are parsed.

    Lesson content is the only large payload this API accepts, and a lesson
    that needs more than a megabyte is a mistake or an attack.
    """

    MAX_BYTES = 1_048_576  # 1 MiB

    async def dispatch(self, request: Request, call_next) -> Response:
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > self.MAX_BYTES:
            from starlette.responses import JSONResponse

            return JSONResponse(
                {"detail": "request body too large"},
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )
        return await call_next(request)
