"""Recall memories from Hindsight memory engine.

Usage:
    rr-recall --query "用户偏好" --bank my-bank --budget high
    rr-recall --query "加密货币" --tags "crypto,defi" --max-tokens 8192
"""

import argparse
import asyncio
import json
import sys

from .engine import engine_context, default_context, default_bank_id
from .utils import setup_utf8


async def _recall(
    query: str,
    bank_id: str,
    budget: str = "mid",
    max_tokens: int = 16384,
    tags: list[str] | None = None,
    include_entities: bool = True,
    include_source_facts: bool = True,
):
    async with engine_context() as engine:
        ctx = default_context()

        kwargs = {}
        if tags:
            kwargs["tags"] = tags

        result = await engine.recall_async(
            bank_id=bank_id,
            query=query,
            budget=budget,
            max_tokens=max_tokens,
            include_entities=include_entities,
            include_source_facts=include_source_facts,
            request_context=ctx,
            **kwargs,
        )

        output = {
            "query": query,
            "bank_id": bank_id,
            "budget": budget,
            "results": [f.model_dump() for f in result.results],
        }
        if result.entities:
            output["entities"] = {k: v.model_dump() for k, v in result.entities.items()}
        if result.source_facts:
            output["source_facts"] = {k: v.model_dump() for k, v in result.source_facts.items()}

        return output


def main():
    setup_utf8()
    parser = argparse.ArgumentParser(description="RealResearch: recall memories")
    parser.add_argument("--query", "-q", required=True, help="Recall query")
    parser.add_argument("--bank", "-b", default=None, help="Bank ID")
    parser.add_argument("--budget", default="mid", choices=["low", "mid", "high"])
    parser.add_argument("--max-tokens", type=int, default=16384)
    parser.add_argument("--tags", default=None, help="Comma-separated tags to filter")
    parser.add_argument("--no-entities", action="store_true")
    parser.add_argument("--no-source-facts", action="store_true")
    args = parser.parse_args()

    bank_id = args.bank or default_bank_id()
    tags = [t.strip() for t in args.tags.split(",")] if args.tags else None

    from .logger import get_logger
    logger = get_logger()
    if logger:
        logger.start_step("rr-recall", {"query": args.query, "bank_id": bank_id, "budget": args.budget, "tags": tags})

    result = asyncio.run(_recall(
        query=args.query,
        bank_id=bank_id,
        budget=args.budget,
        max_tokens=args.max_tokens,
        tags=tags,
        include_entities=not args.no_entities,
        include_source_facts=not args.no_source_facts,
    ))

    if logger:
        summary = None
        if "error" not in result:
            results = result.get("results", [])
            summary = {
                "total_results": len(results),
                "bank_id": result.get("bank_id", ""),
                "has_entities": bool(result.get("entities")),
                "has_source_facts": bool(result.get("source_facts")),
            }
        logger.end_step(result_summary=summary, error=result.get("error"))

    print(json.dumps(result, ensure_ascii=False, indent=2))
