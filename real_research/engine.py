"""MemoryEngine lifecycle management for RealResearch.

Translates RR_* config into Hindsight MemoryEngine constructor kwargs,
bypassing Hindsight's own HINDSIGHT_API_* env-var reading entirely.

Storage strategy:
  1. If RR_DATABASE_URL is set → use that (user-managed PostgreSQL)
  2. Otherwise → start pg0-embedded with data_dir in LOCALAPPDATA
"""

import json
import logging
import os
import sys
from contextlib import asynccontextmanager

# ───────────────────────────────────────────────
# Auto-add hindsightbase/hindsight-api-slim to sys.path
# so we can import hindsight_api without pip install
# ───────────────────────────────────────────────
_script_dir = os.path.dirname(os.path.abspath(__file__))

# Support two layouts:
# 1) hindsightbase/ inside project root (sibling to real_research/)  ← SKILL.md
# 2) hindsightbase/ in parent dir of project root                    ← README
_project_root = os.path.dirname(_script_dir)  # up to RealResearch/
_hindsight_slim = os.path.join(_project_root, "hindsightbase", "hindsight-api-slim")
if not os.path.isdir(_hindsight_slim):
    _project_root = os.path.dirname(_project_root)  # fallback to parent dir
    _hindsight_slim = os.path.join(_project_root, "hindsightbase", "hindsight-api-slim")
if os.path.isdir(_hindsight_slim) and _hindsight_slim not in sys.path:
    sys.path.insert(0, _hindsight_slim)

from hindsight_api import MemoryEngine, RequestContext
from hindsight_api.engine.cross_encoder import CohereCrossEncoder
from hindsight_api.engine.embeddings import OpenAIEmbeddings
from hindsight_api.engine.query_analyzer import DateparserQueryAnalyzer
from hindsight_api.engine.task_backend import SyncTaskBackend

from .config import load_config

logger = logging.getLogger(__name__)


# ───────────────────────────────────────────────
# MiMo schema-echo fix (non-invasive)
# MiMo sometimes returns the JSON schema definition itself
# instead of actual data. This patch hooks into the OpenAI client
# to add a clarification to the system prompt right before the API call.
# ───────────────────────────────────────────────
def _apply_mimo_schema_echo_fix():
    """Hook into OpenAI client to prevent MiMo from echoing the JSON schema."""
    from openai.resources.chat.completions import AsyncCompletions

    _original_create = AsyncCompletions.create

    async def _patched_create(self, **kwargs):
        messages = kwargs.get("messages", [])
        model = kwargs.get("model", "")

        # Only patch for MiMo
        if "mimo" in model.lower() and messages:
            for msg in messages:
                if msg.get("role") == "system":
                    content = msg.get("content", "")
                    if "You must respond with valid JSON matching this schema" in content:
                        clarification = (
                            "\n\n⚠️ CRITICAL: You are being asked to EXTRACT FACTS from the input text. "
                            "Do NOT return the JSON schema definition. Return a JSON object with a 'facts' array "
                            "containing the actual extracted information. "
                            "CORRECT: {\"facts\": [{\"what\": \"...\", \"when\": \"...\", ...}]} "
                            "WRONG: {\"type\": \"object\", \"properties\": {...}}"
                        )
                        msg["content"] = content + clarification
                    break

        return await _original_create(self, **kwargs)

    AsyncCompletions.create = _patched_create

_apply_mimo_schema_echo_fix()

# Pure-ASCII path for PostgreSQL data (pg0/initdb doesn't support CJK paths)
_local_app = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
MEMORY_STORE_DIR = os.path.join(_local_app, "real-research", "memory_store")
_PG0_INFO_FILE = os.path.join(MEMORY_STORE_DIR, ".pg0_info.json")

_PG0_NAME = "real-research"
_PG0_USER = "hindsight"
_PG0_PASS = "hindsight"
_PG0_DB = "hindsight"


# ───────────────────────────────────────────────
# Database URL resolution
# ───────────────────────────────────────────────

def _read_cached_uri() -> str | None:
    """Read cached pg0 URI (fast path for repeated CLI calls)."""
    try:
        with open(_PG0_INFO_FILE, "r", encoding="utf-8") as f:
            info = json.load(f)
        uri = info.get("uri")
        if not uri:
            return None
        import socket
        from urllib.parse import urlparse
        parsed = urlparse(uri)
        host = parsed.hostname or "localhost"
        port = parsed.port or 5432
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        try:
            sock.connect((host, port))
            return uri
        except (ConnectionRefusedError, OSError):
            return None
        finally:
            sock.close()
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return None


def _write_cached_uri(uri: str):
    os.makedirs(MEMORY_STORE_DIR, exist_ok=True)
    with open(_PG0_INFO_FILE, "w", encoding="utf-8") as f:
        json.dump({"uri": uri, "data_dir": MEMORY_STORE_DIR}, f)


def _start_local_pg0() -> str:
    """Start pg0-embedded, return postgresql:// URI."""
    cached = _read_cached_uri()
    if cached:
        return cached

    os.makedirs(MEMORY_STORE_DIR, exist_ok=True)

    try:
        from pg0 import Pg0
    except ImportError:
        logger.warning("pg0-embedded not installed. Install with: pip install 'real-research[embedded-db]'")
        return "pg0"

    try:
        pg = Pg0(
            name=_PG0_NAME, data_dir=MEMORY_STORE_DIR,
            username=_PG0_USER, password=_PG0_PASS, database=_PG0_DB,
        )
    except TypeError:
        # Older pg0 versions without data_dir parameter
        pg = Pg0(
            name=_PG0_NAME, username=_PG0_USER,
            password=_PG0_PASS, database=_PG0_DB,
        )

    info = pg.start()
    uri = info.uri
    logger.info(f"pg0 started: {uri}")
    _write_cached_uri(uri)
    return uri


def resolve_db_url() -> str:
    """Resolve database URL from config or pg0."""
    cfg = load_config()
    if cfg["database_url"]:
        return cfg["database_url"]
    return _start_local_pg0()


# ───────────────────────────────────────────────
# MemoryEngine construction
# ───────────────────────────────────────────────

def _build_engine_kwargs(cfg: dict, db_url: str) -> dict:
    """Build MemoryEngine constructor kwargs from resolved config."""
    kwargs: dict = {
        "db_url": db_url,
        "embeddings": OpenAIEmbeddings(
            api_key=cfg["embedding_api_key"],
            model=cfg["embedding_model"],
            base_url=cfg["embedding_base_url"],
            batch_size=10,  # DashScope limit
        ),
        "cross_encoder": CohereCrossEncoder(
            api_key=cfg["rerank_api_key"],
            model=cfg["rerank_model"],
            base_url=cfg["rerank_base_url"],
        ),
        "query_analyzer": DateparserQueryAnalyzer(),
        "task_backend": SyncTaskBackend(),
        "run_migrations": False,  # Skip migrations - database already set up
        # LLM config — passed directly, bypassing hindsight_api env-var defaults
        "memory_llm_provider": cfg["llm_provider"],
        "memory_llm_api_key": cfg["llm_api_key"],
        "memory_llm_base_url": cfg["llm_base_url"],
    }

    if cfg["llm_model"]:
        kwargs["memory_llm_model"] = cfg["llm_model"]

    # Per-operation LLM overrides
    for op in ("retain", "reflect", "consolidation"):
        provider = cfg.get(f"{op}_llm_provider")
        model = cfg.get(f"{op}_llm_model")
        if provider:
            kwargs[f"{op}_llm_provider"] = provider
        if model:
            kwargs[f"{op}_llm_model"] = model

    return kwargs


def create_engine() -> MemoryEngine:
    """Create a configured MemoryEngine (not yet initialized).

    Caller must ``await engine.initialize()``.
    """
    cfg = load_config()
    db_url = resolve_db_url()
    kwargs = _build_engine_kwargs(cfg, db_url)
    return MemoryEngine(**kwargs)


def create_embeddings() -> OpenAIEmbeddings:
    """Create a standalone OpenAIEmbeddings instance (for route.py)."""
    cfg = load_config()
    return OpenAIEmbeddings(
        api_key=cfg["embedding_api_key"],
        model=cfg["embedding_model"],
        base_url=cfg["embedding_base_url"],
    )


def default_context() -> RequestContext:
    """Create a default RequestContext for CLI tools."""
    return RequestContext(internal=True)


def default_bank_id() -> str:
    """Return the default bank ID from config."""
    cfg = load_config()
    return cfg["default_bank"]


@asynccontextmanager
async def engine_context():
    """Async context manager: create → initialize → yield → close."""
    engine = create_engine()
    try:
        await engine.initialize()
        yield engine
    finally:
        await engine.close()
