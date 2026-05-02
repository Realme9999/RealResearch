"""Reflect (reason) over accumulated memories using Hindsight's agentic loop.

Usage:
    rr-reflect --query "综合分析市场趋势" --bank my-bank --budget high
    rr-reflect --query "..." --bank my-bank --output-file ./reflect.json
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime

from .engine import engine_context, default_context, default_bank_id
from .utils import setup_utf8

# Default Reports folder (relative to project root)
_script_dir = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_script_dir)
if not os.path.isdir(os.path.join(_PROJECT_ROOT, "Reports")):
    _PROJECT_ROOT = os.path.dirname(_PROJECT_ROOT)
_DEFAULT_REPORTS_DIR = os.path.join(_PROJECT_ROOT, "Reports")


def _generate_report_path(query: str, reports_dir: str = None) -> str:
    """Generate a report path with date stamp based on query."""
    if reports_dir is None:
        reports_dir = _DEFAULT_REPORTS_DIR

    # Create Reports folder if not exists
    os.makedirs(reports_dir, exist_ok=True)

    # Generate filename: YYYY-MM-DD_query_summary.json
    date_str = datetime.now().strftime("%Y-%m-%d")
    # Extract first 20 chars of query for filename, remove special chars
    query_summary = "".join(c for c in query[:20] if c.isalnum() or c in " _-").strip()
    query_summary = query_summary.replace(" ", "_")
    if not query_summary:
        query_summary = "report"

    filename = f"{date_str}_{query_summary}.json"
    return os.path.join(reports_dir, filename)


async def _reflect(
    query: str,
    bank_id: str,
    budget: str = "high",
    max_tokens: int = 32768,
    context: str | None = None,
    tags: list[str] | None = None,
    wall_timeout: int | None = None,
):
    async with engine_context() as engine:
        ctx = default_context()

        kwargs = {}
        if tags:
            kwargs["tags"] = tags
        if context:
            kwargs["context"] = context

        result = await engine.reflect_async(
            bank_id=bank_id,
            query=query,
            budget=budget,
            max_tokens=max_tokens,
            request_context=ctx,
            **kwargs,
        )

        based_on_raw = result.based_on or []
        based_on_serialized = []
        for item in based_on_raw:
            if hasattr(item, "model_dump"):
                based_on_serialized.append(item.model_dump())
            elif hasattr(item, "__dict__"):
                based_on_serialized.append(str(item))
            else:
                based_on_serialized.append(item)

        output = {
            "query": query,
            "bank_id": bank_id,
            "answer": result.text,
            "based_on": based_on_serialized,
        }
        if result.structured_output:
            output["structured_output"] = result.structured_output
        if result.usage:
            output["usage"] = result.usage.model_dump()

        return output


def main():
    setup_utf8()
    parser = argparse.ArgumentParser(description="RealResearch: reason over memories")
    parser.add_argument("--query", "-q", required=True, help="Question to reflect on")
    parser.add_argument("--bank", "-b", default=None, help="Bank ID")
    parser.add_argument("--budget", default="high", choices=["low", "mid", "high"])
    parser.add_argument("--max-tokens", type=int, default=8192)
    parser.add_argument("--context", default=None, help="Additional context")
    parser.add_argument("--tags", default=None, help="Comma-separated tags")
    parser.add_argument("--output-file", "-o", default=None, help="Write full JSON to file (default: Reports/YYYY-MM-DD_query.json)")
    parser.add_argument("--reports-dir", default=None, help="Reports folder path (default: ./Reports)")
    parser.add_argument("--timeout", "-t", type=int, default=None, help="Wall-clock timeout in seconds")
    parser.add_argument("--no-save", action="store_true", help="Don't save to file, print to stdout only")
    args = parser.parse_args()

    bank_id = args.bank or default_bank_id()
    tags = [t.strip() for t in args.tags.split(",")] if args.tags else None

    # Generate default output path if not specified and not --no-save
    output_file = args.output_file
    if output_file is None and not args.no_save:
        output_file = _generate_report_path(args.query, args.reports_dir)

    from .logger import get_logger
    logger = get_logger(default_query=args.query, bank_id=bank_id)
    if logger:
        logger.start_step("rr-reflect", {"query": args.query, "bank_id": bank_id, "budget": args.budget, "tags": tags, "timeout": args.timeout})

    reflect_coro = _reflect(
        query=args.query,
        bank_id=bank_id,
        budget=args.budget,
        max_tokens=args.max_tokens,
        context=args.context,
        tags=tags,
        wall_timeout=args.timeout,
    )

    if args.timeout:
        result = asyncio.run(asyncio.wait_for(reflect_coro, timeout=args.timeout))
    else:
        result = asyncio.run(reflect_coro)

    if logger:
        answer_text = result.get("answer", "")
        token_usage = result.get("usage", {})
        logger.end_step(
            result_summary={
                "answer_length": len(answer_text),
                "answer_preview": answer_text[:200],
                "usage": token_usage,
            },
            token_usage=token_usage if token_usage else None,
            error=result.get("error"),
        )

    if output_file:
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)

            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)

            md_path = os.path.splitext(output_file)[0] + ".md"
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(result.get("answer", ""))

            answer_text = result.get("answer", "")
            preview = answer_text[:200] + "..." if len(answer_text) > 200 else answer_text
            summary = {
                "saved": True,
                "filepath": os.path.abspath(output_file),
                "markdown_file": os.path.abspath(md_path),
                "answer_preview": preview,
                "usage": result.get("usage", {}),
            }
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        except Exception as e:
            print(json.dumps({"saved": False, "error": str(e)}, ensure_ascii=False, indent=2))
            sys.exit(1)
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
