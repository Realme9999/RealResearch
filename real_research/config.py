"""Unified configuration reader for RealResearch.

Reads RR_* environment variables from .env and validates required keys.
All Hindsight configuration is derived from these variables — no separate
HINDSIGHT_API_* setup is needed.
"""

import os

from .utils import load_dotenv

# Load .env on first import so all RR_* vars are available
load_dotenv()


def _require(env_name: str) -> str:
    val = os.environ.get(env_name)
    if not val:
        raise ValueError(f"{env_name} is required. Set it in your .env file.")
    return val


def load_config() -> dict:
    """Read all RR_* env vars into a structured config dict.

    Raises ValueError if any required key is missing.
    """
    cfg = {
        # ── API keys (required) ────────────────────────
        "embedding_api_key": _require("RR_EMBEDDING_API_KEY"),
        "rerank_api_key": _require("RR_RERANK_API_KEY"),
        "llm_api_key": _require("RR_LLM_API_KEY"),
        "search_api_key": _require("RR_SEARCH_API_KEY"),

        # ── Embedding ──────────────────────────────────
        "embedding_model": os.environ.get(
            "RR_EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-4B"
        ),
        "embedding_base_url": os.environ.get(
            "RR_EMBEDDING_BASE_URL", "https://api.siliconflow.cn/v1"
        ).rstrip("/"),
        "embedding_dimensions": int(
            os.environ.get("RR_EMBEDDING_DIMENSIONS", "1024")
        ),

        # ── Rerank ─────────────────────────────────────
        "rerank_model": os.environ.get(
            "RR_RERANK_MODEL", "Qwen/Qwen3-Reranker-8B"
        ),
        "rerank_base_url": os.environ.get(
            "RR_RERANK_BASE_URL", "https://api.siliconflow.cn/v1/rerank"
        ).rstrip("/"),

        # ── LLM ────────────────────────────────────────
        "llm_provider": os.environ.get("RR_LLM_PROVIDER", "groq"),
        "llm_model": os.environ.get("RR_LLM_MODEL") or None,
        "llm_base_url": os.environ.get("RR_LLM_BASE_URL", "").rstrip("/"),

        # ── Per-operation LLM overrides (optional) ─────
        "retain_llm_provider": os.environ.get("RR_RETAIN_LLM_PROVIDER") or None,
        "retain_llm_model": os.environ.get("RR_RETAIN_LLM_MODEL") or None,
        "reflect_llm_provider": os.environ.get("RR_REFLECT_LLM_PROVIDER") or None,
        "reflect_llm_model": os.environ.get("RR_REFLECT_LLM_MODEL") or None,
        "consolidation_llm_provider": os.environ.get("RR_CONSOLIDATION_LLM_PROVIDER") or None,
        "consolidation_llm_model": os.environ.get("RR_CONSOLIDATION_LLM_MODEL") or None,

        # ── Database (optional) ────────────────────────
        "database_url": os.environ.get("RR_DATABASE_URL") or None,

        # ── Defaults ───────────────────────────────────
        "default_bank": os.environ.get("RR_DEFAULT_BANK", "deep-research"),

        # ── Logging ────────────────────────────────────
        "log_enabled": os.environ.get("RR_LOG_ENABLED", "true").lower() == "true",
        "log_full_results": os.environ.get("RR_LOG_FULL_RESULTS", "false").lower() == "true",
        "log_retention_days": int(os.environ.get("RR_LOG_RETENTION_DAYS", "90")),
    }

    return cfg


def check_config() -> dict:
    """Return a dict of config readiness checks (never raises)."""
    checks = {}
    required = {
        "embedding_api_key": "RR_EMBEDDING_API_KEY",
        "rerank_api_key": "RR_RERANK_API_KEY",
        "llm_api_key": "RR_LLM_API_KEY",
        "search_api_key": "RR_SEARCH_API_KEY",
    }
    for field, env_name in required.items():
        checks[field] = bool(os.environ.get(env_name))
    return checks
