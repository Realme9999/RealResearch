"""Session-based research process logger for RealResearch.

Records every tool call (input, output, duration, tokens) during a research session.
Logs are stored in Logs/sessions/<session_id>/ as JSON files.

Usage in CLI tools:
    from .logger import get_logger
    logger = get_logger()
    logger.start_step("rr-search", {"query": "...", "max_results": 8})
    # ... do work ...
    logger.end_step(result_summary)
"""

import json
import os
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any

# ── Paths ────────────────────────────────────────────────

_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_script_dir)
LOGS_ROOT = os.path.join(_project_root, "Logs")
SESSIONS_DIR = os.path.join(LOGS_ROOT, "sessions")
SESSIONS_INDEX = os.path.join(LOGS_ROOT, "sessions.jsonl")
CURRENT_SESSION_FILE = os.path.join(LOGS_ROOT, ".current_session")

# ── Thread-local state ───────────────────────────────────

_state = threading.local()


def _extract_keywords(text: str, max_words: int = 4) -> str:
    """Extract Chinese/English keywords for session naming."""
    cleaned = re.sub(r"[^\w\s一-鿿]", " ", text)
    words = cleaned.split()
    keywords = [w for w in words if len(w) > 1][:max_words]
    return "-".join(keywords) if keywords else "research"


def _make_session_id(query: str) -> str:
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d_%H-%M")
    kw = _extract_keywords(query)
    return f"{date_str}_{kw}"


# ── SessionLogger ────────────────────────────────────────

class SessionLogger:
    """Logs tool calls within a single research session."""

    def __init__(self, session_id: str, query: str, bank_id: str | None = None):
        self.session_id = session_id
        self.query = query
        self.bank_id = bank_id
        self.session_dir = os.path.join(SESSIONS_DIR, session_id)
        self.started_at = datetime.now(timezone.utc)
        self.step_counter = 0
        self.steps: list[dict] = []
        self.token_usage: dict[str, int] = {}
        self.tool_counts: dict[str, int] = {}
        self._step_start: float = 0
        self._step_args: dict | None = None
        self._step_tool: str = ""

        os.makedirs(self.session_dir, exist_ok=True)
        self._write_session_meta()

    def _write_session_meta(self):
        meta = {
            "session_id": self.session_id,
            "query": self.query,
            "bank_id": self.bank_id,
            "started_at": self.started_at.isoformat(),
            "finished_at": None,
            "status": "active",
            "total_steps": 0,
            "total_duration_ms": 0,
            "tools_used": {},
            "token_usage": {},
            "report_path": None,
        }
        path = os.path.join(self.session_dir, "session.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

    def start_step(self, tool: str, args: dict[str, Any] | None = None):
        """Record the start of a tool call."""
        self.step_counter += 1
        self._step_start = time.time()
        self._step_tool = tool
        self._step_args = args or {}

    def end_step(
        self,
        result_summary: Any = None,
        result_full: Any = None,
        token_usage: dict[str, int] | None = None,
        error: str | None = None,
    ):
        """Record the end of a tool call."""
        duration_ms = int((time.time() - self._step_start) * 1000)

        # Track tool counts
        self.tool_counts[self._step_tool] = self.tool_counts.get(self._step_tool, 0) + 1

        # Track token usage
        if token_usage:
            for k, v in token_usage.items():
                self.token_usage[k] = self.token_usage.get(k, 0) + v

        step_entry = {
            "step": self.step_counter,
            "tool": self._step_tool,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "duration_ms": duration_ms,
            "args": self._step_args,
            "result_summary": result_summary,
            "token_usage": token_usage,
            "error": error,
        }

        # Optionally store full result
        if result_full is not None:
            step_entry["result_full"] = result_full

        self.steps.append(step_entry)

        # Write individual step file
        filename = f"{self.step_counter:03d}_{self._step_tool}.json"
        filepath = os.path.join(self.session_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(step_entry, f, ensure_ascii=False, indent=2)

        # Update session meta
        self._update_session_meta()

    def record_tokens(self, key: str, count: int):
        """Record token usage without a full step (e.g., from LLM calls)."""
        self.token_usage[key] = self.token_usage.get(key, 0) + count

    def close(self, report_path: str | None = None):
        """Mark session as finished."""
        self._update_session_meta(report_path=report_path, finished=True)
        self._append_to_index()

    def _update_session_meta(
        self, report_path: str | None = None, finished: bool = False
    ):
        now = datetime.now(timezone.utc)
        total_ms = int((now - self.started_at).total_seconds() * 1000)
        meta = {
            "session_id": self.session_id,
            "query": self.query,
            "bank_id": self.bank_id,
            "started_at": self.started_at.isoformat(),
            "finished_at": now.isoformat() if finished else None,
            "status": "finished" if finished else "active",
            "total_steps": self.step_counter,
            "total_duration_ms": total_ms,
            "tools_used": dict(self.tool_counts),
            "token_usage": dict(self.token_usage),
            "report_path": report_path,
        }
        path = os.path.join(self.session_dir, "session.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

    def _append_to_index(self):
        """Append session summary to sessions.jsonl index."""
        now = datetime.now(timezone.utc)
        total_ms = int((now - self.started_at).total_seconds() * 1000)
        entry = {
            "session_id": self.session_id,
            "query": self.query,
            "bank_id": self.bank_id,
            "started_at": self.started_at.isoformat(),
            "finished_at": now.isoformat(),
            "total_steps": self.step_counter,
            "total_duration_ms": total_ms,
            "tools_used": dict(self.tool_counts),
        }
        os.makedirs(os.path.dirname(SESSIONS_INDEX), exist_ok=True)
        with open(SESSIONS_INDEX, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ── Public API ───────────────────────────────────────────

def _save_current_session(session_id: str):
    """Write current session ID to disk for cross-process sharing."""
    os.makedirs(os.path.dirname(CURRENT_SESSION_FILE), exist_ok=True)
    with open(CURRENT_SESSION_FILE, "w", encoding="utf-8") as f:
        f.write(session_id)


def _load_current_session_id() -> str | None:
    """Read current session ID from disk."""
    if not os.path.isfile(CURRENT_SESSION_FILE):
        return None
    try:
        with open(CURRENT_SESSION_FILE, "r", encoding="utf-8") as f:
            sid = f.read().strip()
            return sid if sid else None
    except (OSError, IOError):
        return None


def _clear_current_session():
    """Remove the current session file."""
    try:
        if os.path.isfile(CURRENT_SESSION_FILE):
            os.remove(CURRENT_SESSION_FILE)
    except OSError:
        pass


def get_logger() -> SessionLogger | None:
    """Get the current session logger.

    Checks thread-local first, then falls back to the session file
    on disk so that CLI tools running in separate processes can
    resume the same session.
    """
    # 1. Thread-local (same process)
    logger = getattr(_state, "logger", None)
    if logger is not None:
        return logger

    # 2. Cross-process: read session ID from file and resume
    session_id = _load_current_session_id()
    if session_id is None:
        return None

    session_dir = os.path.join(SESSIONS_DIR, session_id)
    meta_path = os.path.join(session_dir, "session.json")
    if not os.path.isfile(meta_path):
        return None

    return resume_session(session_id)


def start_session(
    query: str, bank_id: str | None = None, session_id: str | None = None
) -> SessionLogger:
    """Start a new research session. Returns the logger."""
    if session_id is None:
        session_id = _make_session_id(query)
    logger = SessionLogger(session_id, query, bank_id)
    _state.logger = logger
    _save_current_session(session_id)
    return logger


def resume_session(session_id: str) -> SessionLogger:
    """Resume an existing session by ID (for continuing across tool calls)."""
    session_dir = os.path.join(SESSIONS_DIR, session_id)
    meta_path = os.path.join(session_dir, "session.json")
    if not os.path.isfile(meta_path):
        return start_session(query=session_id, session_id=session_id)

    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    logger = SessionLogger(session_id, meta["query"], meta.get("bank_id"))
    logger.step_counter = meta.get("total_steps", 0)
    logger.tool_counts = meta.get("tools_used", {})
    logger.token_usage = meta.get("token_usage", {})

    # Parse started_at
    try:
        logger.started_at = datetime.fromisoformat(meta["started_at"])
    except (ValueError, KeyError):
        pass

    _state.logger = logger
    _save_current_session(session_id)
    return logger


def close_session(report_path: str | None = None):
    """Close the current session."""
    logger = get_logger()
    if logger:
        logger.close(report_path=report_path)
        _state.logger = None
        _clear_current_session()
