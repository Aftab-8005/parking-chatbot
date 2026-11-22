"""Shared SQLite checkpointer for the chatbot graph.

Backing conversation + in-flight reservation state with a durable checkpointer
(rather than the in-memory dict Stage 1 used) is what lets the graph genuinely
pause at the admin-approval step (via `interrupt()`) and be resumed later --
including after the process restarts -- instead of faking the wait.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver

from app.config import settings

_saver: SqliteSaver | None = None


def get_checkpointer() -> SqliteSaver:
    global _saver
    if _saver is None:
        db_path = Path(settings.checkpoint_db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        _saver = SqliteSaver(conn)
    return _saver
