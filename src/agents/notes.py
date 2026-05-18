import re
from datetime import datetime, timezone
from pathlib import Path

from ..config import settings
from .base import BaseAgent


class NotesAgent(BaseAgent):
    name = "notes"
    description = "Manage personal notes: create, search, list, read, append, delete."

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.notes_dir = Path(settings.data_dir) / "notes" / user_id
        self.notes_dir.mkdir(parents=True, exist_ok=True)

    async def execute(self, action: str, params: dict) -> dict:
        fn = getattr(self, f"_handle_{action}", None)
        if fn is None:
            return {"error": f"Unknown action: {action}"}
        return await fn(params)

    async def _handle_create(self, p: dict) -> dict:
        title = p.get("title", "untitled")
        content = p.get("content", "")
        tags = p.get("tags", [])

        safe = re.sub(r"[^\w\-_ ]", "", title).strip().replace(" ", "_") or "untitled"
        filepath = self.notes_dir / f"{safe}.md"

        if filepath.exists():
            return {"error": f"Note '{title}' exists. Use append."}

        tag_line = " ".join(f"#{t}" for t in tags)
        header = f"# {title}\n\n_{datetime.now(timezone.utc).isoformat()}_\n"
        if tag_line:
            header += f"Tags: {tag_line}\n"
        header += "\n"

        filepath.write_text(header + content, encoding="utf-8")
        return {"status": "created", "title": title, "path": str(filepath)}

    async def _handle_list(self, p: dict) -> dict:
        tag_filter = p.get("tag")
        files = sorted(
            self.notes_dir.glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True
        )
        notes = []
        for f in files:
            text = f.read_text(encoding="utf-8")[:300]
            tags = re.findall(r"#(\w+)", text)
            if tag_filter and tag_filter not in tags:
                continue
            mtime = datetime.fromtimestamp(
                f.stat().st_mtime, tz=timezone.utc
            ).isoformat()
            notes.append(
                {"title": f.stem.replace("_", " "), "tags": tags, "updated": mtime}
            )
        return {"status": "ok", "count": len(notes), "notes": notes}

    async def _handle_search(self, p: dict) -> dict:
        query = (p.get("query") or "").lower()
        if not query:
            return {"error": "query is required"}
        results = []
        for f in self.notes_dir.glob("*.md"):
            text = f.read_text(encoding="utf-8")
            if query not in text.lower():
                continue
            lines = text.split("\n")
            hit = next((i for i, line in enumerate(lines) if query in line.lower()), 0)
            lo = max(0, hit - 3)
            hi = min(len(lines), hit + 4)
            results.append(
                {
                    "title": f.stem.replace("_", " "),
                    "snippet": "\n".join(lines[lo:hi]),
                    "path": str(f),
                }
            )
        return {"status": "ok", "count": len(results), "results": results}

    async def _handle_read(self, p: dict) -> dict:
        title = p.get("title", "")
        safe = re.sub(r"[^\w\-_ ]", "", title).strip().replace(" ", "_")
        filepath = self.notes_dir / f"{safe}.md"
        if not filepath.exists():
            return {"error": f"Note '{title}' not found"}
        return {
            "status": "ok",
            "title": title,
            "content": filepath.read_text(encoding="utf-8"),
        }

    async def _handle_append(self, p: dict) -> dict:
        title = p.get("title", "")
        content = p.get("content", "")
        safe = re.sub(r"[^\w\-_ ]", "", title).strip().replace(" ", "_")
        filepath = self.notes_dir / f"{safe}.md"
        if not filepath.exists():
            return {"error": f"Note '{title}' not found. Use create."}
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(f"\n{content}\n")
        return {"status": "appended", "title": title}

    async def _handle_delete(self, p: dict) -> dict:
        title = p.get("title", "")
        safe = re.sub(r"[^\w\-_ ]", "", title).strip().replace(" ", "_")
        filepath = self.notes_dir / f"{safe}.md"
        if not filepath.exists():
            return {"error": f"Note '{title}' not found"}
        filepath.unlink()
        return {"status": "deleted", "title": title}

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
                                "create",
                                "list",
                                "search",
                                "read",
                                "append",
                                "delete",
                            ],
                            "description": "Action to perform on notes",
                        },
                        "title": {
                            "type": "string",
                            "description": "Title of the note (used as filename)",
                        },
                        "content": {
                            "type": "string",
                            "description": "Content to write or append to the note",
                        },
                        "query": {
                            "type": "string",
                            "description": "Search query for finding notes",
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Tags to categorize the note",
                        },
                    },
                    "required": ["action"],
                },
            },
        }
