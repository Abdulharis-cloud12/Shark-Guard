"""
SharkGuard - Local run history

Stores only aggregate scores and timestamps for past runs, never API
keys, never raw prompts or answers - consistent with SharkGuard's
stateless design. This is opt-in: the dashboard only writes to this
file if the user explicitly checks "Save this run to local history".

Stored at sharkguard_history.json in the current working directory.
Listed in .gitignore so it never gets committed by accident.
"""

import json
import os
from datetime import datetime, timezone

HISTORY_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sharkguard_history.json")


def load_history() -> list:
    """Returns the list of past run summaries, oldest first. Empty list if none yet."""
    if not os.path.exists(HISTORY_PATH):
        return []
    try:
        with open(HISTORY_PATH) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def save_run(faithfulness: float, resistance: float, threshold: float, gate_pass: bool) -> None:
    """Appends one run's summary scores to the local history file."""
    history = load_history()
    history.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "faithfulness": round(faithfulness, 3),
        "resistance": round(resistance, 3),
        "threshold": threshold,
        "gate_pass": gate_pass,
    })
    with open(HISTORY_PATH, "w") as f:
        json.dump(history, f, indent=2)


def clear_history() -> None:
    """Deletes the local history file, if it exists."""
    if os.path.exists(HISTORY_PATH):
        os.remove(HISTORY_PATH)
