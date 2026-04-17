from __future__ import annotations

from typing import Any


def get_users() -> list[dict[str, Any]]:
    return [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]


def get_user(user_id: int) -> dict[str, Any] | None:
    users = get_users()
    return next((u for u in users if u["id"] == user_id), None)
