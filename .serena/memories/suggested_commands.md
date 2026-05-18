# Suggested Commands — personal-agent

## Development
```bash
# Install dependencies
pip install -r requirements.txt

# Run the bot
python run.py

# Lint with ruff
ruff check src/ --fix

# Format with ruff
ruff format src/

# Run tests
pytest tests/ -v

# Run single test file
pytest tests/test_orchestrator.py -v
```

## Git
```bash
git status
git add .
git commit -m "..."
git push
```

## Python
```bash
# Python 3.11+ required
python --version

# Create virtual environment (optional)
python -m venv .venv
.venv\Scripts\Activate.ps1

# Install specific package
pip install <package>
```

## Telegram Bot Setup
1. Talk to @BotFather on Telegram
2. `/newbot` → choose name + username
3. Copy token → paste in `.env` → `TELEGRAM_BOT_TOKEN=...`

## DeepSeek API
- API key: same as OpenCode Go subscription
- Endpoint: `https://api.deepseek.com`
- Model: `deepseek-chat`

## Config Files
- `.env` — secrets (never commit, in .gitignore)
- `.env.example` — template for new setups
- `AGENTS.md` — project context for OpenCode
