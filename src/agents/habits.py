import uuid
from datetime import date, timedelta

from .base import BaseAgent
from ..db.database import get_connection


class HabitsAgent(BaseAgent):
    name = "habits"
    description = (
        "Track daily habits. Add, check in, skip, view status and streaks. "
        "Use checkin when user did the habit today, skip when they didn't."
    )

    def __init__(self, user_id: str):
        self.user_id = user_id

    async def execute(self, action: str, params: dict) -> dict:
        fn = getattr(self, f"_handle_{action}", None)
        if fn is None:
            return {"error": f"Unknown action: {action}"}
        return fn(params)

    def _handle_add(self, p: dict) -> dict:
        name = p.get("name", "")
        target = p.get("target", "")
        if not name:
            return {"error": "name is required"}

        hid = str(uuid.uuid4())[:8]
        conn = get_connection()
        conn.execute(
            "INSERT INTO habits (id, user_id, name, target) VALUES (?,?,?,?)",
            (hid, self.user_id, name, target),
        )
        conn.commit()
        conn.close()
        return {"status": "created", "id": hid, "name": name, "target": target}

    def _handle_checkin(self, p: dict) -> dict:
        name = p.get("name", "")
        if not name:
            return {"error": "name is required"}

        today_str = date.today().isoformat()
        conn = get_connection()
        row = conn.execute(
            "SELECT id, streak, best_streak FROM habits WHERE user_id=? AND name=?",
            (self.user_id, name),
        ).fetchone()

        if not row:
            conn.close()
            return {"error": f"Habit '{name}' not found"}

        hid = row["id"]
        streak = row["streak"]
        best = row["best_streak"]

        existing = conn.execute(
            "SELECT id FROM habit_logs WHERE habit_id=? AND date=?",
            (hid, today_str),
        ).fetchone()

        if existing:
            conn.close()
            return {"status": "already_checked", "name": name, "streak": streak}

        yesterday = (date.today() - timedelta(days=1)).isoformat()
        yesterday_log = conn.execute(
            "SELECT id FROM habit_logs WHERE habit_id=? AND date=?",
            (hid, yesterday),
        ).fetchone()

        if yesterday_log:
            streak += 1
        else:
            streak = 1
        best = max(best, streak)

        conn.execute(
            "INSERT OR REPLACE INTO habit_logs (id, habit_id, date, status) VALUES (?,?,?,?)",
            (str(uuid.uuid4())[:8], hid, today_str, "done"),
        )
        conn.execute(
            "UPDATE habits SET streak=?, best_streak=?, last_checkin=? WHERE id=?",
            (streak, best, today_str, hid),
        )
        conn.commit()
        conn.close()
        return {"status": "checked_in", "name": name, "streak": streak, "best": best}

    def _handle_skip(self, p: dict) -> dict:
        name = p.get("name", "")
        if not name:
            return {"error": "name is required"}

        today_str = date.today().isoformat()
        conn = get_connection()
        row = conn.execute(
            "SELECT id FROM habits WHERE user_id=? AND name=?",
            (self.user_id, name),
        ).fetchone()

        if not row:
            conn.close()
            return {"error": f"Habit '{name}' not found"}

        hid = row["id"]
        conn.execute(
            "INSERT OR REPLACE INTO habit_logs (id, habit_id, date, status) VALUES (?,?,?,?)",
            (str(uuid.uuid4())[:8], hid, today_str, "skipped"),
        )
        conn.execute(
            "UPDATE habits SET streak=0, last_checkin=? WHERE id=?", (today_str, hid)
        )
        conn.commit()
        conn.close()
        return {"status": "skipped", "name": name, "streak": 0}

    def _handle_status(self, p: dict) -> dict:
        today_str = date.today().isoformat()
        conn = get_connection()
        rows = conn.execute(
            "SELECT id, name, target, streak, best_streak FROM habits WHERE user_id=? ORDER BY name",
            (self.user_id,),
        ).fetchall()

        result = []
        for r in rows:
            check = conn.execute(
                "SELECT status FROM habit_logs WHERE habit_id=? AND date=?",
                (r["id"], today_str),
            ).fetchone()
            result.append(
                {
                    "name": r["name"],
                    "target": r["target"],
                    "streak": r["streak"],
                    "best_streak": r["best_streak"],
                    "today": check["status"] if check else "pending",
                }
            )
        conn.close()
        return {"status": "ok", "count": len(result), "habits": result}

    def _handle_remove(self, p: dict) -> dict:
        name = p.get("name", "")
        conn = get_connection()
        conn.execute(
            "DELETE FROM habits WHERE user_id=? AND name=?", (self.user_id, name)
        )
        conn.commit()
        conn.close()
        return {"status": "removed", "name": name}

    def _handle_history(self, p: dict) -> dict:
        name = p.get("name", "")
        if not name:
            return {"error": "name is required"}
        conn = get_connection()
        row = conn.execute(
            "SELECT id FROM habits WHERE user_id=? AND name=?", (self.user_id, name)
        ).fetchone()
        if not row:
            conn.close()
            return {"error": f"Habit '{name}' not found"}
        rows = conn.execute(
            "SELECT date, status FROM habit_logs WHERE habit_id=? ORDER BY date DESC LIMIT 14",
            (row["id"],),
        ).fetchall()
        conn.close()
        return {"status": "ok", "name": name, "history": [dict(r) for r in rows]}

    @staticmethod
    def get_pending_for(user_id: str) -> list[dict]:
        today_str = date.today().isoformat()
        conn = get_connection()
        rows = conn.execute(
            "SELECT h.id, h.name, h.target, h.streak, h.best_streak, "
            "COALESCE(hl.status, 'pending') as today_status "
            "FROM habits h "
            "LEFT JOIN habit_logs hl ON h.id = hl.habit_id AND hl.date = ? "
            "WHERE h.user_id = ? ORDER BY h.name",
            (today_str, user_id),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def get_users_with_pending() -> list[tuple[str, list[dict]]]:
        today_str = date.today().isoformat()
        conn = get_connection()
        rows = conn.execute(
            "SELECT DISTINCT h.user_id FROM habits h "
            "LEFT JOIN habit_logs hl ON h.id = hl.habit_id AND hl.date = ? "
            "WHERE hl.id IS NULL",
            (today_str,),
        ).fetchall()
        result = []
        for r in rows:
            uid = r["user_id"]
            pending = HabitsAgent.get_pending_for(uid)
            unanswered = [h for h in pending if h["today_status"] == "pending"]
            if unanswered:
                result.append((uid, unanswered))
        conn.close()
        return result

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
                            "enum": [
                                "add",
                                "checkin",
                                "skip",
                                "status",
                                "remove",
                                "history",
                            ],
                            "description": "Action to perform on habits",
                        },
                        "name": {
                            "type": "string",
                            "description": "Habit name (e.g. 'exercicio', 'agua')",
                        },
                        "target": {
                            "type": "string",
                            "description": "Target for add (e.g. '30min', '2L')",
                        },
                    },
                    "required": ["action"],
                },
            },
        }
