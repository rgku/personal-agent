import os
import sys
import atexit

from src.bot import build_app, setup_jobs
from src.db.database import init_db
from src.agents.calendar import start_oauth_server

PID_FILE = os.path.join(os.path.dirname(__file__), "data", "bot.pid")


def acquire_lock():
    os.makedirs(os.path.dirname(PID_FILE), exist_ok=True)
    if os.path.exists(PID_FILE):
        with open(PID_FILE) as f:
            old_pid = f.read().strip()
        alive = False
        try:
            import psutil
            alive = psutil.pid_exists(int(old_pid))
        except Exception:
            try:
                import subprocess
                r = subprocess.run(["tasklist", "/FI", f"PID eq {old_pid}"], capture_output=True, text=True)
                alive = str(old_pid) in r.stdout
            except Exception:
                pass
        if alive:
            print(f"ERROR: Bot already running (PID {old_pid}). Stop it first.")
            sys.exit(1)
        else:
            os.remove(PID_FILE)
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))
    def _cleanup():
        try:
            if os.path.exists(PID_FILE):
                os.remove(PID_FILE)
        except Exception:
            pass
    atexit.register(_cleanup)


def main():
    acquire_lock()
    init_db()
    start_oauth_server()
    app = build_app()
    setup_jobs(app)
    print("Personal Agent started. Ctrl+C to stop.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
