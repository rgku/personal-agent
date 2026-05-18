import json
import re

from ..services.llm import chat as llm_chat


LEARNER_SYSTEM = """\
Analyze the interaction between a user and their personal assistant.
Extract facts, preferences, and profile updates about the user.

Return ONLY valid JSON (no markdown, no explanation, no code fences):
{"facts":[],"preferences":{},"profile_updates":{}}

Example:
User: "I live in Lisbon and prefer short answers"
Assistant: "Got it! How can I help?"
Return: {"facts":["User lives in Lisbon"],"preferences":{"response_style":"concise"},"profile_updates":{}}

Return empty lists/objects if nothing new is learned.\
"""


class Learner:
    def __init__(self, user_id: str):
        self.user_id = user_id

    async def learn(self, user_msg: str, assistant_msg: str):
        from .profile import ProfileManager
        from .episodic import EpisodicMemory

        response = llm_chat(
            messages=[
                {"role": "system", "content": LEARNER_SYSTEM},
                {
                    "role": "user",
                    "content": f"User: {user_msg}\nAssistant: {assistant_msg}",
                },
            ],
            model=None,
        )

        data = self._parse(response.content or "")
        if not data:
            return

        profile_mgr = ProfileManager(self.user_id)
        episodic = EpisodicMemory(self.user_id)

        for fact in data.get("facts", []):
            episodic.store(fact, memory_type="fact")

        prefs = data.get("preferences", {})
        updates = data.get("profile_updates", {})

        if prefs or updates:
            profile = profile_mgr.get()
            if prefs:
                profile.preferences.update(prefs)
            for field, value in updates.items():
                if hasattr(profile, field) and value is not None:
                    setattr(profile, field, value)
            profile_mgr.save(profile)

    @staticmethod
    def _parse(text: str) -> dict | None:
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
        return None
