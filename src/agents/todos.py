import uuid

from .base import BaseAgent
from ..db.database import get_connection


class TodoAgent(BaseAgent):
    name = "todos"
    description = (
        "Manage tasks/todos. Add, list, complete, delete tasks. "
        "Tasks are persistent items without a specific time (unlike reminders). "
        "Priority: high, medium, low. Status: pending, in_progress, done."
    )

    def __init__(self, user_id: str):
        self.user_id = user_id

    async def execute(self, action: str, params: dict) -> dict:
        fn = getattr(self, f"_handle_{action}", None)
        if fn is None:
            return {"error": f"Unknown action: {action}"}
        return fn(params)

    def _handle_add(self, p: dict) -> dict:
        title = p.get("title", "")
        if not title:
            return {"error": "title is required"}
        priority = p.get("priority", "medium")
        if priority not in ("high", "medium", "low"):
            priority = "medium"
        notes = p.get("notes", "")

        tid = str(uuid.uuid4())[:8]
        conn = get_connection()
        conn.execute(
            "INSERT INTO todos (id, user_id, title, notes, priority) VALUES (?,?,?,?,?)",
            (tid, self.user_id, title, notes, priority),
        )
        conn.commit()
        conn.close()
        return {"status": "created", "id": tid, "title": title, "priority": priority}

    def _handle_list(self, p: dict) -> dict:
        show_done = p.get("show_done", False)
        conn = get_connection()
        query = "SELECT id, title, priority, status, notes FROM todos WHERE user_id=?"
        params: list = [self.user_id]
        if not show_done:
            query += " AND status != 'done'"
        query += " ORDER BY CASE priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, created_at ASC"
        rows = conn.execute(query, params).fetchall()
        conn.close()
        return {"status": "ok", "count": len(rows), "todos": [dict(r) for r in rows]}

    def _handle_complete(self, p: dict) -> dict:
        tid = p.get("todo_id", "")
        title = p.get("title", "")
        conn = get_connection()
        if tid:
            conn.execute(
                "UPDATE todos SET status='done', updated_at=datetime('now') WHERE id=? AND user_id=?",
                (tid, self.user_id),
            )
        elif title:
            count = conn.execute(
                "SELECT COUNT(*) as c FROM todos WHERE title=? AND user_id=? AND status!='done'",
                (title, self.user_id),
            ).fetchone()
            if count and count["c"] > 1:
                conn.close()
                return {
                    "error": f"Multiple tasks named '{title}'. Use todo_id from list."
                }
            conn.execute(
                "UPDATE todos SET status='done', updated_at=datetime('now') WHERE title=? AND user_id=?",
                (title, self.user_id),
            )
        changed = conn.total_changes
        conn.commit()
        conn.close()
        return {"status": "completed" if changed else "not_found"}

    def _handle_start(self, p: dict) -> dict:
        tid = p.get("todo_id", "")
        if not tid:
            return {"error": "todo_id is required"}
        conn = get_connection()
        conn.execute(
            "UPDATE todos SET status='in_progress', updated_at=datetime('now') WHERE id=? AND user_id=?",
            (tid, self.user_id),
        )
        conn.commit()
        conn.close()
        return {"status": "started", "id": tid}

    def _handle_delete(self, p: dict) -> dict:
        tid = p.get("todo_id", "")
        conn = get_connection()
        conn.execute("DELETE FROM todos WHERE id=? AND user_id=?", (tid, self.user_id))
        conn.commit()
        conn.close()
        return {"status": "deleted", "id": tid}

    @staticmethod
    def get_pending_for(user_id: str) -> list[dict]:
        conn = get_connection()
        rows = conn.execute(
            "SELECT id, title, priority, status FROM todos WHERE user_id=? AND status!='done' "
            "ORDER BY CASE priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, created_at ASC LIMIT 5",
            (user_id,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def get_pending_count(user_id: str) -> int:
        conn = get_connection()
        row = conn.execute(
            "SELECT COUNT(*) as c FROM todos WHERE user_id=? AND status!='done'",
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
                            "enum": ["add", "list", "complete", "start", "delete"],
                            "description": "Action: add, list, complete, start, delete",
                        },
                        "title": {
                            "type": "string",
                            "description": "Task title",
                        },
                        "notes": {
                            "type": "string",
                            "description": "Optional notes/details",
                        },
                        "priority": {
                            "type": "string",
                            "enum": ["high", "medium", "low"],
                            "description": "Task priority (default medium)",
                        },
                        "todo_id": {
                            "type": "string",
                            "description": "ID from list to complete/start/delete",
                        },
                        "show_done": {
                            "type": "boolean",
                            "description": "Include completed tasks",
                        },
                    },
                    "required": ["action"],
                },
            },
        }
