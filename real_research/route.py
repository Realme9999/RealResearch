"""Route a research query to the most appropriate memory bank.

Hybrid scoring: 70% semantic similarity + 30% keyword overlap.

Usage:
    rr-route --query "Aster Chain L1 主网研究" --top 3
"""

import argparse
import asyncio
import json
import math
import sys

from .engine import engine_context, default_context, create_embeddings
from .utils import setup_utf8


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _bank_profile_text(bank: dict) -> str:
    parts = []
    if bank.get("name") or bank.get("bank_id", ""):
        parts.append(f"Name: {bank.get('name') or bank.get('bank_id', '')}")
    mission = bank.get("mission", "") or ""
    if mission:
        parts.append(mission)
    return "\n".join(parts)


def _keyword_overlap_score(query: str, profile_text: str) -> float:
    """Check if query keywords appear in the bank profile text."""
    query_words = set(query.lower().split())
    profile_lower = profile_text.lower()
    if not query_words:
        return 0.0
    matches = sum(1 for w in query_words if w in profile_lower and len(w) > 1)
    return min(matches / max(len(query_words), 1), 1.0)


async def _route_query(query: str, top_n: int = 3):
    async with engine_context() as engine:
        ctx = default_context()
        banks = await engine.list_banks(request_context=ctx)

        if not banks:
            return {
                "query": query,
                "recommended_banks": [],
                "message": "No banks found. Create one with: rr-bank create --id <name>",
            }

        # Build profile texts from bank name + mission
        bank_profiles = []
        for b in banks:
            text = _bank_profile_text(b)
            bank_profiles.append({
                "bank_id": b.get("bank_id", ""),
                "name": b.get("name") or b.get("bank_id", ""),
                "profile_text": text,
            })

        # Compute embeddings
        embeddings = create_embeddings()
        await embeddings.initialize()

        query_emb = embeddings.encode([query])[0]
        bank_embs = [embeddings.encode([bp["profile_text"]])[0] for bp in bank_profiles]

        # Score
        scored = []
        for bp, emb in zip(bank_profiles, bank_embs):
            sim = _cosine_similarity(query_emb, emb)
            kw_score = _keyword_overlap_score(query, bp["profile_text"])
            combined = sim * 0.7 + kw_score * 0.3
            scored.append({
                "bank_id": bp["bank_id"],
                "name": bp["name"],
                "semantic_score": round(sim, 4),
                "keyword_score": round(kw_score, 4),
                "combined_score": round(combined, 4),
            })

        scored.sort(key=lambda x: x["combined_score"], reverse=True)

        # Reasoning
        top = scored[0] if scored else None
        reasoning = ""
        if top:
            if top["semantic_score"] > 0.75:
                reasoning = f"Strong semantic match ({top['semantic_score']:.2f}) with '{top['name']}'"
            elif top["keyword_score"] > 0.5:
                reasoning = f"Keyword overlap ({top['keyword_score']:.2f}) with '{top['name']}'"
            elif top["combined_score"] > 0.4:
                reasoning = f"Moderate match ({top['combined_score']:.2f}) with '{top['name']}'"
            else:
                reasoning = f"Weak match ({top['combined_score']:.2f}). Consider creating a new bank."

        return {
            "query": query,
            "reasoning": reasoning,
            "recommended_banks": scored[:top_n],
        }


def main():
    setup_utf8()
    parser = argparse.ArgumentParser(description="RealResearch: route query to best bank")
    parser.add_argument("--query", "-q", required=True)
    parser.add_argument("--top", type=int, default=3)
    args = parser.parse_args()

    result = asyncio.run(_route_query(args.query, top_n=args.top))
    print(json.dumps(result, ensure_ascii=False, indent=2))
