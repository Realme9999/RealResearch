"""Manage memory banks — research direction isolation.

Bank metadata (name, description, tags, mission) is stored in Hindsight's
native bank_config JSONB column. No Bank model modification needed.

Usage:
    rr-bank create --id crypto-dex --name "DEX研究" --tags "DeFi,DEX"
    rr-bank list
    rr-bank describe crypto-dex
    rr-bank tag crypto-dex --add "RWA" --remove "NFT"
    rr-bank delete crypto-dex
    rr-bank auto-profile crypto-dex
"""

import argparse
import asyncio
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

from .engine import engine_context, default_context, default_bank_id, resolve_db_url
from .config import load_config
from .utils import setup_utf8

# Import fq_table from hindsight (read-only, not modifying original code)
try:
    from hindsight_api.engine.retain.bank_utils import fq_table as _fq_table
    _HAS_FQ_TABLE = True
except ImportError:
    _HAS_FQ_TABLE = False
    def _fq_table(table: str) -> str:
        return table


def _parse_mission(mission: str) -> tuple[str, list[str]]:
    """Parse mission text back into description and tags.

    Expected format:
        description text

        Tags: tag1, tag2, tag3
    """
    if not mission:
        return "", []
    parts = mission.rsplit("\n\nTags:", 1)
    if len(parts) == 2:
        desc = parts[0].strip()
        tags = [t.strip() for t in parts[1].split(",") if t.strip()]
        return desc, tags
    return mission.strip(), []


async def _create_bank(
    bank_id: str,
    name: str | None = None,
    description: str | None = None,
    tags: list[str] | None = None,
    mission: str | None = None,
):
    """Create or update a bank.

    Hindsight engine only supports name + mission on banks.
    - If mission is provided directly, use it as-is (for LLM system prompt).
    - If description+tags are provided, encode them into mission for routing.
    """
    async with engine_context() as engine:
        ctx = default_context()
        profile = await engine.get_bank_profile(bank_id, request_context=ctx)

        update_kwargs = {}
        if name is not None:
            update_kwargs["name"] = name

        if mission is not None:
            # Direct mission text — use as-is
            update_kwargs["mission"] = mission
        elif description is not None or tags is not None:
            # Build mission from description + tags (legacy mode)
            desc_part = description if description is not None else ""
            tags_part = ", ".join(tags) if tags is not None else ""
            mission_lines = []
            if desc_part:
                mission_lines.append(desc_part)
            if tags_part:
                mission_lines.append(f"Tags: {tags_part}")
            update_kwargs["mission"] = "\n\n".join(mission_lines)

        if update_kwargs:
            await engine.update_bank(bank_id, request_context=ctx, **update_kwargs)
            profile = await engine.get_bank_profile(bank_id, request_context=ctx)

        # Parse mission back into description + tags for return
        mission = profile.get("mission", "") or ""
        parsed_desc, parsed_tags = _parse_mission(mission)

        return {
            "created": True,
            "bank_id": bank_id,
            "name": profile.get("name", bank_id),
            "description": parsed_desc,
            "tags": parsed_tags,
            "mission": mission,
        }


async def _list_banks():
    async with engine_context() as engine:
        ctx = default_context()
        banks = await engine.list_banks(request_context=ctx)

        # Enrich with memory counts
        counts = {}
        try:
            import asyncpg
            db_url = resolve_db_url()
            conn = await asyncpg.connect(db_url)
            try:
                rows = await conn.fetch(
                    f"SELECT bank_id, COUNT(*) as cnt FROM {_fq_table('memory_units')} GROUP BY bank_id"
                )
                for r in rows:
                    counts[r["bank_id"]] = r["cnt"]
            finally:
                await conn.close()
        except Exception:
            pass

        result = []
        for b in banks:
            bid = b.get("bank_id", "")
            mission = b.get("mission", "") or ""
            desc, tags = _parse_mission(mission)
            result.append({
                "bank_id": bid,
                "name": b.get("name") or bid,
                "tags": tags,
                "description": desc,
                "mission": mission,
                "memory_count": counts.get(bid, 0),
                "updated_at": b.get("updated_at"),
            })

        return {"banks": result, "total": len(result)}


async def _describe_bank(bank_id: str):
    async with engine_context() as engine:
        ctx = default_context()
        profile = await engine.get_bank_profile(bank_id, request_context=ctx)

        memory_count = 0
        try:
            import asyncpg
            db_url = resolve_db_url()
            conn = await asyncpg.connect(db_url)
            try:
                memory_count = await conn.fetchval(
                    f"SELECT COUNT(*) FROM {_fq_table('memory_units')} WHERE bank_id = $1",
                    bank_id,
                ) or 0
            finally:
                await conn.close()
        except Exception:
            pass

        mission = profile.get("mission", "") or ""
        desc, tags = _parse_mission(mission)

        return {
            "bank_id": bank_id,
            "name": profile.get("name", bank_id),
            "description": desc,
            "tags": tags,
            "mission": mission,
            "disposition": profile.get("disposition", {}),
            "memory_count": memory_count,
        }


async def _tag_bank(bank_id: str, add: list[str] | None, remove: list[str] | None, set_tags: list[str] | None):
    async with engine_context() as engine:
        ctx = default_context()
        profile = await engine.get_bank_profile(bank_id, request_context=ctx)
        mission = profile.get("mission", "") or ""
        desc, current = _parse_mission(mission)

        if set_tags is not None:
            new_tags = set_tags
        else:
            new_tags = list(current)
            if add:
                for t in add:
                    if t not in new_tags:
                        new_tags.append(t)
            if remove:
                new_tags = [t for t in new_tags if t not in remove]

        # Rebuild mission
        parts = []
        if desc:
            parts.append(desc)
        if new_tags:
            parts.append(f"Tags: {', '.join(new_tags)}")
        new_mission = "\n\n".join(parts)

        await engine.update_bank(bank_id, mission=new_mission, request_context=ctx)
        return {"bank_id": bank_id, "tags_before": current, "tags_after": new_tags}


async def _delete_bank(bank_id: str):
    async with engine_context() as engine:
        ctx = default_context()
        await engine.delete_bank(bank_id, request_context=ctx)
        return {"deleted": True, "bank_id": bank_id}


async def _auto_profile_bank(bank_id: str, sample_size: int = 15):
    """Auto-generate bank profile from memories via LLM."""
    import asyncpg
    from openai import AsyncOpenAI

    async with engine_context() as engine:
        ctx = default_context()
        profile = await engine.get_bank_profile(bank_id, request_context=ctx)

        db_url = resolve_db_url()
        conn = await asyncpg.connect(db_url)
        try:
            memory_count = await conn.fetchval(
                f"SELECT COUNT(*) FROM {_fq_table('memory_units')} WHERE bank_id = $1",
                bank_id,
            ) or 0

            if memory_count < 5:
                return {
                    "error": f"Bank '{bank_id}' has only {memory_count} memories. Need at least 5.",
                    "bank_id": bank_id,
                }

            rows = await conn.fetch(
                f"""
                SELECT text FROM {_fq_table('memory_units')}
                WHERE bank_id = $1 AND text IS NOT NULL AND text != ''
                ORDER BY created_at DESC LIMIT $2
                """,
                bank_id, sample_size,
            )
            samples = [r["text"] for r in rows if r["text"]]
        finally:
            await conn.close()

        if not samples:
            return {"error": f"Bank '{bank_id}' has no readable memory texts.", "bank_id": bank_id}

        sample_text = "\n\n".join(f"- {t[:250]}" for t in samples)
        prompt = f"""You are a research assistant organizing a memory bank.

Bank ID: {bank_id}
Current memory count: {memory_count}

Here are sample research findings from this bank:

{sample_text}

Based on these findings, generate a concise bank profile.

Requirements:
- name: Human-readable display name (concise, ≤20 chars, Chinese or English)
- description: Research focus and scope (50-150 chars)
- tags: Research direction tags as a flat list. Use Title Case, e.g. ["DeFi", "DEX", "Trading"]
- mission: Research goal statement (≤50 chars)

Return ONLY valid JSON with this exact structure (no markdown, no explanations):
{{"name":"...","description":"...","tags":["..."],"mission":"..."}}"""

        cfg = load_config()
        client = AsyncOpenAI(
            api_key=cfg["llm_api_key"],
            base_url=cfg["llm_base_url"] or "https://api.groq.com/openai/v1",
        )
        model = cfg.get("llm_model") or "llama-3.3-70b-versatile"

        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_completion_tokens=2048,
        )

        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw
            raw = raw.rsplit("```", 1)[0] if "```" in raw else raw
            raw = raw.strip()

        generated = json.loads(raw)

        update_kwargs = {}
        if generated.get("name"):
            update_kwargs["name"] = generated["name"]

        # Encode description + tags into mission field
        desc = generated.get("description", "")
        tags = generated.get("tags", [])
        if desc or tags:
            parts = []
            if desc:
                parts.append(desc)
            if tags:
                parts.append(f"Tags: {', '.join(tags)}")
            update_kwargs["mission"] = "\n\n".join(parts)

        if update_kwargs:
            await engine.update_bank(bank_id, request_context=ctx, **update_kwargs)
            profile = await engine.get_bank_profile(bank_id, request_context=ctx)
        else:
            profile = await engine.get_bank_profile(bank_id, request_context=ctx)

        mission = profile.get("mission", "") or ""
        parsed_desc, parsed_tags = _parse_mission(mission)

        return {
            "bank_id": bank_id,
            "memory_count": memory_count,
            "generated": generated,
            "updated": True,
            "profile": {
                "name": profile.get("name", bank_id),
                "description": parsed_desc,
                "tags": parsed_tags,
                "mission": mission,
            },
        }


def _parse_tags(s: str | None) -> list[str] | None:
    if not s:
        return None
    return [t.strip() for t in s.split(",") if t.strip()]


def main():
    setup_utf8()
    parser = argparse.ArgumentParser(description="RealResearch: manage memory banks")
    subparsers = parser.add_subparsers(dest="command", help="Command")

    # create
    cp = subparsers.add_parser("create", help="Create or update a bank")
    cp.add_argument("--id", required=True, help="Bank ID")
    cp.add_argument("--name", default=None)
    cp.add_argument("--description", default=None)
    cp.add_argument("--tags", default=None)
    cp.add_argument("--mission", default=None, help="Direct mission text (overrides description+tags)")

    # list
    subparsers.add_parser("list", help="List all banks")

    # describe
    dp = subparsers.add_parser("describe", help="Show bank details")
    dp.add_argument("bank_id")

    # tag
    tp = subparsers.add_parser("tag", help="Manage bank tags")
    tp.add_argument("bank_id")
    tp.add_argument("--add", default=None)
    tp.add_argument("--remove", default=None)
    tp.add_argument("--set", default=None, dest="set_tags")

    # delete
    delp = subparsers.add_parser("delete", help="Delete a bank and all its memories")
    delp.add_argument("bank_id")

    # auto-profile
    ap = subparsers.add_parser("auto-profile", help="Auto-generate profile from memories")
    ap.add_argument("bank_id")
    ap.add_argument("--sample-size", type=int, default=15)

    args = parser.parse_args()

    if args.command == "create":
        result = asyncio.run(_create_bank(args.id, args.name, args.description, _parse_tags(args.tags), mission=args.mission))
    elif args.command == "list":
        result = asyncio.run(_list_banks())
    elif args.command == "describe":
        result = asyncio.run(_describe_bank(args.bank_id))
    elif args.command == "tag":
        result = asyncio.run(_tag_bank(args.bank_id, _parse_tags(args.add), _parse_tags(args.remove), _parse_tags(args.set_tags)))
    elif args.command == "delete":
        result = asyncio.run(_delete_bank(args.bank_id))
    elif args.command == "auto-profile":
        result = asyncio.run(_auto_profile_bank(args.bank_id, sample_size=args.sample_size))
    else:
        parser.print_help()
        sys.exit(1)

    print(json.dumps(result, ensure_ascii=False, indent=2))
