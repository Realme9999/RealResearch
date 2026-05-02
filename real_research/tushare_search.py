"""Search Tushare research reports from the local index.

Usage:
    rr-tushare-search --query "半导体产能不足"
    rr-tushare-search --query "华为" --industry "电子"
    rr-tushare-search --query "人工智能" --org "中信证券" -n 10
    rr-tushare-search --query "大模型" --stock 002230.SZ
    rr-tushare-search --query "新能源" --start-date 20260401
    rr-tushare-search --query "半导体" --mode keyword   # keyword-only search
    rr-tushare-search --query "半导体" --mode semantic   # semantic-only search
"""

import argparse
import json
import os
import sys

from .utils import setup_utf8, load_dotenv

# Load .env on import
load_dotenv()

# ── Constants ────────────────────────────────────────────────

REPORTS_TABLE = "tushare.reports"

# DashScope / OpenAI-compatible embedding config
EMBEDDING_MODEL = os.environ.get("RR_EMBEDDING_MODEL", "text-embedding-v4")
EMBEDDING_BASE_URL = os.environ.get("RR_EMBEDDING_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
EMBEDDING_API_KEY = os.environ.get("RR_EMBEDDING_API_KEY", "")


# ── Embedding helper ─────────────────────────────────────────

def embed_query(text: str) -> list[float]:
    """Generate embedding for the search query."""
    import openai

    client = openai.OpenAI(
        api_key=EMBEDDING_API_KEY,
        base_url=EMBEDDING_BASE_URL,
    )
    resp = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text,
    )
    return resp.data[0].embedding


# ── Search functions ─────────────────────────────────────────

async def search_semantic(
    conn,
    query_embedding: list[float],
    max_results: int = 20,
    filters: dict | None = None,
) -> list[dict]:
    """Semantic search using pgvector cosine similarity."""
    # Build WHERE clause from filters
    where_parts = ["embedding IS NOT NULL"]
    params = [query_embedding]  # $1 = query embedding
    param_idx = 2

    if filters:
        if filters.get("industry"):
            where_parts.append(f"ind_name = ${param_idx}")
            params.append(filters["industry"])
            param_idx += 1
        if filters.get("org"):
            where_parts.append(f"org = ${param_idx}")
            params.append(filters["org"])
            param_idx += 1
        if filters.get("stock"):
            where_parts.append(f"ts_code = ${param_idx}")
            params.append(filters["stock"])
            param_idx += 1
        if filters.get("report_type"):
            where_parts.append(f"report_type = ${param_idx}")
            params.append(filters["report_type"])
            param_idx += 1
        if filters.get("start_date"):
            where_parts.append(f"trade_date >= ${param_idx}")
            params.append(filters["start_date"])
            param_idx += 1
        if filters.get("end_date"):
            where_parts.append(f"trade_date <= ${param_idx}")
            params.append(filters["end_date"])
            param_idx += 1

    where_sql = " AND ".join(where_parts)
    params.append(max_results)  # LIMIT

    sql = f"""
        SELECT
            id, trade_date, ts_code, title, report_type, author,
            org, ind_name, pdf_url, abstr,
            1 - (embedding <=> $1::vector) AS score
        FROM {REPORTS_TABLE}
        WHERE {where_sql}
        ORDER BY embedding <=> $1::vector
        LIMIT ${param_idx}
    """

    rows = await conn.fetch(sql, *params)
    return [dict(r) for r in rows]


async def search_keyword(
    conn,
    keyword: str,
    max_results: int = 20,
    filters: dict | None = None,
) -> list[dict]:
    """Keyword search using pg_trgm trigram similarity."""
    # Build WHERE clause from filters
    where_parts = []
    params = [keyword]  # $1 = keyword
    param_idx = 2

    # Trigram similarity search on title and content
    where_parts.append(f"(title ILIKE '%' || $1 || '%' OR content ILIKE '%' || $1 || '%')")

    if filters:
        if filters.get("industry"):
            where_parts.append(f"ind_name = ${param_idx}")
            params.append(filters["industry"])
            param_idx += 1
        if filters.get("org"):
            where_parts.append(f"org = ${param_idx}")
            params.append(filters["org"])
            param_idx += 1
        if filters.get("stock"):
            where_parts.append(f"ts_code = ${param_idx}")
            params.append(filters["stock"])
            param_idx += 1
        if filters.get("report_type"):
            where_parts.append(f"report_type = ${param_idx}")
            params.append(filters["report_type"])
            param_idx += 1
        if filters.get("start_date"):
            where_parts.append(f"trade_date >= ${param_idx}")
            params.append(filters["start_date"])
            param_idx += 1
        if filters.get("end_date"):
            where_parts.append(f"trade_date <= ${param_idx}")
            params.append(filters["end_date"])
            param_idx += 1

    where_sql = " AND ".join(where_parts) if where_parts else "TRUE"
    params.append(max_results)  # LIMIT

    # Use trigram similarity for ranking
    sql = f"""
        SELECT
            id, trade_date, ts_code, title, report_type, author,
            org, ind_name, pdf_url, abstr,
            GREATEST(
                similarity(title, $1),
                similarity(COALESCE(content, ''), $1)
            ) AS score
        FROM {REPORTS_TABLE}
        WHERE {where_sql}
        ORDER BY score DESC
        LIMIT ${param_idx}
    """

    rows = await conn.fetch(sql, *params)
    return [dict(r) for r in rows]


async def search_hybrid(
    conn,
    query: str,
    query_embedding: list[float],
    max_results: int = 20,
    semantic_weight: float = 0.7,
    keyword_weight: float = 0.3,
    filters: dict | None = None,
) -> list[dict]:
    """Hybrid search combining semantic and keyword scores."""
    # Get results from both search methods (fetch more, then merge)
    fetch_limit = max_results * 3

    semantic_results = await search_semantic(conn, query_embedding, fetch_limit, filters)
    keyword_results = await search_keyword(conn, query, fetch_limit, filters)

    # Merge results by ID, combining scores
    merged = {}
    for r in semantic_results:
        rid = r["id"]
        merged[rid] = dict(r)
        merged[rid]["_semantic_score"] = float(r["score"])
        merged[rid]["_keyword_score"] = 0.0

    for r in keyword_results:
        rid = r["id"]
        if rid in merged:
            merged[rid]["_keyword_score"] = float(r["score"])
        else:
            merged[rid] = dict(r)
            merged[rid]["_semantic_score"] = 0.0
            merged[rid]["_keyword_score"] = float(r["score"])

    # Calculate combined score
    for rid, r in merged.items():
        r["score"] = (
            semantic_weight * r.get("_semantic_score", 0) +
            keyword_weight * r.get("_keyword_score", 0)
        )
        # Clean up internal fields
        r.pop("_semantic_score", None)
        r.pop("_keyword_score", None)

    # Sort by combined score, return top N
    results = sorted(merged.values(), key=lambda x: x["score"], reverse=True)
    return results[:max_results]


# ── Main logic ───────────────────────────────────────────────

async def run_search(args) -> dict:
    """Core search logic."""
    import asyncpg

    # Validate
    if not EMBEDDING_API_KEY and args.mode != "keyword":
        return {"error": "RR_EMBEDDING_API_KEY is not set. Use --mode keyword for keyword-only search."}

    # Connect to database
    from .engine import resolve_db_url
    db_url = resolve_db_url()

    conn = await asyncpg.connect(db_url)

    # Register pgvector type
    from pgvector.asyncpg import register_vector
    await register_vector(conn)

    try:
        # Check if index has data
        total = await conn.fetchval(f"SELECT COUNT(*) FROM {REPORTS_TABLE}")
        if total == 0:
            return {
                "error": "Index is empty. Run 'rr-tushare-index --months 3' first to build the index.",
                "query": args.query,
                "results": [],
                "total": 0,
                "source": "tushare-index",
            }

        # Build filters
        filters = {}
        if args.industry:
            filters["industry"] = args.industry
        if args.org:
            filters["org"] = args.org
        if args.stock:
            filters["stock"] = args.stock
        if args.type:
            filters["report_type"] = args.type
        if args.start_date:
            filters["start_date"] = args.start_date
        if args.end_date:
            filters["end_date"] = args.end_date

        # Generate query embedding (unless keyword-only mode)
        query_embedding = None
        if args.mode != "keyword":
            query_embedding = embed_query(args.query)

        # Execute search
        if args.mode == "semantic" and query_embedding:
            raw_results = await search_semantic(conn, query_embedding, args.max_results, filters)
        elif args.mode == "keyword":
            raw_results = await search_keyword(conn, args.query, args.max_results, filters)
        else:
            # Hybrid (default)
            raw_results = await search_hybrid(
                conn, args.query, query_embedding, args.max_results,
                semantic_weight=args.semantic_weight,
                keyword_weight=args.keyword_weight,
                filters=filters,
            )

        # Format results
        results = []
        for r in raw_results:
            trade_date = r.get("trade_date")
            date_str = trade_date.strftime("%Y%m%d") if trade_date else None

            # Build content summary
            abstr = r.get("abstr") or ""
            content_parts = []
            if abstr:
                content_parts.append(abstr[:300])
            if r.get("author"):
                content_parts.append(f"分析师: {r['author']}")
            if r.get("org"):
                content_parts.append(f"机构: {r['org']}")
            if r.get("report_type"):
                content_parts.append(f"类型: {r['report_type']}")

            results.append({
                "title": r.get("title", ""),
                "url": r.get("pdf_url") or "",
                "content": "\n".join(content_parts),
                "score": round(float(r.get("score", 0)), 4),
                "metadata": {
                    "id": r.get("id"),
                    "ts_code": r.get("ts_code"),
                    "trade_date": date_str,
                    "report_type": r.get("report_type"),
                    "author": r.get("author"),
                    "org": r.get("org"),
                    "ind_name": r.get("ind_name"),
                },
            })

        return {
            "query": args.query,
            "mode": args.mode,
            "filters": filters if filters else None,
            "results": results,
            "total": len(results),
            "source": "tushare-index",
        }

    finally:
        await conn.close()


# ── CLI entry point ──────────────────────────────────────────

def main():
    setup_utf8()
    parser = argparse.ArgumentParser(
        description="RealResearch: search Tushare research reports"
    )
    parser.add_argument(
        "--query", "-q", required=True,
        help="Search query"
    )
    parser.add_argument(
        "--max-results", "-n", type=int, default=20,
        help="Maximum results to return (default: 20)"
    )
    parser.add_argument(
        "--mode", "-m", default="hybrid",
        choices=["semantic", "keyword", "hybrid"],
        help="Search mode (default: hybrid)"
    )
    parser.add_argument(
        "--semantic-weight", type=float, default=0.7,
        help="Weight for semantic score in hybrid mode (default: 0.7)"
    )
    parser.add_argument(
        "--keyword-weight", type=float, default=0.3,
        help="Weight for keyword score in hybrid mode (default: 0.3)"
    )
    parser.add_argument(
        "--industry", "-i", type=str, default=None,
        help="Filter by industry name (e.g., '电子', '半导体')"
    )
    parser.add_argument(
        "--org", "-o", type=str, default=None,
        help="Filter by institution name (e.g., '中信证券')"
    )
    parser.add_argument(
        "--stock", "-s", type=str, default=None,
        help="Filter by stock code (e.g., '600519.SH')"
    )
    parser.add_argument(
        "--type", "-t", type=str, default=None,
        help="Filter by report type (e.g., '个股研报', '行业研报')"
    )
    parser.add_argument(
        "--start-date", type=str, default=None,
        help="Filter: start date YYYYMMDD"
    )
    parser.add_argument(
        "--end-date", type=str, default=None,
        help="Filter: end date YYYYMMDD"
    )
    args = parser.parse_args()

    from .logger import get_logger
    logger = get_logger(default_query=args.query)
    if logger:
        logger.start_step("rr-tushare-search", {
            "query": args.query, "mode": args.mode, "max_results": args.max_results,
            "industry": args.industry, "org": args.org, "stock": args.stock,
        })

    import asyncio
    result = asyncio.run(run_search(args))

    if logger:
        summary = None
        if "error" not in result:
            summary = {
                "total_results": result.get("total", 0),
                "mode": result.get("mode", ""),
                "filters": result.get("filters"),
                "sources": [r.get("url", "") for r in result.get("results", [])[:5]],
            }
        logger.end_step(result_summary=summary, error=result.get("error"))

    print(json.dumps(result, ensure_ascii=False, indent=2))
    if "error" in result:
        sys.exit(1)
