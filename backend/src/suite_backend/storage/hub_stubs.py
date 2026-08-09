"""Hub / Teams interfaces — not implemented (no cloud)."""

from __future__ import annotations

from typing import Any


class LocalSharingProvider:
    def publish(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"status": "not_available", "message": "Hub publishing is not available locally"}


class LocalQuotaProvider:
    def get_quota(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "status": "not_available",
            "free_tier_bytes": 1_073_741_824,
            "message": "Hub quota enforced only when cloud exists",
        }


class LocalTeamRepository:
    def list_teams(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"status": "not_available", "teams": []}
