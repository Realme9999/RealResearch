"""Verify all RealResearch dependencies are ready.

Usage:
    rr-env-check
"""

import json
import os
import sys

# Auto-add hindsightbase path (same as engine.py)
_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_script_dir)
_hindsight_slim = os.path.join(_project_root, "hindsightbase", "hindsight-api-slim")
if not os.path.isdir(_hindsight_slim):
    _project_root = os.path.dirname(_project_root)
    _hindsight_slim = os.path.join(_project_root, "hindsightbase", "hindsight-api-slim")
if os.path.isdir(_hindsight_slim) and _hindsight_slim not in sys.path:
    sys.path.insert(0, _hindsight_slim)

from .config import check_config
from .utils import setup_utf8, print_json


def check_all() -> dict:
    checks = {
        "python": sys.version,
    }

    # Config keys
    config_checks = check_config()
    checks.update(config_checks)

    # Core Python packages
    packages = {
        "tavily": "tavily",
        "requests": "requests",
        "bs4": "beautifulsoup4",
        "asyncpg": "asyncpg",
        "pgvector": "pgvector",
        "openai": "openai",
        "sqlalchemy": "sqlalchemy",
        "pydantic": "pydantic",
        "tiktoken": "tiktoken",
    }
    for module, pip_name in packages.items():
        try:
            __import__(module)
            checks[f"pkg_{pip_name}"] = True
        except ImportError:
            checks[f"pkg_{pip_name}"] = False

    # Hindsight importability
    try:
        from hindsight_api import MemoryEngine, RequestContext
        checks["pkg_hindsight_api"] = True
    except ImportError as e:
        checks["pkg_hindsight_api"] = False
        checks["pkg_hindsight_api_error"] = str(e)

    # pg0-embedded
    try:
        from pg0 import Pg0
        checks["pg0_embedded"] = True
    except ImportError:
        checks["pg0_embedded"] = False

    # Tushare
    try:
        import tushare
        checks["pkg_tushare"] = True
    except ImportError:
        checks["pkg_tushare"] = False
    checks["tushare_token"] = bool(os.environ.get("RR_TUSHARE_TOKEN"))

    # Overall status
    all_config_ok = all(v for k, v in checks.items() if k in config_checks.values() or k in config_checks)
    required_keys = ["embedding_api_key", "rerank_api_key", "llm_api_key", "search_api_key"]
    config_ok = all(checks.get(k, False) for k in required_keys)
    checks["status"] = "READY" if config_ok else "NOT READY"

    return checks


def main():
    setup_utf8()
    result = check_all()
    print_json(result)
    if result["status"] != "READY":
        sys.exit(1)
