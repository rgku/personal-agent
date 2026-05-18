# personal-agent — Project Overview

Personal AI assistant bot via Telegram powered by DeepSeek V4 Flash LLM.

## Concept
Multi-agent personal assistant accessible via Telegram. Manages notes, calendar, email, reminders, shopping lists.
Learns user preferences over time through profile + episodic memory system.

## Stack
- **Python 3.11+** — recommended for AI agent ecosystem
- **python-telegram-bot v21** — Telegram bot framework (async)
- **openai SDK** — talking to DeepSeek API (drop-in: `base_url=https://api.deepseek.com`)
- **DeepSeek V4 Flash** (`deepseek-chat`) — LLM, already paid via OpenCode Go subscription
- **SQLite** — relational data (reminders, shopping, conversations)
- **ChromaDB** — vector store for episodic memory (Phase 2)
- **APScheduler** — background reminders
- **Google APIs** — Calendar + Gmail (Phase 4)

## Architecture
```
Telegram User → python-telegram-bot → Orchestrator (LLM + function calling)
                                            ↓
                    ┌───────────────────────┼───────────────────────┐
                    ↓                       ↓                       ↓
            Calendar Agent          Email Agent            Notes Agent
            Reminder Agent          Shopping Agent         [future agents]
```

## Key Design Decisions
1. **No LangChain** — direct openai SDK for function calling. More control, less abstraction.
2. **Multi-user** — each Telegram user has own profile, notes, agents.
3. **Memory system** — 3 layers: structured profile (JSON), episodic memory (ChromaDB), daily context (computed).
4. **Learning loop** — LLM extracts user facts/preferences after each interaction.
5. **Local first** — runs on user's PC, cloud-migratable later.

## Phases
1. **Foundation** — Telegram bot, orchestrator, notes agent (DONE)
2. **Memory** — profile, episodic memory, learning extraction, daily context
3. **More Agents** — shopping, reminders, SQLite schema
4. **Google Integration** — Calendar + Gmail OAuth2
5. **Voice & Polish** — STT via Whisper, UX improvements

## File Structure
```
personal-agent/
├── run.py                  # Entry point
├── src/
│   ├── config.py           # Pydantic settings from .env
│   ├── bot.py              # Telegram handlers
│   ├── orchestrator.py     # LLM orchestrator + function calling
│   ├── agents/
│   │   ├── base.py         # BaseAgent ABC
│   │   └── notes.py        # Notes agent (markdown)
│   ├── memory/             # User profile & learning (Phase 2)
│   ├── services/
│   │   └── llm.py          # DeepSeek client via openai SDK
│   └── db/                 # SQLite helpers (Phase 3)
└── data/                   # Local storage (.gitignored)
```
