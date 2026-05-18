# personal-agent

Personal AI assistant bot via Telegram powered by DeepSeek LLM.

## Stack
- Python 3.11+
- python-telegram-bot v21
- openai SDK -> OpenRouter (DeepSeek models)
- SQLite + ChromaDB

## Structure
```
src/bot.py             Telegram handlers
src/orchestrator.py    LLM orchestrator + tool routing
src/agents/            Specialized agents (notes, calendar, email, etc)
src/memory/            User profile & learning system
src/services/          LLM client, auth, speech
src/db/                Database helpers
data/                  Local storage (profiles, notes, db)
```

## Commands
- Install deps: `pip install -r requirements.txt`
- Run: `python run.py`
- Lint: `ruff check src/ --fix`
- Format: `ruff format src/`
- Test: `pytest tests/ -v`

## Config
Copy `.env.example` to `.env` and fill tokens.
Get Telegram token from @BotFather.
Get OpenRouter key from https://openrouter.ai/keys
