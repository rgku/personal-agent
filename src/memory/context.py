from datetime import datetime, timezone

from .profile import ProfileManager
from .episodic import EpisodicMemory


class ContextBuilder:
    def __init__(self, user_id: str):
        self.user_id = user_id
        self._profile = ProfileManager(user_id)
        self._episodic = EpisodicMemory(user_id)

    def build(self) -> str:
        profile = self._profile.get()
        now = datetime.now(timezone.utc)
        parts: list[str] = []

        parts.append(f"Current datetime (UTC): {now.strftime('%Y-%m-%dT%H:%M')}")
        parts.append(f"Current day: {now.strftime('%A')}")

        if profile.name:
            parts.append(f"User: {profile.name}")
        if profile.timezone:
            parts.append(f"Timezone: {profile.timezone}")
        if profile.language:
            parts.append(f"Language: {profile.language}")
        if profile.preferences:
            prefs = ", ".join(f"{k}={v}" for k, v in profile.preferences.items())
            parts.append(f"Preferences: {prefs}")
        if profile.frequent_contacts:
            parts.append(f"Frequent contacts: {', '.join(profile.frequent_contacts)}")

        recent = self._episodic.recent(n=3)
        if recent:
            parts.append("Recent interactions:")
            for r in recent:
                parts.append(f"  - {r}")

        facts = self._episodic.recent(n=5, memory_type="fact")
        if facts:
            parts.append("Known facts:")
            for f in facts:
                parts.append(f"  - {f}")

        return "\n".join(parts) if parts else "No profile data yet."
