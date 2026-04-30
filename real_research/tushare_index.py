"""Build and maintain a Tushare research report index in PostgreSQL.

Usage:
    rr-tushare-index --months 3          # First-time: index last 3 months
    rr-tushare-index                     # Incremental: fetch new reports since last run
    rr-tushare-index --dry-run           # Show what would be fetched
    rr-tushare-index --start-date 20260401 --end-date 20260415
    rr-tushare-index --force             # Drop and rebuild the entire index
    rr-tushare-index --no-embed          # Index without generating embeddings
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta

from .utils import setup_utf8, load_dotenv

# Load .env on import
load_dotenv()

# ── Constants ────────────────────────────────────────────────

SCHEMA_NAME = "tushare"
REPORTS_TABLE = f"{SCHEMA_NAME}.reports"
META_TABLE = f"{SCHEMA_NAME}.sync_meta"

# DashScope / OpenAI-compatible embedding config
EMBEDDING_MODEL = os.environ.get("RR_EMBEDDING_MODEL", "text-embedding-v4")
EMBEDDING_BASE_URL = os.environ.get("RR_EMBEDDING_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
EMBEDDING_API_KEY = os.environ.get("RR_EMBEDDING_API_KEY", "")

# SQL for schema creation
SQL_CREATE_SCHEMA = f"CREATE SCHEMA IF NOT EXISTS {SCHEMA_NAME}"

SQL_CREATE_REPORTS = f"""
CREATE TABLE IF NOT EXISTS {REPORTS_TABLE} (
    id             BIGSERIAL PRIMARY KEY,
    trade_date     DATE        NOT NULL,
    ts_code        TEXT,
    title          TEXT        NOT NULL,
    report_type    TEXT,
    author         TEXT,
    org            TEXT,
    ind_name       TEXT,
    pdf_url        TEXT,
    abstr          TEXT,
    content        TEXT,
    embedding      VECTOR(1024)
)
"""

SQL_CREATE_DEDUP_INDEX = f"""
CREATE UNIQUE INDEX IF NOT EXISTS idx_reports_dedup ON {REPORTS_TABLE}
    (COALESCE(ts_code, ''), title, trade_date)
"""

SQL_CREATE_INDEXES = [
    # Semantic search: HNSW cosine
    f"""CREATE INDEX IF NOT EXISTS idx_reports_embedding ON {REPORTS_TABLE}
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)""",
    # Metadata filters
    f"CREATE INDEX IF NOT EXISTS idx_reports_trade_date ON {REPORTS_TABLE} (trade_date DESC)",
    f"CREATE INDEX IF NOT EXISTS idx_reports_ts_code ON {REPORTS_TABLE} (ts_code)",
    f"CREATE INDEX IF NOT EXISTS idx_reports_org ON {REPORTS_TABLE} (org)",
    f"CREATE INDEX IF NOT EXISTS idx_reports_ind_name ON {REPORTS_TABLE} (ind_name)",
    f"CREATE INDEX IF NOT EXISTS idx_reports_type ON {REPORTS_TABLE} (report_type)",
]

SQL_CREATE_TRGM_INDEXES = [
    # Trigram indexes for Chinese keyword search
    f"CREATE INDEX IF NOT EXISTS idx_reports_title_trgm ON {REPORTS_TABLE} USING gin (title gin_trgm_ops)",
    f"CREATE INDEX IF NOT EXISTS idx_reports_content_trgm ON {REPORTS_TABLE} USING gin (content gin_trgm_ops)",
]

SQL_CREATE_META = f"""
CREATE TABLE IF NOT EXISTS {META_TABLE} (
    key   TEXT PRIMARY KEY,
    value TEXT
)
"""

SQL_INIT_META = f"""
INSERT INTO {META_TABLE} (key, value) VALUES
    ('last_indexed_date', NULL),
    ('total_records', '0'),
    ('embedding_model', $1),
    ('embedding_dimensions', '1024')
ON CONFLICT (key) DO NOTHING
"""


# ── Database helpers ─────────────────────────────────────────

async def ensure_schema(conn):
    """Create tushare schema, tables, and indexes if they don't exist."""
    await conn.execute(SQL_CREATE_SCHEMA)
    # Enable pg_trgm extension (needed for trigram indexes)
    try:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    except Exception:
        pass  # May already exist or require superuser
    await conn.execute(SQL_CREATE_REPORTS)
    await conn.execute(SQL_CREATE_DEDUP_INDEX)
    for sql in SQL_CREATE_INDEXES:
        await conn.execute(sql)
    for sql in SQL_CREATE_TRGM_INDEXES:
        try:
            await conn.execute(sql)
        except Exception:
            pass  # pg_trgm might not be available
    await conn.execute(SQL_CREATE_META)
    await conn.execute(SQL_INIT_META, EMBEDDING_MODEL)


async def get_sync_state(conn) -> dict:
    """Read sync metadata from tushare.sync_meta."""
    rows = await conn.fetch(
        f"SELECT key, value FROM {META_TABLE}"
    )
    return {r["key"]: r["value"] for r in rows}


async def update_sync_state(conn, key: str, value: str):
    """Update a single sync_meta entry."""
    await conn.execute(
        f"UPDATE {META_TABLE} SET value = $1 WHERE key = $2",
        value, key,
    )


async def get_total_records(conn) -> int:
    """Count total records in the index."""
    row = await conn.fetchval(f"SELECT COUNT(*) FROM {REPORTS_TABLE}")
    return row or 0


async def clear_index(conn):
    """Drop and recreate the entire index."""
    await conn.execute(f"TRUNCATE {REPORTS_TABLE}")
    await conn.execute(f"UPDATE {META_TABLE} SET value = NULL WHERE key = 'last_indexed_date'")
    await conn.execute(f"UPDATE {META_TABLE} SET value = '0' WHERE key = 'total_records'")


async def insert_records(conn, records: list[dict], embeddings: list[list[float] | None]) -> tuple[int, int]:
    """Insert records into the index, skipping duplicates.

    Returns (inserted_count, skipped_count).
    """
    inserted = 0
    skipped = 0
    for rec, emb in zip(records, embeddings):
        content = (rec.get("title") or "") + "\n" + (rec.get("abstr") or "")
        emb_list = emb  # None if --no-embed
        try:
            await conn.execute(
                f"""INSERT INTO {REPORTS_TABLE}
                    (trade_date, ts_code, title, report_type, author, org, ind_name, pdf_url, abstr, content, embedding)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                    ON CONFLICT (ts_code, title, trade_date) DO NOTHING""",
                rec["trade_date"],
                rec.get("ts_code"),
                rec.get("title", ""),
                rec.get("report_type"),
                rec.get("author"),
                rec.get("org"),
                rec.get("ind_name"),
                rec.get("pdf_url"),
                rec.get("abstr"),
                content,
                emb_list,
            )
            # ON CONFLICT DO NOTHING doesn't tell us if it was inserted or skipped
            # We need to check separately
            inserted += 1
        except Exception:
            skipped += 1
    return inserted, skipped


async def insert_records_batch(conn, records: list[dict], embeddings: list[list[float] | None]) -> tuple[int, int]:
    """Insert records with dedup check, handling NULL ts_code.

    Returns (new_count, skipped_count).
    """
    if not records:
        return 0, 0

    # Check which records already exist (use IS NOT DISTINCT FROM for NULL handling)
    existing = set()
    for rec in records:
        row = await conn.fetchrow(
            f"""SELECT id FROM {REPORTS_TABLE}
                WHERE ts_code IS NOT DISTINCT FROM $1
                  AND title = $2
                  AND trade_date = $3""",
            rec.get("ts_code"), rec.get("title", ""), rec["trade_date"],
        )
        if row:
            existing.add((rec.get("ts_code"), rec.get("title", ""), rec["trade_date"]))

    # Filter out existing records
    new_records = []
    new_embeddings = []
    for rec, emb in zip(records, embeddings):
        key = (rec.get("ts_code"), rec.get("title", ""), rec["trade_date"])
        if key not in existing:
            new_records.append(rec)
            new_embeddings.append(emb)

    skipped = len(existing)
    if not new_records:
        return 0, skipped

    # Insert new records
    inserted = 0
    for rec, emb in zip(new_records, new_embeddings):
        content = (rec.get("title") or "") + "\n" + (rec.get("abstr") or "")
        try:
            await conn.execute(
                f"""INSERT INTO {REPORTS_TABLE}
                    (trade_date, ts_code, title, report_type, author, org, ind_name, pdf_url, abstr, content, embedding)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)""",
                rec["trade_date"],
                rec.get("ts_code"),
                rec.get("title", ""),
                rec.get("report_type"),
                rec.get("author"),
                rec.get("org"),
                rec.get("ind_name"),
                rec.get("pdf_url"),
                rec.get("abstr"),
                content,
                emb,
            )
            inserted += 1
        except Exception:
            skipped += 1

    return inserted, skipped


# ── Tushare helpers ──────────────────────────────────────────

def fetch_tushare_day(token: str, trade_date: str, rate_limit_ms: int = 300) -> list[dict]:
    """Fetch research reports for a single day from Tushare API.

    Args:
        token: Tushare API token
        trade_date: Date in YYYYMMDD format
        rate_limit_ms: Delay between API calls in milliseconds

    Returns:
        List of report dicts with standardized field names
    """
    import tushare as ts
    ts.set_token(token)
    pro = ts.pro_api()

    df = pro.research_report(
        trade_date=trade_date,
        fields='trade_date,title,abstr,report_type,author,name,ts_code,inst_csname,ind_name,url',
    )

    if df is None or len(df) == 0:
        return []

    # Replace pandas NaN with None for asyncpg compatibility
    import math
    df = df.where(df.notna(), None)

    records = []
    for _, row in df.iterrows():
        def _clean(val):
            """Convert NaN/NaT to None, ensure str or None."""
            if val is None:
                return None
            if isinstance(val, float) and math.isnan(val):
                return None
            s = str(val).strip()
            return s if s and s != "nan" and s != "None" else None

        trade_date_raw = row.get("trade_date")
        if trade_date_raw is None:
            continue
        td = _clean(trade_date_raw)
        if td is None:
            continue

        records.append({
            "trade_date": datetime.strptime(td, "%Y%m%d").date(),
            "ts_code": _clean(row.get("ts_code")),
            "title": _clean(row.get("title")) or "",
            "report_type": _clean(row.get("report_type")),
            "author": _clean(row.get("name")),  # Tushare field 'name' = analyst name
            "org": _clean(row.get("inst_csname")),  # Tushare field 'inst_csname' = institution
            "ind_name": _clean(row.get("ind_name")),
            "pdf_url": _clean(row.get("url")),
            "abstr": _clean(row.get("abstr")),
        })

    # Rate limit
    if rate_limit_ms > 0:
        time.sleep(rate_limit_ms / 1000.0)

    return records


def generate_embedding(text: str) -> list[float]:
    """Generate embedding for a single text using DashScope API."""
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


def generate_embeddings_batch(texts: list[str], batch_size: int = 16, rate_limit_ms: int = 100) -> list[list[float]]:
    """Generate embeddings for a batch of texts.

    Args:
        texts: List of text strings to embed
        batch_size: Number of texts per API call
        rate_limit_ms: Delay between API calls in milliseconds

    Returns:
        List of embedding vectors (same order as input)
    """
    import openai

    if not texts:
        return []

    client = openai.OpenAI(
        api_key=EMBEDDING_API_KEY,
        base_url=EMBEDDING_BASE_URL,
    )

    all_embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        resp = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=batch,
        )
        batch_embeddings = [d.embedding for d in resp.data]
        all_embeddings.extend(batch_embeddings)

        # Rate limit between batches
        if i + batch_size < len(texts) and rate_limit_ms > 0:
            time.sleep(rate_limit_ms / 1000.0)

    return all_embeddings


def detect_embedding_dimension() -> int:
    """Detect the embedding dimension by making a test API call."""
    if not EMBEDDING_API_KEY:
        return 1024  # Default

    try:
        emb = generate_embedding("test")
        return len(emb)
    except Exception:
        return 1024  # Default fallback


# ── Date helpers ─────────────────────────────────────────────

def date_range(start: str, end: str) -> list[str]:
    """Generate a list of YYYYMMDD strings from start to end (inclusive)."""
    start_dt = datetime.strptime(start, "%Y%m%d")
    end_dt = datetime.strptime(end, "%Y%m%d")
    dates = []
    current = start_dt
    while current <= end_dt:
        dates.append(current.strftime("%Y%m%d"))
        current += timedelta(days=1)
    return dates


def today_str() -> str:
    """Get today's date as YYYYMMDD."""
    return datetime.now().strftime("%Y%m%d")


def days_ago_str(days: int) -> str:
    """Get date N days ago as YYYYMMDD."""
    return (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")


def next_day(date_str: str) -> str:
    """Get the next day after YYYYMMDD."""
    dt = datetime.strptime(date_str, "%Y%m%d")
    return (dt + timedelta(days=1)).strftime("%Y%m%d")


# ── Main logic ───────────────────────────────────────────────

async def run_index(args) -> dict:
    """Core indexing logic."""
    import asyncpg

    token = os.environ.get("RR_TUSHARE_TOKEN")
    if not token:
        return {"error": "RR_TUSHARE_TOKEN is not set. Add it to your .env file."}

    # Connect to database
    from .engine import resolve_db_url
    db_url = resolve_db_url()

    conn = await asyncpg.connect(db_url)

    # Register pgvector type for asyncpg
    from pgvector.asyncpg import register_vector
    await register_vector(conn)

    try:
        # Ensure schema exists
        await ensure_schema(conn)

        # Force rebuild: clear everything
        if args.force:
            await clear_index(conn)

        # Determine date range
        sync_state = await get_sync_state(conn)
        last_date = sync_state.get("last_indexed_date")

        if args.start_date:
            start_date = args.start_date
        elif last_date and not args.force:
            # Incremental: start from the day after last indexed date
            start_date = next_day(last_date)
        else:
            # First time: use --months parameter
            months = args.months or 3
            start_date = days_ago_str(months * 30)

        end_date = args.end_date or today_str()

        # Check if there's anything to do
        if start_date > end_date:
            total = await get_total_records(conn)
            return {
                "status": "up_to_date",
                "message": "Index is already up to date",
                "last_indexed_date": last_date,
                "total_in_index": total,
            }

        # Dry run: just show the plan
        if args.dry_run:
            dates = date_range(start_date, end_date)
            total = await get_total_records(conn)
            return {
                "status": "dry_run",
                "planned_range": {"from": start_date, "to": end_date},
                "days_to_process": len(dates),
                "estimated_records": len(dates) * 260,  # ~260 per day
                "total_in_index": total,
                "last_indexed_date": last_date,
            }

        # ── Actual indexing ──────────────────────────────────
        start_time = time.time()
        dates = date_range(start_date, end_date)
        total_new = 0
        total_skipped = 0
        total_errors = 0
        days_processed = 0

        for date_str in dates:
            try:
                # Fetch reports for this day
                records = fetch_tushare_day(token, date_str, args.rate_limit)

                if not records:
                    days_processed += 1
                    continue

                # Generate embeddings
                if args.no_embed:
                    embeddings = [None] * len(records)
                else:
                    texts = [r.get("content", "") or (r.get("title", "") + "\n" + (r.get("abstr") or "")) for r in records]
                    embeddings = generate_embeddings_batch(texts, args.batch_size)

                # Insert into database
                inserted, skipped = await insert_records_batch(conn, records, embeddings)
                total_new += inserted
                total_skipped += skipped
                days_processed += 1

                # Update progress: save last indexed date after each day
                await update_sync_state(conn, "last_indexed_date", date_str)
                await update_sync_state(conn, "total_records", str(await get_total_records(conn)))

            except Exception as e:
                total_errors += 1
                days_processed += 1
                # Log error to stderr for debugging
                import sys
                print(f"[ERROR] {date_str}: {e}", file=sys.stderr)

        elapsed = time.time() - start_time
        total = await get_total_records(conn)

        return {
            "status": "success",
            "indexed": {
                "new_records": total_new,
                "skipped_duplicates": total_skipped,
                "errors": total_errors,
            },
            "range": {
                "from": start_date,
                "to": end_date,
                "days_processed": days_processed,
            },
            "total_in_index": total,
            "last_indexed_date": end_date,
            "elapsed_seconds": round(elapsed, 1),
        }

    finally:
        await conn.close()


# ── CLI entry point ──────────────────────────────────────────

def main():
    setup_utf8()
    parser = argparse.ArgumentParser(
        description="RealResearch: Tushare research report index builder"
    )
    parser.add_argument(
        "--months", "-m", type=int, default=3,
        help="Number of months to index on first run (default: 3)"
    )
    parser.add_argument(
        "--start-date", type=str, default=None,
        help="Start date YYYYMMDD (overrides --months)"
    )
    parser.add_argument(
        "--end-date", type=str, default=None,
        help="End date YYYYMMDD (default: today)"
    )
    parser.add_argument(
        "--batch-size", "-b", type=int, default=10,
        help="Embedding API batch size (default: 10, max for DashScope)"
    )
    parser.add_argument(
        "--rate-limit", type=int, default=300,
        help="Tushare API rate limit delay in ms (default: 300)"
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Force rebuild: drop and recreate the entire index"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be fetched without actually doing it"
    )
    parser.add_argument(
        "--no-embed", action="store_true",
        help="Index without generating embeddings (for debugging)"
    )
    args = parser.parse_args()

    import asyncio
    result = asyncio.run(run_index(args))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if "error" in result:
        sys.exit(1)
