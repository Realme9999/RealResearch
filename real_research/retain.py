"""Store research findings into Hindsight memory engine.

Usage:
    rr-retain --content "研究发现..." --bank my-bank
    rr-retain --content "..." --tags "quantum,2026" --context "Spiral 1"
    echo "content" | rr-retain --bank my-bank
"""

import argparse
import asyncio
import json
import sys

from .engine import engine_context, default_context, default_bank_id
from .utils import setup_utf8


async def _retain(
    content: str,
    bank_id: str,
    context: str = "",
    tags: list[str] | None = None,
):
    async with engine_context() as engine:
        ctx = default_context()
        unit_ids = await engine.retain_async(
            bank_id=bank_id,
            content=content,
            context=context,
            request_context=ctx,
        )

        result = {
            "stored": True,
            "bank_id": bank_id,
            "unit_ids": unit_ids,
            "unit_count": len(unit_ids),
        }
        return result


def main():
    setup_utf8()
    parser = argparse.ArgumentParser(description="RealResearch: store findings to memory")
    parser.add_argument("--content", "-c", default=None, help="Content to store")
    parser.add_argument("--bank", "-b", default=None, help="Bank ID")
    parser.add_argument("--context", default="", help="Context for the retention")
    parser.add_argument("--tags", default=None, help="Comma-separated tags")
    parser.add_argument("--file", "-f", default=None, help="Read content from file")
    args = parser.parse_args()

    content = args.content
    if not content and args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            content = f.read()
    if not content and not sys.stdin.isatty():
        content = sys.stdin.read()

    if not content:
        print(json.dumps({"error": "No content provided. Use --content, --file, or pipe stdin."}))
        sys.exit(1)

    bank_id = args.bank or default_bank_id()
    tags = [t.strip() for t in args.tags.split(",")] if args.tags else None

    from .logger import get_logger
    logger = get_logger(default_query=args.context or content[:80], bank_id=bank_id)
    if logger:
        logger.start_step("rr-retain", {"bank_id": bank_id, "context": args.context, "tags": tags, "content_length": len(content or "")})

    result = asyncio.run(_retain(
        content=content.strip(),
        bank_id=bank_id,
        context=args.context,
        tags=tags,
    ))

    if logger:
        summary = None
        if "error" not in result:
            summary = {
                "stored": result.get("stored", False),
                "bank_id": result.get("bank_id", ""),
                "unit_count": result.get("unit_count", 0),
            }
        logger.end_step(result_summary=summary, error=result.get("error"))

    print(json.dumps(result, ensure_ascii=False, indent=2))
