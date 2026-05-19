import json

from .config import settings
from .services.llm import chat as llm_chat
from .agents.notes import NotesAgent
from .agents.reminders import ReminderAgent
from .agents.shopping import ShoppingAgent
from .agents.search import SearchAgent
from .agents.todos import TodoAgent
from .agents.habits import HabitsAgent
from .agents.calendar import CalendarAgent
from .memory.context import ContextBuilder
from .memory.learner import Learner
from .memory.episodic import EpisodicMemory

SYSTEM_PROMPT = """\
You are an intelligent personal assistant. Help the user manage notes, reminders, shopping lists, tasks, habits, and daily life.
Be concise, friendly, proactive. Respond in the user's language.
Use tools when appropriate, then interpret the result clearly for the user.
You have web_search + web_fetch for real-time info (weather, news, prices, facts). Use when the user asks about current events.
You have calendar for Google Calendar (list_today, list_week, list, create). Use for any agenda/calendar/schedule/marking questions.

IMPORTANT for reminders: trigger_at is when the NOTIFICATION should fire, not necessarily the event time.
If the user says "remind me about X at Y, but remind me at Z", set trigger_at=Z (the reminder time).
If the user only gives an event time, set trigger_at to that time (use common sense: remind a few minutes before events).
Example: "meeting tomorrow at 9:30" -> trigger_at=2026-05-19T09:25 (5 min before)
Example: "meeting tomorrow at 9:30, remind me at 8:00" -> trigger_at=2026-05-19T08:00\
"""

MAX_MESSAGES = 20


class Orchestrator:
    def __init__(self, user_id: str):
        self.user_id = user_id
        self._ctx = ContextBuilder(user_id)
        self._learner = Learner(user_id)
        self._episodic = EpisodicMemory(user_id)
        self._interaction_count = 0

        self.agents = {
            "notes": NotesAgent(user_id),
            "reminders": ReminderAgent(user_id),
            "shopping": ShoppingAgent(user_id),
            "web_search": SearchAgent(user_id),
            "todos": TodoAgent(user_id),
            "habits": HabitsAgent(user_id),
            "calendar": CalendarAgent(user_id),
        }

        context = self._ctx.build()
        self.conversation: list[dict] = [
            {"role": "system", "content": f"{SYSTEM_PROMPT}\n\n{context}"}
        ]

    def _tools(self) -> list[dict]:
        return [a.get_tool_definition() for a in self.agents.values()]

    def _refresh_context(self):
        self.conversation[0] = {
            "role": "system",
            "content": f"{SYSTEM_PROMPT}\n\n{self._ctx.build()}",
        }

    def _trim(self):
        if len(self.conversation) > MAX_MESSAGES:
            self.conversation = [
                self.conversation[0],
                *self.conversation[-(MAX_MESSAGES - 1) :],
            ]

    async def process(self, user_message: str) -> str:
        self._refresh_context()
        self.conversation.append({"role": "user", "content": user_message})
        self._trim()

        try:
            msg = llm_chat(self.conversation, tools=self._tools())
        except Exception as e:
            print(f"[Orchestrator] LLM API error: {e}")
            return "Desculpa, o servico LLM esta indisponivel. Tenta novamente em alguns segundos."

        if msg.tool_calls:
            self.conversation.append(_assistant_tool_msg(msg))

            for tc in msg.tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments)
                except (json.JSONDecodeError, TypeError) as e:
                    args = {
                        "error": f"Invalid tool arguments: {e}",
                        "raw": tc.function.arguments,
                    }
                agent = self.agents.get(name)
                result = (
                    await agent.execute(args.get("action", ""), args)
                    if agent
                    else {"error": f"No agent: {name}"}
                )
                self.conversation.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )

            try:
                msg = llm_chat(self.conversation)
            except Exception as e:
                print(f"[Orchestrator] LLM API error after tools: {e}")
                return "Desculpa, o servico LLM esta indisponivel. Tenta novamente em alguns segundos."

        reply = msg.content or "Desculpa, nao consegui processar."
        self.conversation.append({"role": "assistant", "content": reply})
        self._trim()

        try:
            self._episodic.store(
                f"User: {user_message}\nAssistant: {reply}",
                memory_type="interaction",
            )
        except Exception as e:
            print(f"[Orchestrator] Episodic memory store failed: {e}")

        self._interaction_count += 1
        if self._interaction_count >= settings.profile_update_threshold:
            try:
                await self._learner.learn(user_message, reply)
            except Exception as e:
                print(f"[Orchestrator] Learner failed: {e}")
            self._interaction_count = 0

        return reply

    def reset(self):
        self.conversation = [
            {"role": "system", "content": f"{SYSTEM_PROMPT}\n\n{self._ctx.build()}"}
        ]


def _assistant_tool_msg(msg) -> dict:
    return {
        "role": "assistant",
        "content": msg.content,
        "tool_calls": [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in msg.tool_calls
        ],
    }
