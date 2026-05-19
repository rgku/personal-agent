import os
import sys
import atexit
import logging
import psutil

from src.bot import build_app, setup_jobs
from src.db.database import init_db
from src.agents.calendar import start_oauth_server

PID_FILE = os.path.join(os.path.dirname(__file__), "data", "bot.pid")


def _setup_logging():
    log_dir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(log_dir, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=[
            logging.FileHandler(os.path.join(log_dir, "bot.log"), encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def acquire_lock():
    os.makedirs(os.path.dirname(PID_FILE), exist_ok=True)
    try:
        fd = os.open(PID_FILE, os.O_CREAT | os.O_EXCL | os.O_RDWR)
        with os.fdopen(fd, "w") as f:
            f.write(str(os.getpid()))
    except FileExistsError:
        with open(PID_FILE) as f:
            old_pid = f.read().strip()
        try:
            old_pid_int = int(old_pid)
            alive = psutil.pid_exists(old_pid_int)
        except (ValueError, Exception):
            alive = False
        if alive:
            print(f"ERROR: Bot already running (PID {old_pid}). Stop it first.")
            sys.exit(1)
        os.remove(PID_FILE)
        fd = os.open(PID_FILE, os.O_CREAT | os.O_EXCL | os.O_RDWR)
        with os.fdopen(fd, "w") as f:
            f.write(str(os.getpid()))

    def _cleanup():
        try:
            if os.path.exists(PID_FILE):
                os.remove(PID_FILE)
        except Exception:
            pass

    atexit.register(_cleanup)


def main():
    _setup_logging()
    acquire_lock()
    init_db()
    start_oauth_server()
    app = build_app()
    setup_jobs(app)
    logging.getLogger(__name__).info("Personal Agent started. Ctrl+C to stop.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
