import os
import json
from datetime import datetime

SESSION_DIR = "sessions"

def ensure_session_dir():
    if not os.path.exists(SESSION_DIR):
        os.makedirs(SESSION_DIR)


def log_exercise_to_session(session_log):
    """
    Save or append the current session log to a JSON file.
    If file exists, it is overwritten.
    """
    ensure_session_dir()

    session_id = session_log["session_id"]
    filename = os.path.join(SESSION_DIR, f"{session_id}.json")

    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(session_log, f, indent=2, ensure_ascii=False)
        print(f"📁 Session log updated: {filename}")
    except Exception as e:
        print(f"⚠️ Failed to save session log: {e}")


def load_session_log(session_id):
    """
    Load a session log by session ID.
    """
    filename = os.path.join(SESSION_DIR, f"{session_id}.json")
    if not os.path.exists(filename):
        print(f"⚠️ Session log {session_id} not found.")
        return None

    with open(filename, 'r', encoding='utf-8') as f:
        return json.load(f)
