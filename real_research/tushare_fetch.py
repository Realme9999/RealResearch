"""Download and convert Tushare research report PDFs to Markdown.

Usage:
    rr-tushare-fetch --url "https://pdf.dfcfw.com/..."
    rr-tushare-fetch --id 5622
    rr-tushare-fetch --url "https://..." --save ./report.md
    rr-tushare-fetch --url "https://..." --max-length 10000
    rr-tushare-fetch --url "https://..." --topic "国产AI算力产业链" --save ./report.md
"""

import argparse
import json
import os
import sys

from .utils import setup_utf8, load_dotenv

# Load .env on import
load_dotenv()

# ── Constants ────────────────────────────────────────────────

TEXTIN_API_URL = "https://api.textin.com/ai/service/v1/pdf_to_markdown"
REPORTS_TABLE = "tushare.reports"


# ── LLM Distillation ────────────────────────────────────────

DISTILL_SYSTEM_PROMPT = """你是一个金融研报分析师。你的任务是根据给定的研究主题，从研报全文中提取结构化洞察。

提取分为两部分：必选维度和自由维度。

## 必选维度（每篇研报必须提取）

1. **核心观点**：提取所有与研究主题相关的重要观点，不要遗漏，长研报可能有10条以上
2. **关键数据**：具体数字、百分比、市场规模、增长率、财务指标等，必须包含具体数字，不要笼统描述
3. **投资建议**：机构评级、目标价、推荐方向、估值逻辑
4. **风险提示**：风险因素、不确定性、潜在利空

## 自由维度（根据研报内容自行判断）

根据研报实际内容，自行决定需要提取哪些维度。常见的有但不限于：
- 产业链分析（上下游、供应链、国产化替代）
- 竞争格局（市场份额、主要玩家、竞争壁垒）
- 技术/产品进展（新产品、技术突破、产能变化）
- 政策/监管因素（政策支持、监管变化）
- 订单/合同（新签合同、在手订单、订单趋势）
- 产能利用率（开工率、产能释放节奏）
- 客户/市场拓展（新客户、出口、市场开拓）
- 行业景气度/周期（所处周期阶段、景气趋势）
- 财务健康度（现金流、负债、资产质量）
- 管理层/治理（管理层变动、股权结构、激励机制）
- 同业对比（与同行公司的比较分析）
- 催化剂/事件驱动（未来可能的股价催化剂）

原则：研报里有什么重要内容就提取什么，不要被上面的列表限制。如果发现了列表之外的重要维度，也要提取。

## 输出格式

来源：[机构名]《[报告标题]》[日期]
机构评级：[买入/增持/中性/减持/卖出]

核心观点：
1. [观点1]
2. [观点2]
...

关键数据：
- [数据1]
- [数据2]
...

[自由维度1]：
- [内容1]
- [内容2]
...

[自由维度2]：
- [内容1]
- [内容2]
...

（自由维度的数量和名称根据研报内容决定，有多少写多少）

投资建议：[详细描述，包含目标价、估值逻辑等]
风险提示：[详细描述]

## 要求
- 优先提取与研究主题相关的内容，但不要遗漏研报中的重要信息
- 数据必须包含具体数字，不要笼统描述
- 自由维度的名称要简洁明了，能准确概括内容
- 如果研报与研究主题关联度很低，只输出"关联度低"和一句话说明即可"""


def distill_with_llm(markdown: str, topic: str, title: str = "", org: str = "", trade_date: str = "") -> str:
    """Call LLM to extract structured insights from report markdown.

    Args:
        markdown: Full report markdown text
        topic: Current research topic for targeted extraction
        title: Report title (for context)
        org: Report org (for context)
        trade_date: Report date (for context)

    Returns:
        Structured insight text, or error string starting with "Error:"
    """
    import openai

    api_key = os.environ.get("RR_LLM_API_KEY")
    base_url = os.environ.get("RR_LLM_BASE_URL", "").rstrip("/")
    model = os.environ.get("RR_LLM_MODEL", "mimo-v2.5-pro")

    if not api_key:
        return "Error: RR_LLM_API_KEY not set"

    client = openai.OpenAI(api_key=api_key, base_url=base_url if base_url else None)

    # Build context header
    context_parts = []
    if org:
        context_parts.append(f"机构：{org}")
    if title:
        context_parts.append(f"标题：{title}")
    if trade_date:
        context_parts.append(f"日期：{trade_date}")
    context_header = "\n".join(context_parts) if context_parts else ""

    user_content = f"研究主题：{topic}\n\n"
    if context_header:
        user_content += f"{context_header}\n\n"
    user_content += f"研报全文：\n{markdown}"

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": DISTILL_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            max_tokens=4096,
        )
        return resp.choices[0].message.content
    except Exception as e:
        return f"Error: LLM distillation failed: {e}"


# ── Core functions ───────────────────────────────────────────

def download_pdf(url: str) -> bytes:
    """Download PDF from URL. Returns raw bytes."""
    import requests

    resp = requests.get(url, timeout=30, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    })
    resp.raise_for_status()
    return resp.content


def pdf_to_markdown(pdf_bytes: bytes) -> dict:
    """Convert PDF bytes to Markdown using TextIn API.

    Returns:
        {"markdown": str, "pages": int, "file_type": str} on success
        {"error": str} on failure
    """
    import requests

    app_id = os.environ.get("RR_TEXTIN_APP_ID")
    secret_code = os.environ.get("RR_TEXTIN_SECRET_CODE")
    if not app_id or not secret_code:
        return {"error": "RR_TEXTIN_APP_ID or RR_TEXTIN_SECRET_CODE not set in .env"}

    headers = {
        "x-ti-app-id": app_id,
        "x-ti-secret-code": secret_code,
        "Content-Type": "application/octet-stream",
    }

    resp = requests.post(TEXTIN_API_URL, headers=headers, data=pdf_bytes, timeout=120)
    resp.raise_for_status()

    result = resp.json()
    if result.get("code") != 200:
        return {"error": f"TextIn API error: {result.get('msg', 'unknown')}"}

    inner = result.get("result", {})
    return {
        "markdown": inner.get("markdown", ""),
        "pages": inner.get("total_page_number", 0),
        "file_type": result.get("file_type", "PDF"),
    }


def fetch_by_url(url: str, max_length: int = 50000, topic: str | None = None,
                 title: str = "", org: str = "", trade_date: str = "",
                 save_path: str | None = None) -> dict:
    """Download PDF and convert to Markdown.

    Args:
        url: PDF download URL
        max_length: Max markdown characters (only used when topic is None)
        topic: If provided, LLM distills insights instead of returning full markdown
        title: Report title (for distillation context)
        org: Report org (for distillation context)
        trade_date: Report date (for distillation context)
        save_path: If provided, save full markdown to this file before distillation

    Returns:
        On success (without topic):
            {"url", "markdown", "markdown_length", "truncated", "pages", "source"}
        On success (with topic):
            {"url", "insights", "full_length", "pages", "source", "saved_to"}
        On failure:
            {"error", "url"}
    """
    try:
        pdf_bytes = download_pdf(url)
    except Exception as e:
        return {"error": f"Failed to download PDF: {e}", "url": url}

    if len(pdf_bytes) == 0:
        return {"error": "Downloaded PDF is empty", "url": url}

    conversion = pdf_to_markdown(pdf_bytes)
    if "error" in conversion:
        return {"error": conversion["error"], "url": url}

    markdown = conversion["markdown"]
    full_length = len(markdown)

    # Save full markdown to file if requested
    if save_path:
        os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
        with open(save_path, "w", encoding="utf-8") as f:
            f.write(markdown)

    if topic:
        # LLM distillation mode: return structured insights, not full text
        insights = distill_with_llm(markdown, topic, title, org, trade_date)
        result = {
            "url": url,
            "insights": insights,
            "full_length": full_length,
            "pages": conversion.get("pages", 0),
            "source": "textin",
        }
        if save_path:
            result["saved_to"] = save_path
        return result
    else:
        # Legacy mode: return (truncated) full markdown
        truncated = full_length > max_length
        if truncated:
            markdown = markdown[:max_length] + "\n\n... [content truncated]"

        result = {
            "url": url,
            "markdown": markdown,
            "markdown_length": len(markdown),
            "truncated": truncated,
            "pages": conversion.get("pages", 0),
            "source": "textin",
        }
        if save_path:
            result["saved_to"] = save_path
        return result


async def fetch_by_id(record_id: int, max_length: int = 50000, no_content: bool = False,
                      topic: str | None = None, save_path: str | None = None) -> dict:
    """Fetch report by database record ID.

    Looks up the record in tushare.reports, gets the pdf_url,
    then downloads and converts the PDF.
    """
    import asyncpg
    from .engine import resolve_db_url

    db_url = resolve_db_url()
    conn = await asyncpg.connect(db_url)
    try:
        row = await conn.fetchrow(
            f"""SELECT id, title, ts_code, trade_date, org, ind_name, report_type, pdf_url
                FROM {REPORTS_TABLE} WHERE id = $1""",
            record_id,
        )
        if not row:
            return {"error": f"Record {record_id} not found in index"}

        pdf_url = row["pdf_url"]
        if not pdf_url:
            return {"error": f"Record {record_id} has no PDF URL"}

        trade_date = row["trade_date"]
        date_str = trade_date.strftime("%Y%m%d") if trade_date else None

        result = {
            "id": row["id"],
            "title": row["title"],
            "url": pdf_url,
            "ts_code": row["ts_code"],
            "trade_date": date_str,
            "org": row["org"],
            "ind_name": row["ind_name"],
            "report_type": row["report_type"],
        }

        if no_content:
            result["markdown"] = None
            result["markdown_length"] = 0
            result["truncated"] = False
            result["source"] = "textin"
            return result

        # Download and convert (with optional distillation)
        fetch_result = fetch_by_url(
            pdf_url, max_length, topic=topic,
            title=row["title"] or "", org=row["org"] or "",
            trade_date=date_str or "", save_path=save_path,
        )
        if "error" in fetch_result:
            return {**result, "error": fetch_result["error"]}

        return {**result, **fetch_result}

    finally:
        await conn.close()


# ── CLI entry point ──────────────────────────────────────────

def main():
    setup_utf8()
    parser = argparse.ArgumentParser(
        description="RealResearch: fetch and convert Tushare research report PDFs"
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--url", "-u", type=str,
        help="PDF download URL"
    )
    group.add_argument(
        "--id", type=int,
        help="Database record ID (from rr-tushare-search results)"
    )

    parser.add_argument(
        "--max-length", "-m", type=int, default=50000,
        help="Max markdown characters to return (default: 50000, ignored when --topic is set)"
    )
    parser.add_argument(
        "--save", type=str, default=None,
        help="Save full markdown to file path"
    )
    parser.add_argument(
        "--no-content", action="store_true",
        help="Return metadata only, skip PDF download"
    )
    parser.add_argument(
        "--topic", "-t", type=str, default=None,
        help="Research topic for LLM distillation. When set, returns structured insights instead of full markdown"
    )
    args = parser.parse_args()

    from .logger import get_logger
    logger = get_logger(default_query=args.topic or args.url or args.id)
    if logger:
        logger.start_step("rr-tushare-fetch", {
            "url": args.url, "id": args.id, "max_length": args.max_length,
            "topic": args.topic, "save": args.save, "no_content": args.no_content,
        })

    if args.url:
        result = fetch_by_url(args.url, args.max_length, topic=args.topic, save_path=args.save)
    else:
        import asyncio
        result = asyncio.run(fetch_by_id(args.id, args.max_length, args.no_content, topic=args.topic, save_path=args.save))

    if logger:
        summary = None
        if "error" not in result:
            summary = {
                "url": result.get("url", ""),
                "pages": result.get("pages", 0),
                "source": result.get("source", ""),
                "saved_to": result.get("saved_to"),
                "has_insights": bool(result.get("insights")),
                "markdown_length": result.get("markdown_length", result.get("full_length", 0)),
            }
        logger.end_step(result_summary=summary, error=result.get("error"))

    print(json.dumps(result, ensure_ascii=False, indent=2))
    if "error" in result:
        sys.exit(1)
