"""View and manage research session logs.

Usage:
    rr-log list                        # List all sessions
    rr-log show <session-id>           # Show session overview
    rr-log show <session-id> --step 3  # Show step detail
    rr-log stats                       # Aggregate statistics
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

from .logger import LOGS_ROOT, SESSIONS_DIR, SESSIONS_INDEX
from .utils import setup_utf8


def _load_session_meta(session_id: str) -> dict | None:
    path = os.path.join(SESSIONS_DIR, session_id, "session.json")
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_step(session_id: str, step: int) -> dict | None:
    session_dir = os.path.join(SESSIONS_DIR, session_id)
    files = sorted(f for f in os.listdir(session_dir) if f.startswith(f"{step:03d}_"))
    if not files:
        return None
    path = os.path.join(session_dir, files[0])
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _format_duration(ms: int) -> str:
    if ms < 1000:
        return f"{ms}ms"
    if ms < 60000:
        return f"{ms / 1000:.1f}s"
    return f"{ms / 60000:.1f}min"


def _format_time(iso_str: str | None) -> str:
    if not iso_str:
        return "—"
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return iso_str


# ── Commands ─────────────────────────────────────────────

def cmd_list(args):
    """List all research sessions."""
    if not os.path.isfile(SESSIONS_INDEX):
        print("No sessions found.")
        return

    sessions = []
    with open(SESSIONS_INDEX, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                sessions.append(json.loads(line))

    if not sessions:
        print("No sessions found.")
        return

    # Sort by start time descending
    sessions.sort(key=lambda s: s.get("started_at", ""), reverse=True)

    if args.limit:
        sessions = sessions[: args.limit]

    print(f"{'Session ID':<50} {'Steps':>5} {'Duration':>10} {'Tools'}")
    print("─" * 100)
    for s in sessions:
        sid = s["session_id"]
        steps = s.get("total_steps", 0)
        dur = _format_duration(s.get("total_duration_ms", 0))
        tools = ", ".join(
            f"{k}:{v}" for k, v in s.get("tools_used", {}).items()
        )
        print(f"{sid:<50} {steps:>5} {dur:>10} {tools}")


def cmd_show(args):
    """Show session details."""
    meta = _load_session_meta(args.session_id)
    if not meta:
        print(f"Session not found: {args.session_id}", file=sys.stderr)
        sys.exit(1)

    if args.step:
        # Show specific step
        step_data = _load_step(args.session_id, args.step)
        if not step_data:
            print(f"Step {args.step} not found in session {args.session_id}")
            sys.exit(1)
        print(json.dumps(step_data, ensure_ascii=False, indent=2))
        return

    # Show session overview
    print(f"Session: {meta['session_id']}")
    print(f"Query:   {meta['query']}")
    if meta.get("bank_id"):
        print(f"Bank:    {meta['bank_id']}")
    print(f"Started: {_format_time(meta.get('started_at'))}")
    print(f"Status:  {meta.get('status', '?')}")
    print(f"Steps:   {meta.get('total_steps', 0)}")
    print(f"Duration: {_format_duration(meta.get('total_duration_ms', 0))}")
    if meta.get("report_path"):
        print(f"Report:  {meta['report_path']}")

    # Token usage
    tokens = meta.get("token_usage", {})
    if tokens:
        print(f"\nToken Usage:")
        total_in = 0
        total_out = 0
        for k, v in tokens.items():
            print(f"  {k}: {v:,}")
            if "input" in k:
                total_in += v
            elif "output" in k:
                total_out += v
        if total_in or total_out:
            print(f"  ─────────────────")
            print(f"  Total input:  {total_in:,}")
            print(f"  Total output: {total_out:,}")

    # Tool summary
    tools = meta.get("tools_used", {})
    if tools:
        print(f"\nTools Used:")
        for tool, count in tools.items():
            print(f"  {tool}: {count} calls")

    # List steps
    print(f"\nSteps:")
    session_dir = os.path.join(SESSIONS_DIR, args.session_id)
    if os.path.isdir(session_dir):
        step_files = sorted(
            f for f in os.listdir(session_dir)
            if f.endswith(".json") and f != "session.json"
        )
        for sf in step_files:
            path = os.path.join(session_dir, sf)
            with open(path, "r", encoding="utf-8") as f:
                step = json.load(f)
            step_num = step.get("step", "?")
            tool = step.get("tool", "?")
            dur = _format_duration(step.get("duration_ms", 0))
            error = " ERROR" if step.get("error") else ""
            args_preview = ""
            if step.get("args"):
                first_arg = next(iter(step["args"].values()), None)
                if isinstance(first_arg, str):
                    args_preview = first_arg[:60]
                    if len(first_arg) > 60:
                        args_preview += "..."
            print(f"  [{step_num:03d}] {tool:<25} {dur:>8}  {args_preview}{error}")


def cmd_stats(args):
    """Show aggregate statistics across all sessions."""
    if not os.path.isdir(SESSIONS_DIR):
        print("No sessions found.")
        return

    total_sessions = 0
    total_steps = 0
    total_duration_ms = 0
    tool_totals: dict[str, int] = {}
    token_totals: dict[str, int] = {}

    for sid in os.listdir(SESSIONS_DIR):
        meta_path = os.path.join(SESSIONS_DIR, sid, "session.json")
        if not os.path.isfile(meta_path):
            continue
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)

        total_sessions += 1
        total_steps += meta.get("total_steps", 0)
        total_duration_ms += meta.get("total_duration_ms", 0)

        for tool, count in meta.get("tools_used", {}).items():
            tool_totals[tool] = tool_totals.get(tool, 0) + count

        for k, v in meta.get("token_usage", {}).items():
            token_totals[k] = token_totals.get(k, 0) + v

    print(f"Total Sessions:  {total_sessions}")
    print(f"Total Steps:     {total_steps}")
    print(f"Total Duration:  {_format_duration(total_duration_ms)}")
    if total_sessions > 0:
        print(f"Avg Steps/Session: {total_steps / total_sessions:.1f}")
        print(f"Avg Duration/Session: {_format_duration(total_duration_ms // total_sessions)}")

    if tool_totals:
        print(f"\nTool Usage (all sessions):")
        for tool, count in sorted(tool_totals.items(), key=lambda x: -x[1]):
            print(f"  {tool}: {count}")

    if token_totals:
        print(f"\nToken Usage (all sessions):")
        total_in = 0
        total_out = 0
        for k, v in sorted(token_totals.items()):
            print(f"  {k}: {v:,}")
            if "input" in k:
                total_in += v
            elif "output" in k:
                total_out += v
        if total_in or total_out:
            print(f"  ─────────────────")
            print(f"  Total input:  {total_in:,}")
            print(f"  Total output: {total_out:,}")


# ── Main ─────────────────────────────────────────────────

def main():
    setup_utf8()
    parser = argparse.ArgumentParser(
        description="RealResearch: view and manage research session logs"
    )
    sub = parser.add_subparsers(dest="command")

    # list
    p_list = sub.add_parser("list", help="List all sessions")
    p_list.add_argument("--limit", "-n", type=int, default=20, help="Max sessions to show")

    # show
    p_show = sub.add_parser("show", help="Show session details")
    p_show.add_argument("session_id", help="Session ID")
    p_show.add_argument("--step", "-s", type=int, default=None, help="Show specific step detail")

    # stats
    sub.add_parser("stats", help="Aggregate statistics")

    args = parser.parse_args()

    if args.command == "list":
        cmd_list(args)
    elif args.command == "show":
        cmd_show(args)
    elif args.command == "stats":
        cmd_stats(args)
    else:
        parser.print_help()
        sys.exit(1)
