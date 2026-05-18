import uuid

from .base import BaseAgent
from ..db.database import get_connection


def get_all_user_ids() -> list[str]:
    from pathlib import Path
    from ..config import settings
    pd = Path(settings.data_dir) / "profiles"
    if not pd.exists():
        return []
    return [p.stem for p in pd.glob("*.json")]


class ShoppingAgent(BaseAgent):
    name = "shopping"
    description = (
        "Manage shopping lists: create lists, add/remove items, toggle bought."
    )

    def __init__(self, user_id: str):
        self.user_id = user_id

    async def execute(self, action: str, params: dict) -> dict:
        fn = getattr(self, f"_handle_{action}", None)
        if fn is None:
            return {"error": f"Unknown action: {action}"}
        return fn(params)

    def _handle_create_list(self, p: dict) -> dict:
        name = p.get("list_name", "default")
        lid = str(uuid.uuid4())[:8]
        conn = get_connection()
        conn.execute(
            "INSERT INTO shopping_lists (id, user_id, name) VALUES (?,?,?)",
            (lid, self.user_id, name),
        )
        conn.commit()
        conn.close()
        return {"status": "created", "list_id": lid, "name": name}

    def _handle_list_lists(self, p: dict) -> dict:
        conn = get_connection()
        rows = conn.execute(
            "SELECT id, name, created_at FROM shopping_lists WHERE user_id=? ORDER BY created_at DESC",
            (self.user_id,),
        ).fetchall()
        conn.close()
        return {"status": "ok", "count": len(rows), "lists": [dict(r) for r in rows]}

    def _handle_add_item(self, p: dict) -> dict:
        list_name = p.get("list_name", "default")
        item_name = p.get("item_name", "")
        quantity = p.get("quantity", "")

        if not item_name:
            return {"error": "item_name is required"}

        conn = get_connection()
        row = conn.execute(
            "SELECT id FROM shopping_lists WHERE user_id=? AND name=?",
            (self.user_id, list_name),
        ).fetchone()
        if not row:
            lid = str(uuid.uuid4())[:8]
            conn.execute(
                "INSERT INTO shopping_lists (id, user_id, name) VALUES (?,?,?)",
                (lid, self.user_id, list_name),
            )
        else:
            lid = row["id"]

        iid = str(uuid.uuid4())[:8]
        conn.execute(
            "INSERT INTO shopping_items (id, list_id, name, quantity) VALUES (?,?,?,?)",
            (iid, lid, item_name, quantity),
        )
        conn.commit()
        conn.close()
        return {"status": "added", "item_id": iid, "item": item_name, "list": list_name}

    def _handle_list_items(self, p: dict) -> dict:
        list_name = p.get("list_name", "default")
        show_bought = p.get("show_bought", False)

        conn = get_connection()
        row = conn.execute(
            "SELECT id FROM shopping_lists WHERE user_id=? AND name=?",
            (self.user_id, list_name),
        ).fetchone()

        if not row:
            conn.close()
            return {"status": "ok", "count": 0, "items": [], "list": list_name}

        lid = row["id"]
        query = "SELECT id, name, quantity, bought FROM shopping_items WHERE list_id=?"
        if not show_bought:
            query += " AND bought=0"
        query += " ORDER BY added_at"

        rows = conn.execute(query, (lid,)).fetchall()
        conn.close()
        return {
            "status": "ok",
            "count": len(rows),
            "list": list_name,
            "items": [dict(r) for r in rows],
        }

    def _handle_remove_item(self, p: dict) -> dict:
        iid = p.get("item_id", "")
        name = p.get("item_name", "")

        conn = get_connection()
        if iid:
            conn.execute("DELETE FROM shopping_items WHERE id=?", (iid,))
        elif name:
            conn.execute(
                "DELETE FROM shopping_items WHERE name=? AND list_id IN (SELECT id FROM shopping_lists WHERE user_id=?)",
                (name, self.user_id),
            )
        conn.commit()
        conn.close()
        return {"status": "removed"}

    def _handle_toggle_bought(self, p: dict) -> dict:
        iid = p.get("item_id", "")
        if not iid:
            return {"error": "item_id is required"}

        conn = get_connection()
        conn.execute(
            "UPDATE shopping_items SET bought = CASE WHEN bought=0 THEN 1 ELSE 0 END WHERE id=?",
            (iid,),
        )
        conn.commit()
        conn.close()
        return {"status": "toggled", "item_id": iid}

    @staticmethod
    def get_pending_summary_for(user_id: str) -> list[dict]:
        conn = get_connection()
        rows = conn.execute(
            "SELECT sl.name as list_name, si.name as item, si.quantity "
            "FROM shopping_items si "
            "JOIN shopping_lists sl ON si.list_id = sl.id "
            "WHERE sl.user_id=? AND si.bought=0 "
            "ORDER BY sl.name, si.added_at",
            (user_id,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

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
                                "create_list",
                                "list_lists",
                                "add_item",
                                "list_items",
                                "remove_item",
                                "toggle_bought",
                            ],
                            "description": "Action to perform",
                        },
                        "list_name": {
                            "type": "string",
                            "description": "Name of the shopping list (default if omitted)",
                        },
                        "item_name": {
                            "type": "string",
                            "description": "Name of the item to add/remove",
                        },
                        "quantity": {
                            "type": "string",
                            "description": "Quantity text (e.g. '2', '500g')",
                        },
                        "item_id": {
                            "type": "string",
                            "description": "ID of item to remove or toggle (from list_items)",
                        },
                        "show_bought": {
                            "type": "boolean",
                            "description": "Include already-bought items in listing",
                        },
                    },
                    "required": ["action"],
                },
            },
        }
