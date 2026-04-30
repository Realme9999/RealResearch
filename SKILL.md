---
name: real-research
description: "Spiral deep research with persistent memory — combines web search (Tavily) and research report search (Tushare) with Hindsight memory engine for research that builds on prior knowledge"
license: MIT
metadata:
  version: "0.1.0"
  tags: [research, search, memory, spiral, deep-research, hindsight, tushare, reports]
  requires: [RR_SEARCH_API_KEY, RR_EMBEDDING_API_KEY, RR_RERANK_API_KEY, RR_LLM_API_KEY]
---

# RealResearch

Spiral research methodology: deep search + persistent memory. Every session builds on prior knowledge.

## Directory Structure (CRITICAL)

The Hindsight engine **must** be placed inside the `RealResearch/` project root, **sibling to `real_research/`**.

```
RealResearch/                    ← Project root (where README.md / SKILL.md live)
├── hindsightbase/               ← MUST be here
│   └── hindsight-api-slim/
│       └── hindsight_api/
├── real_research/               ← Python source package
├── Reports/
├── README.md
├── SKILL.md
├── pyproject.toml
└── .env.example
```

> ⚠️ **Agent Note**: `engine.py` resolves the Hindsight path by walking **two levels up** from `real_research/engine.py` to the project root (`RealResearch/`), then looking for `hindsightbase/hindsight-api-slim`. Placing `hindsightbase` in the parent directory of `RealResearch/` or any other location will fail.

## Prerequisites

```bash
rr-env-check
```

If not ready:
1. **Python 3.11+**
2. **Clone Hindsight into the correct location**:
   ```bash
   cd /path/to/RealResearch
   git clone https://github.com/vectorize-io/hindsight.git hindsightbase
   ```
3. **Install**:
   - `pip install -e ./hindsightbase/hindsight-api-slim` (Hindsight engine)
   - `pip install -e .` (this tool)
4. **Config**: Copy `.env.example` to `.env`, fill in API keys (RR_* prefix)

## When to Use

- In-depth research requiring multiple sources and cross-referencing
- Research that benefits from building on previous findings
- Multi-session or longitudinal research topics
- Complex analysis requiring entity tracking and contradiction detection

### When NOT to Use

- Simple factual lookups (use web search directly)
- Single-source queries (use `WebFetch` or `WebSearch`)
- Casual Q&A that doesn't require persistent memory
- Time-sensitive queries where speed matters more than depth

## Available Tools

| Tool | Purpose |
|------|---------|
| `rr-search` | Web search via Tavily (cached) |
| `rr-fetch` | Fetch and extract webpage content |
| `rr-recall` | Retrieve relevant memories from prior research |
| `rr-retain` | Store new findings to persistent memory |
| `rr-reflect` | Synthesize reasoning over accumulated memories |
| `rr-report` | Generate and save final research report |
| `rr-bank` | Manage memory banks (research directions) |
| `rr-route` | Route query to the best matching bank |
| `rr-env-check` | Verify all dependencies |
| `rr-tushare-index` | Build/update Tushare research report index |
| `rr-tushare-search` | Search Tushare research reports from index |
| `rr-tushare-fetch` | Download and convert Tushare report PDFs to Markdown |
| `rr-log` | View and manage research session logs |

## Research Workflow: The Spiral

### Phase 0: Initialize

```bash
rr-env-check
```

Determine the **bank ID** for this research domain.

**For financial/stock research**, also ensure the Tushare index is up to date:
```bash
rr-tushare-index          # Incremental update (fast, only fetches new reports)
rr-tushare-index --months 3  # First-time: index last 3 months of reports
```

### Phase 1: Grounding (Recall existing knowledge)

ALWAYS start by recalling what is already known:

```bash
rr-recall --query "core concepts of the research question" --bank <bank-id> --budget high --max-tokens 4096
```

Analyze recall results: known facts, entities, connections, **knowledge gaps**.

If recall returns empty, this is a new domain. Proceed to Phase 2.

### Phase 2: Gap Analysis

Based on Phase 1, formulate 3-5 **targeted search queries** to fill gaps.

### Phase 3: Deep Search

Two search sources are available. Use one or both per spiral based on the research question:

**Web search** — real-time news, blogs, forums, official sites:
```bash
rr-search --query "<targeted query>" --max-results 8 --search-depth advanced
rr-fetch --url "<result URL>" --max-length 15000
```

**Research report search** — broker analysis, industry reports, financial data:
```bash
rr-tushare-search -q "<targeted query>" --mode semantic -n 5
rr-tushare-fetch --url "<pdf_url>" --topic "<research question>" --save ./reports/<name>.md
```

Filters for `rr-tushare-search`: `--industry`, `--org`, `--stock`, `--type`, `--start-date`, `--end-date`.

When `--topic` is set, `rr-tushare-fetch` uses LLM to distill the report into structured insights (returned in `insights` field). Full markdown is saved to `--save` path. The `insights` field is ready for direct storage via `rr-retain`.

**One tool per turn.** Fully analyze each result before the next step.

### Phase 4: Immediate Retain

Do NOT wait until the end. Store findings immediately.

**Web search findings:**
```bash
rr-retain --content "<structured finding>" --bank <bank-id> --context "Spiral 1, source: <url>"
```

Format:
```
Source: [URL]
Claim: [specific fact]
Context: [why this matters]
Entities: [key people/orgs/concepts]
Confidence: [confirmed/likely/uncertain/conflicting]
```

**Research report findings:**
The `rr-tushare-fetch --topic` command returns structured insights in the `insights` field. Store it directly:

```bash
rr-retain --content "<insights field from rr-tushare-fetch>" --bank <bank-id> --context "Spiral N, source: rr-tushare-search"
```

### Phase 5: Connection Recall

After retaining, recall again to discover cross-references:

```bash
rr-recall --query "<narrow query about a specific finding>" --bank <bank-id> --budget mid
```

Look for: shared entities, temporal patterns, semantic similarity, contradictions.

**Strategy triggers:**
- High-value entity (3+ mentions) → deep dive search
- Contradiction found → fact-check search
- New angle discovered → perspective search

### Phase 6: Convergence Check

- Have gaps been addressed? Contradictions resolved? Entities investigated?
- **Continue** if major gaps remain
- **Converge** if claims are cross-verified and searches return diminishing returns
- **Maximum 4-5 spirals**, then proceed even if minor gaps remain

### Phase 7: Reflect

```bash
rr-reflect --query "<original question with accumulated context>" --bank <bank-id> --budget high --max-tokens 8192 --output-file ./reflect.json
```

`--output-file` generates both `reflect.json` and `reflect.md`.

### Phase 8: Final Report

```bash
rr-report --query "<original question>" --content "<full markdown report>"
```

**Report structure:**
```markdown
# Research Report: <Question>

> Research date: YYYY-MM-DD
> Spirals completed: N
> Memory bank: <bank-id>

## Executive Summary
[2-3 sentence overview]

## Key Findings
### Finding 1: [Title]
[Details with source citations]

## Entity Analysis
## Contradictions & Resolutions
## Confidence Assessment
## Knowledge Gaps (remaining)
## Sources
```

## Rules

- **One tool per turn.** Never make multiple tool calls in a single response.
- **Always recall first.** Never search before checking existing memory.
- **Always retain findings.** Never discard search results without storing.
- **Never fabricate.** If recall returns nothing, state "no prior knowledge found."
- **Track spirals.** State which spiral number (1, 2, 3...) at the start of each.
- **State gaps explicitly.** List remaining gaps as a numbered list after each recall.
- **After ~15 tool calls** without convergence, evaluate whether to continue or report.
- **Respond in the user's language** unless otherwise requested.
- **Stop after tool calls.** After one tool call, end the response immediately.

## Error Handling

| Error | Fix |
|-------|-----|
| `rr-env-check` NOT READY | Fix reported missing dependencies |
| `rr-recall` error | Check RR_LLM_API_KEY and database connectivity |
| `rr-search` returns empty | Rewrite query with synonyms, try English/Chinese |
| `rr-fetch` 404/timeout | Search for cached version or alternative source |
| `rr-tushare-search` returns empty | Try semantic mode, broader keywords, or remove filters |
| `rr-tushare-fetch` download failed | Check URL validity, try `--id` mode instead |
| `rr-reflect` timeout | Reduce max-tokens or simplify query |

If the same error repeats 3 times, pause and report to the user.

## Memory Bank Strategy

- **One bank per research domain** (e.g., "crypto-markets", "ai-safety")
- Bank names: lowercase + hyphens
- Related sub-topics share the same bank for cross-referencing
- Default bank: "deep-research"

## Session Logging

Every research session is automatically logged. Each tool call (search, fetch, retain, recall, reflect, report) records its inputs, outputs, duration, and token usage.

**View logs:**
```bash
rr-log list                         # List all sessions
rr-log show <session-id>            # Show session overview
rr-log show <session-id> --step 3   # Show step detail
rr-log stats                        # Aggregate statistics
```

**Log storage:** `Logs/sessions/<session_id>/` — each step is a separate JSON file, session metadata in `session.json`, index in `Logs/sessions.jsonl`.

**Configuration (in .env):**
```
RR_LOG_ENABLED=true          # Enable/disable logging (default: true)
RR_LOG_FULL_RESULTS=false    # Store full tool outputs (default: false)
RR_LOG_RETENTION_DAYS=90     # Auto-cleanup after N days (default: 90)
```
