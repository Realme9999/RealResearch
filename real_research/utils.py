"""Shared utilities for RealResearch CLI tools."""

import hashlib
import io
import json
import os
import sys
import tempfile
import time


def load_dotenv():
    """Load .env file from cwd or parent directories without external deps."""
    candidates = [".env"]
    # Also check RealResearch/ parent
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates.append(os.path.join(script_dir, "..", ".env"))
    candidates.append(os.path.join(script_dir, ".env"))
    for path in candidates:
        path = os.path.abspath(path)
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        key, val = line.split("=", 1)
                        key = key.strip()
                        val = val.strip().strip('"').strip("'")
                        if key and key not in os.environ:
                            os.environ[key] = val
            except Exception:
                pass
            break


def setup_utf8():
    """Configure stdin/stdout/stderr for UTF-8 I/O."""
    if hasattr(sys.stdin, "buffer"):
        sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")


def print_json(data: dict):
    """Print data as JSON to stdout."""
    print(json.dumps(data, ensure_ascii=False, indent=2))


def exit_with_error(message: str, **details):
    """Print error as JSON and exit with code 1."""
    error = {"error": message}
    error.update(details)
    print_json(error)
    sys.exit(1)


class SearchCache:
    """File-based cache for search results with TTL."""

    def __init__(self, ttl: int = 3600, cache_dir: str = None):
        self.ttl = ttl
        self.cache_dir = cache_dir or os.path.join(tempfile.gettempdir(), "rr_cache")
        os.makedirs(self.cache_dir, exist_ok=True)

    def _key(self, query: str, max_results: int, depth: str) -> str:
        raw = f"{query}:{max_results}:{depth}"
        return hashlib.md5(raw.encode()).hexdigest()

    def get(self, query: str, max_results: int, depth: str) -> dict | None:
        path = os.path.join(self.cache_dir, self._key(query, max_results, depth) + ".json")
        if not os.path.isfile(path):
            return None
        try:
            mtime = os.path.getmtime(path)
            if time.time() - mtime > self.ttl:
                os.remove(path)
                return None
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def set(self, query: str, max_results: int, depth: str, result: dict):
        path = os.path.join(self.cache_dir, self._key(query, max_results, depth) + ".json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False)
        except Exception:
            pass
