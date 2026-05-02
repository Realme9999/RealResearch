"""Generate a detailed research material package for report writing.

Aggregates all relevant memories from a bank, structures them into
organized sections (facts, entities, data, timeline, sources), and
optionally runs reflect for synthesis. Output is a material package
that an Agent can use to write a comprehensive report.

Usage:
    rr-detail --query "国产AI算力产业链分析" --bank china-gpu
    rr-detail --query "煤化工设备" --bank coal-chemical-equipment --output ./detail.md
    rr-detail --query "AI芯片" --bank china-gpu --cross-bank
"""

import argparse
import asyncio
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

from .engine import engine_context, default_context, default_bank_id
from .utils import setup_utf8

# Default Reports folder
_script_dir = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_script_dir)
if not os.path.isdir(os.path.join(_PROJECT_ROOT, "Reports")):
    _PROJECT_ROOT = os.path.dirname(_PROJECT_ROOT)
_DEFAULT_REPORTS_DIR = os.path.join(_PROJECT_ROOT, "Reports")


# ── Helpers ──────────────────────────────────────────────────────────

def _extract_numbers(text: str) -> list[dict]:
    """Extract numeric data points from fact text."""
    patterns = [
        # Chinese: 1895亿元, 68.06%, 4000吨/天
        r"([\d,]+\.?\d*)\s*(万亿元|亿元|万元|元|亿美元|美元|万|亿|%|吨|台|套|个|倍|TOPS|TFLOPS|GB|TB|W|Nm³/h|等级)",
        # English: $42B, 352 TFLOPS
        r"\$?([\d,]+\.?\d*)\s*(B|M|K|TFLOPS|TOPS|GB|TB|W|%)",
    ]
    results = []
    for pat in patterns:
        for m in re.finditer(pat, text):
            value = m.group(1).replace(",", "")
            unit = m.group(2)
            # Get surrounding context (the full number expression)
            start = max(0, m.start() - 10)
            end = min(len(text), m.end() + 10)
            context = text[start:end].strip()
            try:
                num = float(value)
                results.append({"value": num, "unit": unit, "context": context})
            except ValueError:
                pass
    return results


def _extract_dates_from_text(text: str) -> list[str]:
    """Extract date references from fact text."""
    patterns = [
        r"(\d{4}年\d{1,2}月\d{1,2}日)",
        r"(\d{4}年\d{1,2}月)",
        r"(\d{4}年)",
        r"(\d{4}-\d{2}-\d{2})",
        r"(\d{4}Q[1-4])",
        r"(\d{4}年上半年|\d{4}年下半年)",
        r"(H[12]\s*\d{4})",
    ]
    dates = []
    for pat in patterns:
        for m in re.finditer(pat, text):
            dates.append(m.group(1))
    return dates


def _group_facts_by_entity(facts: list[dict]) -> dict[str, list[dict]]:
    """Group facts by their linked entities."""
    entity_facts = defaultdict(list)
    for fact in facts:
        entities = fact.get("entities") or []
        if isinstance(entities, list):
            for ent in entities:
                if isinstance(ent, str) and ent:
                    entity_facts[ent].append(fact)
        elif isinstance(entities, dict):
            for ent_name in entities.keys():
                if ent_name:
                    entity_facts[ent_name].append(fact)
    return dict(entity_facts)


def _group_facts_by_context(facts: list[dict]) -> dict[str, list[dict]]:
    """Group facts by their context (spiral/source)."""
    ctx_facts = defaultdict(list)
    for fact in facts:
        ctx = fact.get("context") or "未分类"
        ctx_facts[ctx].append(fact)
    return dict(ctx_facts)


def _extract_sources(facts: list[dict]) -> dict[str, int]:
    """Count facts by source type/context."""
    sources = Counter()
    for fact in facts:
        ctx = fact.get("context") or ""
        if "rr-tushare" in ctx or "研报" in ctx or "tushare" in ctx.lower():
            sources["券商研报"] += 1
        elif "Spiral" in ctx or "spiral" in ctx:
            sources["螺旋研究"] += 1
        elif fact.get("document_id"):
            sources["文档"] += 1
        else:
            sources["网页搜索/其他"] += 1
    return dict(sources)


def _find_numeric_facts(facts: list[dict]) -> list[dict]:
    """Find facts that contain significant numeric data."""
    numeric = []
    for fact in facts:
        text = fact.get("text", "")
        numbers = _extract_numbers(text)
        if numbers:
            numeric.append({
                "text": text,
                "numbers": numbers,
                "entities": fact.get("entities") or [],
                "context": fact.get("context"),
            })
    return numeric


def _build_timeline(facts: list[dict]) -> list[dict]:
    """Build a timeline from facts with date references."""
    timeline = []
    for fact in facts:
        text = fact.get("text", "")

        # Check structured date fields first
        occurred = fact.get("occurred_start") or fact.get("occurred_end")
        if occurred:
            try:
                if isinstance(occurred, str):
                    date_str = occurred[:10]
                else:
                    date_str = str(occurred)[:10]
                timeline.append({
                    "date": date_str,
                    "event": text[:200],
                    "entities": fact.get("entities") or [],
                })
                continue
            except (ValueError, TypeError):
                pass

        # Extract dates from text
        dates = _extract_dates_from_text(text)
        if dates:
            timeline.append({
                "date": dates[0],
                "event": text[:200],
                "entities": fact.get("entities") or [],
            })

    # Sort by date
    timeline.sort(key=lambda x: x["date"])
    return timeline


# ── Core ─────────────────────────────────────────────────────────────

async def _recall_all(
    query: str,
    bank_id: str,
    max_tokens: int = 16384,
    tags: list[str] | None = None,
) -> dict:
    """Full recall from the specified bank."""
    async with engine_context() as engine:
        ctx = default_context()
        kwargs = {}
        if tags:
            kwargs["tags"] = tags

        result = await engine.recall_async(
            bank_id=bank_id,
            query=query,
            budget="high",
            max_tokens=max_tokens,
            include_entities=True,
            include_source_facts=True,
            request_context=ctx,
            **kwargs,
        )

        facts = [f.model_dump() for f in result.results]
        entities = {}
        if result.entities:
            entities = {k: v.model_dump() for k, v in result.entities.items()}
        source_facts = {}
        if result.source_facts:
            source_facts = {k: v.model_dump() for k, v in result.source_facts.items()}

        return {
            "facts": facts,
            "entities": entities,
            "source_facts": source_facts,
        }


async def _cross_bank_search(
    query: str,
    primary_bank_id: str,
    entity_names: list[str],
    max_entities: int = 5,
) -> list[dict]:
    """Search other banks for top entities to find cross-references."""
    from .route import _route_query

    cross_results = []
    # Route the query to find related banks
    route_result = await _route_query(query, top_n=5)
    related_banks = [
        b["bank_id"] for b in route_result.get("recommended_banks", [])
        if b["bank_id"] != primary_bank_id and b.get("combined_score", 0) > 0.3
    ]

    if not related_banks:
        return []

    # Search top entities in related banks
    top_entities = entity_names[:max_entities]
    async with engine_context() as engine:
        ctx = default_context()
        for bank_id in related_banks[:2]:  # Max 2 related banks
            for entity in top_entities[:3]:  # Max 3 entities per bank
                try:
                    result = await engine.recall_async(
                        bank_id=bank_id,
                        query=entity,
                        budget="low",
                        max_tokens=2048,
                        include_entities=False,
                        include_source_facts=False,
                        request_context=ctx,
                    )
                    if result.results:
                        cross_results.append({
                            "source_bank": bank_id,
                            "search_entity": entity,
                            "facts": [f.model_dump() for f in result.results[:5]],
                        })
                except Exception:
                    continue

    return cross_results


async def _reflect_synthesis(
    query: str,
    bank_id: str,
    context: str | None = None,
    max_tokens: int = 8192,
    timeout: int | None = None,
) -> dict | None:
    """Run reflect for high-level synthesis."""
    async with engine_context() as engine:
        ctx = default_context()
        kwargs = {}
        if context:
            kwargs["context"] = context

        try:
            if timeout:
                result = await asyncio.wait_for(
                    engine.reflect_async(
                        bank_id=bank_id,
                        query=query,
                        budget="high",
                        max_tokens=max_tokens,
                        request_context=ctx,
                        **kwargs,
                    ),
                    timeout=timeout,
                )
            else:
                result = await engine.reflect_async(
                    bank_id=bank_id,
                    query=query,
                    budget="high",
                    max_tokens=max_tokens,
                    request_context=ctx,
                    **kwargs,
                )

            return {
                "answer": result.text,
                "usage": result.usage.model_dump() if result.usage else None,
            }
        except asyncio.TimeoutError:
            return {"answer": "[Reflect 超时，跳过综合分析]", "usage": None}
        except Exception as e:
            return {"answer": f"[Reflect 出错: {e}]", "usage": None}


async def _get_bank_memory_count(bank_id: str) -> int:
    """Get total memory count for a bank."""
    try:
        from .engine import resolve_db_url
        import asyncpg

        db_url = resolve_db_url()
        conn = await asyncpg.connect(db_url)
        try:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM memory_units WHERE bank_id = $1",
                bank_id,
            )
            return count or 0
        finally:
            await conn.close()
    except Exception:
        return -1


# ── Material Package Builder ─────────────────────────────────────────

def _build_material_package(
    query: str,
    bank_id: str,
    recall_data: dict,
    reflect_data: dict | None,
    cross_bank_data: list[dict],
) -> dict:
    """Build the structured material package from all gathered data."""
    facts = recall_data.get("facts", [])
    entities = recall_data.get("entities", {})
    source_facts = recall_data.get("source_facts", {})

    # Merge source_facts into facts for complete picture
    all_facts = list(facts)
    seen_ids = {f.get("id") for f in all_facts}
    for sf_id, sf in source_facts.items():
        if sf_id not in seen_ids:
            all_facts.append(sf)

    # Core analysis
    entity_groups = _group_facts_by_entity(all_facts)
    context_groups = _group_facts_by_context(all_facts)
    numeric_facts = _find_numeric_facts(all_facts)
    timeline = _build_timeline(all_facts)
    sources = _extract_sources(all_facts)

    # Sort entities by mention count
    entity_ranking = sorted(
        entity_groups.items(),
        key=lambda x: len(x[1]),
        reverse=True,
    )

    # Build entity profiles (top 20)
    entity_profiles = []
    for ent_name, ent_facts in entity_ranking[:20]:
        profile = {
            "name": ent_name,
            "mention_count": len(ent_facts),
            "facts": [f.get("text", "")[:300] for f in ent_facts[:10]],
        }
        # Extract key data for this entity
        ent_numbers = []
        for f in ent_facts:
            nums = _extract_numbers(f.get("text", ""))
            ent_numbers.extend(nums)
        if ent_numbers:
            profile["key_data"] = [
                f"{n['value']}{n['unit']}" for n in ent_numbers[:5]
            ]
        entity_profiles.append(profile)

    # Build data table
    data_points = []
    for nf in numeric_facts[:50]:
        entry = {
            "text": nf["text"][:200],
            "values": [f"{n['value']}{n['unit']}" for n in nf["numbers"][:3]],
        }
        if nf["entities"]:
            entry["entities"] = nf["entities"][:3]
        data_points.append(entry)

    now = datetime.now(timezone.utc)
    package = {
        "meta": {
            "query": query,
            "bank_id": bank_id,
            "generated_at": now.isoformat(),
            "total_facts": len(all_facts),
            "total_entities": len(entity_groups),
            "total_numeric_facts": len(numeric_facts),
            "timeline_events": len(timeline),
        },
        "reflect_synthesis": reflect_data,
        "core_facts_by_context": {
            ctx: [f.get("text", "")[:300] for f in cfacts[:20]]
            for ctx, cfacts in context_groups.items()
        },
        "entity_profiles": entity_profiles,
        "data_points": data_points,
        "timeline": timeline[:50],
        "source_statistics": sources,
        "cross_bank_references": cross_bank_data,
    }

    return package


# ── Markdown Renderer ────────────────────────────────────────────────

def _render_markdown(package: dict) -> str:
    """Render the material package as readable markdown."""
    meta = package["meta"]
    lines = []

    lines.append(f"# 详细报告素材：{meta['query']}")
    lines.append("")
    lines.append(f"> 生成时间：{meta['generated_at'][:19]}")
    lines.append(f"> Bank：{meta['bank_id']}")
    lines.append(f"> 记忆条数：{meta['total_facts']} 条")
    lines.append(f"> 覆盖实体：{meta['total_entities']} 个")
    lines.append(f"> 含数据的事实：{meta['total_numeric_facts']} 条")
    lines.append(f"> 时间线事件：{meta['timeline_events']} 个")
    lines.append("")

    # Reflect synthesis
    reflect = package.get("reflect_synthesis")
    if reflect and reflect.get("answer"):
        lines.append("---")
        lines.append("")
        lines.append("## 综合分析（Reflect）")
        lines.append("")
        lines.append(reflect["answer"])
        lines.append("")

    # Core facts by context
    ctx_facts = package.get("core_facts_by_context", {})
    if ctx_facts:
        lines.append("---")
        lines.append("")
        lines.append("## 核心事实（按来源分组）")
        lines.append("")
        for ctx, fact_texts in ctx_facts.items():
            lines.append(f"### {ctx}")
            lines.append("")
            for text in fact_texts:
                lines.append(f"- {text}")
            lines.append("")

    # Entity profiles
    profiles = package.get("entity_profiles", [])
    if profiles:
        lines.append("---")
        lines.append("")
        lines.append("## 实体画像")
        lines.append("")
        for prof in profiles:
            lines.append(f"### {prof['name']}（提及 {prof['mention_count']} 次）")
            lines.append("")
            if prof.get("key_data"):
                lines.append(f"**关键数据**: {', '.join(prof['key_data'])}")
                lines.append("")
            for fact_text in prof["facts"][:5]:
                lines.append(f"- {fact_text}")
            lines.append("")

    # Data points
    data_points = package.get("data_points", [])
    if data_points:
        lines.append("---")
        lines.append("")
        lines.append("## 关键数据")
        lines.append("")
        lines.append("| 数据 | 数值 | 相关实体 |")
        lines.append("|------|------|---------|")
        for dp in data_points[:30]:
            text = dp["text"][:80].replace("|", "\\|")
            vals = ", ".join(dp["values"][:3])
            ents = ", ".join((dp.get("entities") or [])[:2])
            lines.append(f"| {text} | {vals} | {ents} |")
        lines.append("")

    # Timeline
    timeline = package.get("timeline", [])
    if timeline:
        lines.append("---")
        lines.append("")
        lines.append("## 时间线")
        lines.append("")
        lines.append("| 时间 | 事件 | 相关实体 |")
        lines.append("|------|------|---------|")
        for t in timeline[:30]:
            event = t["event"][:80].replace("|", "\\|")
            ents_list = t.get("entities") or []
            ents = ", ".join(ents_list[:2])
            lines.append(f"| {t['date']} | {event} | {ents} |")
        lines.append("")

    # Source statistics
    sources = package.get("source_statistics", {})
    if sources:
        lines.append("---")
        lines.append("")
        lines.append("## 数据来源统计")
        lines.append("")
        lines.append("| 来源类型 | 条数 | 占比 |")
        lines.append("|---------|------|------|")
        total = sum(sources.values()) or 1
        for src, count in sorted(sources.items(), key=lambda x: x[1], reverse=True):
            pct = f"{count / total * 100:.1f}%"
            lines.append(f"| {src} | {count} | {pct} |")
        lines.append("")

    # Cross-bank references
    cross = package.get("cross_bank_references", [])
    if cross:
        lines.append("---")
        lines.append("")
        lines.append("## 跨 Bank 关联数据")
        lines.append("")
        for ref in cross:
            lines.append(f"### 来源：{ref['source_bank']}（搜索实体：{ref['search_entity']}）")
            lines.append("")
            for fact in ref.get("facts", []):
                lines.append(f"- {fact.get('text', '')[:200]}")
            lines.append("")

    return "\n".join(lines)


# ── Main ─────────────────────────────────────────────────────────────

async def _generate_detail(
    query: str,
    bank_id: str,
    cross_bank: bool = False,
    include_reflect: bool = True,
    max_tokens: int = 32768,
    reflect_timeout: int | None = None,
    output_file: str | None = None,
    no_save: bool = False,
):
    """Generate the detailed material package."""
    from .logger import get_logger

    logger = get_logger(default_query=query, bank_id=bank_id)
    if logger:
        logger.start_step("rr-detail", {
            "query": query,
            "bank_id": bank_id,
            "cross_bank": cross_bank,
            "include_reflect": include_reflect,
        })

    # Step 1: Full recall
    recall_data = await _recall_all(
        query=query,
        bank_id=bank_id,
        max_tokens=max_tokens,
    )
    fact_count = len(recall_data.get("facts", []))
    entity_count = len(recall_data.get("entities", {}))

    # Step 2: Cross-bank search (optional)
    cross_bank_data = []
    if cross_bank and entity_count > 0:
        entity_names = list(recall_data.get("entities", {}).keys())
        cross_bank_data = await _cross_bank_search(
            query=query,
            primary_bank_id=bank_id,
            entity_names=entity_names,
        )

    # Step 3: Reflect synthesis (optional)
    reflect_data = None
    if include_reflect:
        reflect_data = await _reflect_synthesis(
            query=query,
            bank_id=bank_id,
            timeout=reflect_timeout,
        )

    # Step 4: Build material package
    package = _build_material_package(
        query=query,
        bank_id=bank_id,
        recall_data=recall_data,
        reflect_data=reflect_data,
        cross_bank_data=cross_bank_data,
    )

    # Step 5: Render markdown
    markdown = _render_markdown(package)

    # Step 6: Save
    if not no_save:
        out_dir = _DEFAULT_REPORTS_DIR
        os.makedirs(out_dir, exist_ok=True)

        if output_file:
            json_path = output_file
            if json_path.endswith(".md"):
                json_path = json_path[:-3] + ".json"
            md_path = output_file if output_file.endswith(".md") else output_file + ".md"
        else:
            date_str = datetime.now().strftime("%Y-%m-%d")
            query_summary = "".join(
                c for c in query[:20] if c.isalnum() or c in " _-"
            ).strip().replace(" ", "_")
            if not query_summary:
                query_summary = "detail"
            json_path = os.path.join(out_dir, f"{date_str}_{query_summary}_detail.json")
            md_path = os.path.join(out_dir, f"{date_str}_{query_summary}_detail.md")

        # Ensure directories exist
        os.makedirs(os.path.dirname(json_path) or ".", exist_ok=True)
        os.makedirs(os.path.dirname(md_path) or ".", exist_ok=True)

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(package, f, ensure_ascii=False, indent=2, default=str)

        with open(md_path, "w", encoding="utf-8") as f:
            f.write(markdown)

        result = {
            "saved": True,
            "json_file": os.path.abspath(json_path),
            "markdown_file": os.path.abspath(md_path),
            "meta": package["meta"],
        }
    else:
        result = {
            "saved": False,
            "meta": package["meta"],
            "markdown_preview": markdown[:2000] + "..." if len(markdown) > 2000 else markdown,
        }

    if logger:
        logger.end_step(
            result_summary={
                "total_facts": package["meta"]["total_facts"],
                "total_entities": package["meta"]["total_entities"],
                "has_reflect": reflect_data is not None,
                "has_cross_bank": bool(cross_bank_data),
                "saved": result.get("saved", False),
            },
        )

    return result


def main():
    setup_utf8()
    parser = argparse.ArgumentParser(
        description="RealResearch: generate detailed report material package"
    )
    parser.add_argument("--query", "-q", required=True, help="Research question")
    parser.add_argument("--bank", "-b", default=None, help="Bank ID")
    parser.add_argument("--cross-bank", action="store_true", help="Search related banks for cross-references")
    parser.add_argument("--no-reflect", action="store_true", help="Skip reflect synthesis")
    parser.add_argument("--max-tokens", type=int, default=32768, help="Max tokens for recall")
    parser.add_argument("--reflect-timeout", type=int, default=None, help="Reflect timeout in seconds")
    parser.add_argument("--output", "-o", default=None, help="Output file path (default: Reports/)")
    parser.add_argument("--no-save", action="store_true", help="Print to stdout only")
    args = parser.parse_args()

    bank_id = args.bank or default_bank_id()

    result = asyncio.run(_generate_detail(
        query=args.query,
        bank_id=bank_id,
        cross_bank=args.cross_bank,
        include_reflect=not args.no_reflect,
        max_tokens=args.max_tokens,
        reflect_timeout=args.reflect_timeout,
        output_file=args.output,
        no_save=args.no_save,
    ))

    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
