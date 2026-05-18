import uuid
from datetime import datetime, timedelta, timezone as tz

import dateparser

from .base import BaseAgent
from ..db.database import get_connection
from ..memory.profile import ProfileManager

UTC = tz.utc
RECURRENCE_DELTA = {
    "daily": timedelta(days=1),
    "weekly": timedelta(weeks=1),
    "monthly": timedelta(days=30),
}


def _now_utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M")


def parse_date(text: str, user_tz: str | None) -> str | None:
    settings = {"PREFER_DATES_FROM": "future"}
    if user_tz:
        settings["TIMEZONE"] = user_tz
    try:
        dt = dateparser.parse(text, settings=settings)
        if dt is None:
            return None
        if dt.tzinfo:
            dt = dt.astimezone(UTC)
        else:
            dt = dt.replace(tzinfo=UTC)
        return dt.strftime("%Y-%m-%dT%H:%M")
    except Exception:
        return None


class ReminderAgent(BaseAgent):
    name = "reminders"
    description = (
        "Manage reminders. Create, list, cancel reminders. "
        "trigger_at is the NOTIFICATION time (when to send the reminder to the user), "
        "not necessarily the event time. Pass natural language like 'tomorrow at 9:30' "
        "or ISO format: YYYY-MM-DDTHH:MM."
    )

    def __init__(self, user_id: str):
        self.user_id = user_id

    def _tz(self) -> str | None:
        p = ProfileManager(self.user_id).get()
        return p.timezone or None

    async def execute(self, action: str, params: dict) -> dict:
        fn = getattr(self, f"_handle_{action}", None)
        if fn is None:
            return {"error": f"Unknown action: {action}"}
        return fn(params)

    def _handle_create(self, p: dict) -> dict:
        message = p.get("message", "")
        raw_trigger = p.get("trigger_at", "")
        recurrence = p.get("recurrence")

        if not message or not raw_trigger:
            return {"error": "message and trigger_at are required"}

        if recurrence and recurrence not in RECURRENCE_DELTA:
            return {"error": f"Invalid recurrence: {recurrence}. Use daily, weekly, monthly."}

        trigger_at = parse_date(raw_trigger, self._tz())
        if trigger_at is None:
            trigger_at = raw_trigger

        rid = str(uuid.uuid4())[:8]
        conn = get_connection()
        conn.execute(
            "INSERT INTO reminders (id, user_id, message, trigger_at, recurrence) VALUES (?,?,?,?,?)",
            (rid, self.user_id, message, trigger_at, recurrence),
        )
        conn.commit()
        conn.close()
        return {
            "status": "created",
            "id": rid,
            "message": message,
            "trigger_at": trigger_at,
        }

    def _handle_list(self, p: dict) -> dict:
        conn = get_connection()
        rows = conn.execute(
            "SELECT id, message, trigger_at, recurrence, notified "
            "FROM reminders WHERE user_id=? ORDER BY trigger_at",
            (self.user_id,),
        ).fetchall()
        conn.close()
        return {
            "status": "ok",
            "count": len(rows),
            "reminders": [dict(r) for r in rows],
        }

    def _handle_list_pending(self, p: dict) -> dict:
        conn = get_connection()
        rows = conn.execute(
            "SELECT id, message, trigger_at FROM reminders "
            "WHERE user_id=? AND notified=0 ORDER BY trigger_at",
            (self.user_id,),
        ).fetchall()
        conn.close()
        return {
            "status": "ok",
            "count": len(rows),
            "reminders": [dict(r) for r in rows],
        }

    def _handle_cancel(self, p: dict) -> dict:
        rid = p.get("reminder_id", "")
        conn = get_connection()
        cur = conn.execute(
            "DELETE FROM reminders WHERE id=? AND user_id=?",
            (rid, self.user_id),
        )
        conn.commit()
        conn.close()
        return {"status": "cancelled" if cur.rowcount else "not_found", "id": rid}

    @staticmethod
    def get_due():
        conn = get_connection()
        now = _now_utc()
        rows = conn.execute(
            "SELECT id, user_id, message, recurrence "
            "FROM reminders WHERE trigger_at <= ? AND notified = 0",
            (now,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def mark_notified(rid: str):
        conn = get_connection()
        row = conn.execute(
            "SELECT recurrence, trigger_at FROM reminders WHERE id=?", (rid,)
        ).fetchone()
        if not row:
            conn.close()
            return

        recurrence = row["recurrence"]
        if recurrence and recurrence in RECURRENCE_DELTA:
            next_ts = dateparser.parse(
                row["trigger_at"],
                settings={"PREFER_DATES_FROM": "future"},
            )
            if next_ts:
                next_ts += RECURRENCE_DELTA[recurrence]
                new_trigger = next_ts.strftime("%Y-%m-%dT%H:%M")
                conn.execute(
                    "UPDATE reminders SET trigger_at=?, notified=0 WHERE id=?",
                    (new_trigger, rid),
                )
                conn.commit()
                conn.close()
                return

        conn.execute("UPDATE reminders SET notified = 1 WHERE id = ?", (rid,))
        conn.commit()
        conn.close()

    @staticmethod
    def get_for_day_range(user_id: str, start: str, end: str) -> list[dict]:
        conn = get_connection()
        rows = conn.execute(
            "SELECT id, message, trigger_at, recurrence "
            "FROM reminders WHERE user_id=? AND trigger_at >= ? AND trigger_at < ? "
            "AND notified=0 ORDER BY trigger_at",
            (user_id, start, end),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def get_pending_count(user_id: str) -> int:
        conn = get_connection()
        row = conn.execute(
            "SELECT COUNT(*) as c FROM reminders WHERE user_id=? AND notified=0",
            (user_id,),
        ).fetchone()
        conn.close()
        return row["c"] if row else 0

    def get_tool_definition(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["create", "list", "list_pending", "cancel"],
                            "description": "Action to perform on reminders",
                        },
                        "message": {
                            "type": "string",
                            "description": "Reminder message text",
                        },
                        "trigger_at": {
                            "type": "string",
                            "description": (
                                "When to notify. Natural language (e.g. 'tomorrow at 9:30', "
                                "'in 2 hours') OR ISO (2026-05-19T08:00). "
                                "This is the NOTIFICATION time, not the event time."
                            ),
                        },
                        "recurrence": {
                            "type": "string",
                            "description": "daily, weekly, monthly or null",
                        },
                        "reminder_id": {
                            "type": "string",
                            "description": "ID from list to cancel",
                        },
                    },
                    "required": ["action"],
                },
            },
        }