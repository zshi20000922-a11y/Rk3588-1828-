from __future__ import annotations

import json
from typing import Any, Awaitable, Callable

from .database import Database, now_iso


ToolHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class ToolRegistry:
    def __init__(self, db: Database):
        self.db = db
        self.handlers: dict[str, tuple[ToolHandler, bool]] = {}

    def register(self, name: str, handler: ToolHandler, confirmation: bool = False) -> None:
        self.handlers[name] = (handler, confirmation)

    def describe(self) -> list[dict[str, Any]]:
        return [{"name": name, "requires_confirmation": value[1]} for name, value in self.handlers.items()]

    async def execute(self, name: str, arguments: dict[str, Any], request_id: str,
                      conversation_id: str | None, confirmed: bool) -> dict[str, Any]:
        outcome: dict[str, Any]
        try:
            handler, needs_confirmation = self.handlers[name]
            if needs_confirmation and not confirmed:
                outcome = {"ok": False, "confirmation_required": True}
            else:
                outcome = await handler(arguments)
        except KeyError:
            outcome = {"ok": False, "error": "tool_not_allowed"}
        except Exception as exc:  # audited boundary; internal details stay local
            outcome = {"ok": False, "error": type(exc).__name__}
        self.db.execute("INSERT INTO audit_log(request_id, conversation_id, tool, arguments, outcome, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                        (request_id, conversation_id, name, json.dumps(arguments, ensure_ascii=False),
                         json.dumps(outcome, ensure_ascii=False), now_iso()))
        return outcome

