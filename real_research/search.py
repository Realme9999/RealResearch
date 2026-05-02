"""Web search via Tavily API.

Usage:
    rr-search --query "量子计算最新进展"
    rr-search --query "AI agents" --max-results 8 --search-depth advanced
"""

import argparse
import json
import os
import sys

from .utils import setup_utf8, SearchCache, load_dotenv

# Load .env on import
load_dotenv()

TAVILY_MISSING_MSG = (
    "RR_SEARCH_API_KEY is not set. Get a free key at https://tavily.com"
)


def search_tavily(query: str, max_results: int = 8, search_depth: str = "advanced") -> dict:
    """Search via Tavily API."""
    api_key = os.environ.get("RR_SEARCH_API_KEY")
    if not api_key:
        raise RuntimeError("RR_SEARCH_API_KEY not set")

    from tavily import TavilyClient

    client = TavilyClient(api_key=api_key)
    response = client.search(
        query=query,
        max_results=max_results,
        search_depth=search_depth,
        include_answer=True,
    )

    results = []
    for r in response.get("results", []):
        results.append({
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "content": r.get("content", ""),
            "score": r.get("score", 0),
        })

    return {
        "query": query,
        "answer": response.get("answer", ""),
        "results": results,
        "source": "tavily",
    }


def search(
    query: str,
    max_results: int = 8,
    search_depth: str = "advanced",
    cache_ttl: int = 1800,
) -> dict:
    """Search the web via Tavily API with caching."""
    if not os.environ.get("RR_SEARCH_API_KEY"):
        return {"error": TAVILY_MISSING_MSG}

    cache = SearchCache(ttl=cache_ttl)

    cached = cache.get(query, max_results, search_depth)
    if cached is not None:
        cached["cached"] = True
        return cached

    try:
        result = search_tavily(query, max_results, search_depth)
    except Exception as e:
        return {"error": f"Tavily search failed: {e}"}

    cache.set(query, max_results, search_depth, result)
    return result


def main():
    setup_utf8()
    parser = argparse.ArgumentParser(description="RealResearch: web search")
    parser.add_argument("--query", "-q", required=True, help="Search query")
    parser.add_argument("--max-results", "-n", type=int, default=8, help="Max results (default: 8)")
    parser.add_argument("--search-depth", "-d", default="advanced", choices=["basic", "advanced"])
    parser.add_argument("--cache-ttl", type=int, default=1800, help="Cache TTL seconds (default: 1800)")
    args = parser.parse_args()

    from .logger import get_logger
    logger = get_logger(default_query=args.query)
    if logger:
        logger.start_step("rr-search", {"query": args.query, "max_results": args.max_results, "search_depth": args.search_depth})

    result = search(args.query, args.max_results, args.search_depth, cache_ttl=args.cache_ttl)

    if logger:
        summary = None
        if "error" not in result:
            summary = {
                "total_results": len(result.get("results", [])),
                "answer_preview": (result.get("answer") or "")[:200],
                "sources": [r.get("url", "") for r in result.get("results", [])[:5]],
                "cached": result.get("cached", False),
            }
        logger.end_step(result_summary=summary, error=result.get("error"))

    print(json.dumps(result, ensure_ascii=False, indent=2))
    if "error" in result:
        sys.exit(1)
