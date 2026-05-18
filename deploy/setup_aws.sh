#!/usr/bin/env bash
set -euo pipefail

# ================================================================
# Personal Agent — AWS EC2 / Lightsail Setup Script
# Tested on: Ubuntu 22.04 / 24.04 LTS (ARM or x86)
# Usage:
#   chmod +x setup_aws.sh
#   ./setup_aws.sh
# ================================================================

REPO_URL="https://github.com/YOUR_USER/YOUR_REPO.git"   # <<< EDIT
BRANCH="main"
PROJECT_DIR="$HOME/personal-agent"
SERVICE_NAME="personal-agent"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
log()  { echo -e "${GREEN}[+]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[x]${NC} $1"; }

# ----------------------------------------------------------------
# 1. System dependencies
# ----------------------------------------------------------------
sudo apt-get update -qq
sudo apt-get install -y -qq python3-pip python3-venv git curl

log "System deps installed"

# ----------------------------------------------------------------
# 2. Clone / pull repo
# ----------------------------------------------------------------
if [ -d "$PROJECT_DIR" ]; then
    warn "Project dir exists — pulling latest..."
    cd "$PROJECT_DIR"
    git pull origin "$BRANCH"
else
    git clone --branch "$BRANCH" "$REPO_URL" "$PROJECT_DIR"
fi
cd "$PROJECT_DIR"

# ----------------------------------------------------------------
# 3. Python virtual env + deps
# ----------------------------------------------------------------
if [ ! -d "venv" ]; then
    python3 -m venv venv
    log "Virtual env created"
fi
source venv/bin/activate

pip install --upgrade pip -q
pip install -r requirements.txt -q
log "Python deps installed"

# ----------------------------------------------------------------
# 4. ChromaDB ONNX model — pre-download to avoid timeout on first call
# ----------------------------------------------------------------
log "Pre-loading ChromaDB ONNX model (prevents timeout)..."
python3 -c "
import chromadb
from chromadb.utils import embedding_functions
try:
    ef = embedding_functions.DefaultEmbeddingFunction()
    ef(['warmup'])
    print('ChromaDB ONNX model ready')
except Exception as e:
    print(f'WARN: ChromaDB warmup: {e}')
" 2>&1 || warn "ChromaDB warmup skipped (will lazy-load)"


# ----------------------------------------------------------------
# 5. Create .env (manual step)
# ----------------------------------------------------------------
if [ ! -f ".env" ]; then
    cp .env.example .env
    warn "====================================================="
    warn " EDIT .env with your tokens:"
    warn "   nano $PROJECT_DIR/.env"
    warn ""
    warn " Required: TELEGRAM_BOT_TOKEN, OPENROUTER_API_KEY"
    warn " Optional: GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET"
    warn "====================================================="
else
    log ".env already exists"
fi

# ----------------------------------------------------------------
# 6. Create data directories
# ----------------------------------------------------------------
mkdir -p data/profiles data/cal_tokens

# ----------------------------------------------------------------
# 7. Pre-download ChromaDB ONNX model to avoid timeout
# ----------------------------------------------------------------
log "Pre-download ChromaDB ONNX model..."
python3 << 'PYEOF'
import chromadb
from chromadb.utils import embedding_functions
try:
    ef = embedding_functions.DefaultEmbeddingFunction()
    ef(['warmup'])
    print('OK: ONNX model loaded')
except Exception as e:
    print(f'WARN: {e}')
PYEOF

# ----------------------------------------------------------------
# 8. Systemd service (auto-start on boot + auto-restart)
# ----------------------------------------------------------------
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

sudo tee "$SERVICE_FILE" > /dev/null << SERVICEEOF
[Unit]
Description=Personal Agent Telegram Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$PROJECT_DIR
ExecStart=$PROJECT_DIR/venv/bin/python $PROJECT_DIR/run.py
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
SERVICEEOF

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"

log "Systemd service created: ${SERVICE_NAME}"
log "  start:  sudo systemctl start ${SERVICE_NAME}"
log "  stop:   sudo systemctl stop ${SERVICE_NAME}"
log "  status: sudo systemctl status ${SERVICE_NAME}"
log "  logs:   journalctl -u ${SERVICE_NAME} -f"

# ----------------------------------------------------------------
# 9. Firewall — port 8080 for Google Calendar OAuth
# ----------------------------------------------------------------
if command -v ufw &> /dev/null; then
    sudo ufw allow 8080/tcp comment 'Personal Agent OAuth'
    log "UFW: port 8080 opened"
elif command -v firewall-cmd &> /dev/null; then
    sudo firewall-cmd --add-port=8080/tcp --permanent
    sudo firewall-cmd --reload
    log "firewalld: port 8080 opened"
else
    warn "No firewall tool found — check AWS Security Group manually"
fi

# ----------------------------------------------------------------
# 10. AWS Security Group reminder
# ----------------------------------------------------------------
echo ""
warn "========================================================="
warn " AWS MANUAL STEP — Security Group Inbound Rules:"
warn "   - Type: Custom TCP"
warn "   - Port: 8080"
warn "   - Source: 0.0.0.0/0 (or your IP)"
warn "   - Description: Personal Agent OAuth callback"
warn ""
warn " GOOGLE OAUTH — .env needs:"
warn "   GOOGLE_REDIRECT_URI=http://YOUR_EC2_PUBLIC_IP:8080/oauth/callback"
warn ""
warn " Then add SAME URI in Google Cloud Console →"
warn " APIs & Services → Credentials → Web client →"
warn " Authorized redirect URIs"
warn "========================================================="

# ----------------------------------------------------------------
# Done
# ----------------------------------------------------------------
echo ""
log "========================================"
log " Setup complete!"
log ""
log " Next steps:"
log "   1. nano .env   ← fill your tokens"
log "   2. sudo systemctl start ${SERVICE_NAME}"
log "   3. sudo systemctl status ${SERVICE_NAME}"
log ""
log " To watch logs:"
log "   journalctl -u ${SERVICE_NAME} -f"
log "========================================"
