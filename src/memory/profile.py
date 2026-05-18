import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

from ..config import settings


class UserProfile(BaseModel):
    user_id: str = ""
    name: str | None = None
    timezone: str = "UTC"
    language: str = "pt"
    email: str | None = None
    preferences: dict = {}
    frequent_contacts: list[str] = []
    routines: list[dict] = []
    created_at: str = ""
    updated_at: str = ""


class ProfileManager:
    def __init__(self, user_id: str):
        self.user_id = user_id
        self._dir = Path(settings.data_dir) / "profiles"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / f"{user_id}.json"

    def get(self) -> UserProfile:
        if self._path.exists():
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return UserProfile(**data)
        now = datetime.now(timezone.utc).isoformat()
        return UserProfile(user_id=self.user_id, created_at=now, updated_at=now)

    def save(self, profile: UserProfile):
        profile.updated_at = datetime.now(timezone.utc).isoformat()
        self._path.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
