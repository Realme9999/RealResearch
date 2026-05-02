"""Generate and save a structured research report.

Usage:
    rr-report --query "原始问题" --content "## 报告内容..."
    rr-report --query "原始问题" --file /tmp/report.md
    cat report.md | rr-report --query "原始问题"
"""

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone

from .utils import setup_utf8

# Default Reports folder (relative to project root)
_script_dir = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_script_dir)
if not os.path.isdir(os.path.join(_PROJECT_ROOT, "Reports")):
    _PROJECT_ROOT = os.path.dirname(_PROJECT_ROOT)
_DEFAULT_REPORTS_DIR = os.path.join(_PROJECT_ROOT, "Reports")


def _extract_keywords(text: str, max_words: int = 6) -> str:
    cleaned = re.sub(r"[^\w\s一-鿿]", " ", text)
    words = cleaned.split()
    keywords = [w for w in words if len(w) > 1][:max_words]
    return "-".join(keywords) if keywords else "report"


def save_report(
    query: str,
    content: str,
    reports_dir: str | None = None,
    bank_id: str | None = None,
) -> dict:
    """Save report to a markdown file with YAML frontmatter."""
    out_dir = reports_dir or _DEFAULT_REPORTS_DIR
    os.makedirs(out_dir, exist_ok=True)

    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    keywords = _extract_keywords(query)
    filename = f"{date_str}_{keywords}.md"
    filepath = os.path.join(out_dir, filename)

    fm_lines = [
        "---",
        f"generated_at: {now.isoformat()}",
        f"original_query: {query!r}",
        "tool: real-research",
    ]
    if bank_id:
        fm_lines.append(f"bank_id: {bank_id!r}")
    fm_lines.extend(["---", ""])

    with open(filepath, "w", encoding="utf-8", newline="") as f:
        f.write("\n".join(fm_lines) + "\n")
        f.write(content)

    return {
        "saved": True,
        "filepath": os.path.abspath(filepath),
        "filename": filename,
    }


def main():
    setup_utf8()
    parser = argparse.ArgumentParser(description="RealResearch: save report")
    parser.add_argument("--query", "-q", required=True, help="Original research question")
    parser.add_argument("--content", "-c", default=None, help="Report content (markdown)")
    parser.add_argument("--file", "-f", default=None, help="Read content from file")
    parser.add_argument("--output-dir", "-o", default=None, help="Output directory (default: reports/)")
    parser.add_argument("--bank", "-b", default=None, help="Associate report with a memory bank")
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

    from .logger import get_logger
    logger = get_logger(default_query=args.query, bank_id=args.bank)
    if logger:
        logger.start_step("rr-report", {"query": args.query, "bank_id": args.bank, "content_length": len(content or "")})

    result = save_report(args.query, content.strip(), args.output_dir, bank_id=args.bank)

    if logger:
        logger.end_step(
            result_summary={"saved": result.get("saved", False), "filepath": result.get("filepath", ""), "filename": result.get("filename", "")},
            error=result.get("error"),
        )
        if result.get("saved"):
            from .logger import close_session
            close_session(report_path=result.get("filepath"))

    print(json.dumps(result, ensure_ascii=False, indent=2))
