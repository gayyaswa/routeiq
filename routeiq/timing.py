"""Lightweight timing log — appends [HH:MM:SS] lines to logs/timing.log."""
from __future__ import annotations
import os
import time

_LOG_PATH = "logs/timing.log"


def log(msg: str) -> None:
    os.makedirs("logs", exist_ok=True)
    with open(_LOG_PATH, "a") as f:
        f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")


def clear() -> None:
    """Call at the start of each planning run to get a clean log."""
    os.makedirs("logs", exist_ok=True)
    with open(_LOG_PATH, "w") as f:
        f.write(f"=== run started {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
