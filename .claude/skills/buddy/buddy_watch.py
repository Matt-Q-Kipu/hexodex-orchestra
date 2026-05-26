#!/usr/bin/env python3
"""
Buddy Watch — a live Textual viewer for your coding companion.

Run in a separate terminal pane alongside Claude Code:
    python3 .claude/skills/buddy/buddy_watch.py

The app watches .buddy_state.json for changes and live-updates
the buddy card with animation and a scrolling reaction log.

Press q or ctrl+c to quit.
"""

import glob
import json
import os
import sys
import time
from pathlib import Path

try:
    from textual.app import App, ComposeResult
    from textual.widgets import Static, Footer, TabbedContent, TabPane
    from textual.containers import Vertical
    from textual.reactive import reactive
except ImportError:
    print("buddy_watch requires Textual: pip3 install textual")
    sys.exit(1)

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
except ImportError:
    print("buddy_watch requires watchdog: pip3 install watchdog")
    sys.exit(1)

BUDDY_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BUDDY_DIR)

from buddy import (
    load_state,
    render_buddy_card_rich,
    render_ascii,
    PLAY_SCENARIOS,
    REACTIONS_PET,
    HAS_RICH,
)

BUDDY_FILE = os.path.join(BUDDY_DIR, ".buddy_state.json")

# Claude Stuffs

# Claude Code transcript location — one .jsonl per session.
# Per Claude Code v2.1.126 binary (function P5_ and B2):
#   used = input + cache_creation + cache_read + output
#   denom = model context window (1M for claude-opus-4-7, 200K otherwise)
# This matches the Claude Code footer's "X% used" display exactly.
CLAUDE_PROJECTS_DIR = os.path.expanduser("~/.claude/projects")
MODEL_CONTEXT_WINDOWS = {
    "claude-opus-4-7": 1_000_000,
    "claude-opus-4-6": 200_000,
    "claude-sonnet-4-6": 200_000,
    "claude-sonnet-4-5": 200_000,
    "claude-opus-4-5": 200_000,
    "claude-haiku-4-5": 200_000,
}
DEFAULT_CONTEXT_WINDOW = 200_000

USER_SETTINGS_PATH = os.path.expanduser("~/.claude/settings.json")


def _read_effort_level():
    """Read effortLevel from ~/.claude/settings.json, or None."""
    try:
        with open(USER_SETTINGS_PATH) as f:
            return json.load(f).get("effortLevel")
    except (OSError, json.JSONDecodeError):
        return None

# Auto-compact thresholds, per Claude Code binary (functions m9H, c08, CB7).
# Effective window reserves output capacity: window - min(max_output, 20000).
# For claude-opus-4-7, max_output default is 64K — so reserve is capped at 20K.
# Auto-compact fires at: effective_window - 13000.
# Hard block at: effective_window - 3000.
MAX_OUTPUT_RESERVE = 20_000
AUTO_COMPACT_MARGIN = 13_000
BLOCK_MARGIN = 3_000

def _find_latest_transcript(entrypoint="cli"):
    """Return the most recently modified .jsonl transcript matching the given entrypoint."""
    if not os.path.isdir(CLAUDE_PROJECTS_DIR):
        return None
    pattern = os.path.join(CLAUDE_PROJECTS_DIR, "*", "*.jsonl")
    latest = None
    latest_mtime = 0
    for path in glob.glob(pattern):
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            continue
        if mtime > latest_mtime:
            _, ep = _transcript_meta(path)
            if ep != entrypoint:
                continue
            latest_mtime = mtime
            latest = path
    return latest


def _read_last_usage(path):
    """Scan the JSONL backwards for the most recent assistant usage block."""
    if not path:
        return None
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            chunk_size = min(size, 65536)
            f.seek(max(0, size - chunk_size))
            tail = f.read().decode("utf-8", errors="replace")
    except OSError:
        return None
    lines = tail.splitlines()
    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = d.get("message") if isinstance(d.get("message"), dict) else None
        usage = msg.get("usage") if msg else None
        if isinstance(usage, dict) and "input_tokens" in usage:
            return usage
    return None


def _context_tokens(usage):
    if not usage:
        return 0
    return (
        usage.get("input_tokens", 0)
        + usage.get("cache_creation_input_tokens", 0)
        + usage.get("cache_read_input_tokens", 0)
        + usage.get("output_tokens", 0)
    )


def _context_window_for(model):
    if not model:
        return DEFAULT_CONTEXT_WINDOW
    for prefix, window in MODEL_CONTEXT_WINDOWS.items():
        if model.startswith(prefix):
            return window
    return DEFAULT_CONTEXT_WINDOW


def _auto_compact_threshold(window):
    """Tokens at which Claude Code's auto-compact fires."""
    return window - MAX_OUTPUT_RESERVE - AUTO_COMPACT_MARGIN


# Claude Code cost estimation — per-MTok rates from platform.claude.com/docs/en/about-claude/pricing.
# Cache operations ARE billed: write=1.25x base input, read=0.1x base input.
# The JSONL transcript logs each message twice (parent+child entries with identical
# usage). We deduplicate by message ID.
PRICING = {
    # prefix match; order matters (most specific first)
    "claude-opus":       {"input":  5.00, "output": 25.00, "cache_write":  6.25, "cache_read": 0.50},
    "claude-sonnet":     {"input":  3.00, "output": 15.00, "cache_write":  3.75, "cache_read": 0.30},
    "claude-haiku-4-5":  {"input":  1.00, "output":  5.00, "cache_write":  1.25, "cache_read": 0.10},
    "claude-3-5-haiku":  {"input":  0.80, "output":  4.00, "cache_write":  1.00, "cache_read": 0.08},
}

# Orwell's *1984* is ~89K words ≈ ~49K tokens (empirical ratio ~0.55 tok/word
# for English prose). Used for the whimsical "Nx 1984" comparison.
TOKENS_PER_1984 = 49_000

# Opus context budget (practical ceiling before auto-compaction).
SESSION_CACHE = {"path": None, "mtime": 0, "stats": None}
DESKTOP_SESSION_CACHE = {"path": None, "mtime": 0, "stats": None}

# Daily token/cost accumulator — tracks totals across all sessions today.
# Uses the same date-comparison pattern as buddy.py weather/teach logic.
DAILY_CACHE = {
    "cli": {"date": None, "total_tokens": 0, "total_cost": 0.0, "last_scan": 0},
    "claude-desktop": {"date": None, "total_tokens": 0, "total_cost": 0.0, "last_scan": 0},
}

BILLING_BUDGET = 100.0
BILLING_PERIOD_START = "2026-05-15"
BILLING_CACHE = {"month": None, "total_tokens": 0, "total_cost": 0.0, "last_scan": 0}

DESKTOP_5H_LIMIT = 48_000_000
DESKTOP_5H_CACHE = {"total_tokens": 0, "reset": "", "last_scan": 0}

WEEKLY_LIMIT = 2_400_000_000
WEEKLY_CACHE = {"total_tokens": 0, "reset": "", "last_scan": 0}

FILE_STATS_CACHE = {}
META_CACHE = {}


def _transcript_meta(path):
    """Return (start_date, entrypoint) for a transcript, cached by mtime."""
    from datetime import date as _date
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None, None
    cached = META_CACHE.get(path)
    if cached and cached[0] == mtime:
        return cached[1], cached[2]
    result_date = None
    result_ep = None
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not result_date:
                    ts = d.get("timestamp")
                    if ts and len(ts) >= 10:
                        try:
                            result_date = _date.fromisoformat(ts[:10])
                        except ValueError:
                            pass
                if not result_ep:
                    result_ep = d.get("entrypoint")
                if result_date and result_ep:
                    break
    except OSError:
        pass
    META_CACHE[path] = (mtime, result_date, result_ep)
    return result_date, result_ep


def _stats_for_transcript(path):
    """Extract total tokens and cost from a transcript. Caches by mtime."""
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return 0, 0.0
    cached = FILE_STATS_CACHE.get(path)
    if cached and cached[0] == mtime:
        return cached[1], cached[2]
    tokens_in = tokens_out = tokens_cr = tokens_cc = 0
    cost = 0.0
    seen_msg_ids = set()
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg = d.get("message") if isinstance(d.get("message"), dict) else None
                if msg:
                    usage = msg.get("usage")
                    if isinstance(usage, dict):
                        msg_id = msg.get("id")
                        if msg_id:
                            if msg_id in seen_msg_ids:
                                continue
                            seen_msg_ids.add(msg_id)
                        ti = usage.get("input_tokens", 0)
                        to = usage.get("output_tokens", 0)
                        tcc = usage.get("cache_creation_input_tokens", 0)
                        tcr = usage.get("cache_read_input_tokens", 0)
                        tokens_in += ti
                        tokens_out += to
                        tokens_cc += tcc
                        tokens_cr += tcr
                        model = msg.get("model", "")
                        rates = _price_for_model(model or "")
                        cost += (
                            ti * rates["input"]
                            + to * rates["output"]
                            + tcc * rates["cache_write"]
                            + tcr * rates["cache_read"]
                        ) / 1_000_000
    except OSError:
        return 0, 0.0
    total = tokens_in + tokens_out + tokens_cr + tokens_cc
    FILE_STATS_CACHE[path] = (mtime, total, cost)
    return total, cost


def _daily_totals(entrypoint="cli"):
    """Return (total_tokens, total_cost) across sessions today for the given entrypoint."""
    from datetime import datetime, date
    now = time.time()
    cache = DAILY_CACHE.get(entrypoint)
    if not cache:
        cache = {"date": None, "total_tokens": 0, "total_cost": 0.0, "last_scan": 0}
        DAILY_CACHE[entrypoint] = cache
    today_str = datetime.now().strftime("%Y-%m-%d")
    if cache["date"] != today_str:
        cache["date"] = today_str
        cache["total_tokens"] = 0
        cache["total_cost"] = 0.0
        cache["last_scan"] = 0
    if now - cache["last_scan"] < 30:
        return cache["total_tokens"], cache["total_cost"]
    cache["last_scan"] = now
    if not os.path.isdir(CLAUDE_PROJECTS_DIR):
        return 0, 0.0
    patterns = [
        os.path.join(CLAUDE_PROJECTS_DIR, "*", "*.jsonl"),
        os.path.join(CLAUDE_PROJECTS_DIR, "*", "*", "subagents", "*.jsonl"),
    ]
    today = date.today()
    total_tokens = 0
    total_cost = 0.0
    for pattern in patterns:
        for path in glob.glob(pattern):
            ts_date, ep = _transcript_meta(path)
            if ts_date != today or ep != entrypoint:
                continue
            t, c = _stats_for_transcript(path)
            total_tokens += t
            total_cost += c
    cache["total_tokens"] = total_tokens
    cache["total_cost"] = total_cost
    return total_tokens, total_cost


def _billing_period_totals():
    """Return (total_tokens, total_cost) across all CLI sessions since BILLING_PERIOD_START."""
    from datetime import date
    now = time.time()
    period_start = date.fromisoformat(BILLING_PERIOD_START)
    cache_key = BILLING_PERIOD_START
    if BILLING_CACHE["month"] != cache_key:
        BILLING_CACHE["month"] = cache_key
        BILLING_CACHE["total_tokens"] = 0
        BILLING_CACHE["total_cost"] = 0.0
        BILLING_CACHE["last_scan"] = 0
    if now - BILLING_CACHE["last_scan"] < 30:
        return BILLING_CACHE["total_tokens"], BILLING_CACHE["total_cost"]
    BILLING_CACHE["last_scan"] = now
    if not os.path.isdir(CLAUDE_PROJECTS_DIR):
        return 0, 0.0
    patterns = [
        os.path.join(CLAUDE_PROJECTS_DIR, "*", "*.jsonl"),
        os.path.join(CLAUDE_PROJECTS_DIR, "*", "*", "subagents", "*.jsonl"),
    ]
    total_tokens = 0
    total_cost = 0.0
    for pattern in patterns:
        for path in glob.glob(pattern):
            ts_date, ep = _transcript_meta(path)
            if not ts_date or ts_date < period_start or ep == "claude-desktop":
                continue
            t, c = _stats_for_transcript(path)
            total_tokens += t
            total_cost += c
    BILLING_CACHE["total_tokens"] = total_tokens
    BILLING_CACHE["total_cost"] = total_cost
    return total_tokens, total_cost


DESKTOP_MONTHLY_CACHE = {"month": None, "total_tokens": 0, "total_cost": 0.0, "last_scan": 0}


def _desktop_monthly_totals():
    """Return (total_tokens, total_cost) across Desktop sessions this calendar month."""
    from datetime import datetime, date
    now = time.time()
    current_month = datetime.now().strftime("%Y-%m")
    if DESKTOP_MONTHLY_CACHE["month"] != current_month:
        DESKTOP_MONTHLY_CACHE["month"] = current_month
        DESKTOP_MONTHLY_CACHE["total_tokens"] = 0
        DESKTOP_MONTHLY_CACHE["total_cost"] = 0.0
        DESKTOP_MONTHLY_CACHE["last_scan"] = 0
    if now - DESKTOP_MONTHLY_CACHE["last_scan"] < 30:
        return DESKTOP_MONTHLY_CACHE["total_tokens"], DESKTOP_MONTHLY_CACHE["total_cost"]
    DESKTOP_MONTHLY_CACHE["last_scan"] = now
    if not os.path.isdir(CLAUDE_PROJECTS_DIR):
        return 0, 0.0
    month_start = date(datetime.now().year, datetime.now().month, 1)
    patterns = [
        os.path.join(CLAUDE_PROJECTS_DIR, "*", "*.jsonl"),
        os.path.join(CLAUDE_PROJECTS_DIR, "*", "*", "subagents", "*.jsonl"),
    ]
    total_tokens = 0
    total_cost = 0.0
    for pattern in patterns:
        for path in glob.glob(pattern):
            ts_date, ep = _transcript_meta(path)
            if not ts_date or ts_date < month_start or ep != "claude-desktop":
                continue
            t, c = _stats_for_transcript(path)
            total_tokens += t
            total_cost += c
    DESKTOP_MONTHLY_CACHE["total_tokens"] = total_tokens
    DESKTOP_MONTHLY_CACHE["total_cost"] = total_cost
    return total_tokens, total_cost


def _fmt_reset(seconds):
    """Format seconds-until-reset as a human string like '4h', '2h 30m', '5d'."""
    if seconds <= 0:
        return "now"
    s = int(seconds)
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m = s // 60
    if d:
        return f"{d}d {h}h" if h else f"{d}d"
    if h:
        return f"{h}h {m}m" if m else f"{h}h"
    return f"{m}m"


def _desktop_5h_usage():
    """Return (total_tokens, pct, reset_str) for Desktop sessions active in the last 5 hours."""
    now = time.time()
    if now - DESKTOP_5H_CACHE["last_scan"] < 10:
        tokens = DESKTOP_5H_CACHE["total_tokens"]
        pct = min(100, tokens / DESKTOP_5H_LIMIT * 100) if DESKTOP_5H_LIMIT else 0
        return tokens, pct, DESKTOP_5H_CACHE["reset"]
    DESKTOP_5H_CACHE["last_scan"] = now
    if not os.path.isdir(CLAUDE_PROJECTS_DIR):
        return 0, 0, ""
    window = 5 * 3600
    cutoff = now - window
    patterns = [
        os.path.join(CLAUDE_PROJECTS_DIR, "*", "*.jsonl"),
        os.path.join(CLAUDE_PROJECTS_DIR, "*", "*", "subagents", "*.jsonl"),
    ]
    total_tokens = 0
    oldest_mtime = None
    for pattern in patterns:
        for path in glob.glob(pattern):
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                continue
            if mtime < cutoff:
                continue
            _, ep = _transcript_meta(path)
            if ep != "claude-desktop":
                continue
            t, _ = _stats_for_transcript(path)
            total_tokens += t
            if oldest_mtime is None or mtime < oldest_mtime:
                oldest_mtime = mtime
    reset_str = ""
    if oldest_mtime:
        reset_str = "resets " + _fmt_reset((oldest_mtime + window) - now)
    DESKTOP_5H_CACHE["total_tokens"] = total_tokens
    DESKTOP_5H_CACHE["reset"] = reset_str
    pct = min(100, total_tokens / DESKTOP_5H_LIMIT * 100) if DESKTOP_5H_LIMIT else 0
    return total_tokens, pct, reset_str


def _weekly_usage():
    """Return (total_tokens, pct, reset_str) across all sessions in the last 7 days."""
    now = time.time()
    if now - WEEKLY_CACHE["last_scan"] < 30:
        tokens = WEEKLY_CACHE["total_tokens"]
        pct = min(100, tokens / WEEKLY_LIMIT * 100) if WEEKLY_LIMIT else 0
        return tokens, pct, WEEKLY_CACHE["reset"]
    WEEKLY_CACHE["last_scan"] = now
    if not os.path.isdir(CLAUDE_PROJECTS_DIR):
        return 0, 0, ""
    window = 7 * 24 * 3600
    cutoff = now - window
    patterns = [
        os.path.join(CLAUDE_PROJECTS_DIR, "*", "*.jsonl"),
        os.path.join(CLAUDE_PROJECTS_DIR, "*", "*", "subagents", "*.jsonl"),
    ]
    total_tokens = 0
    oldest_mtime = None
    for pattern in patterns:
        for path in glob.glob(pattern):
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                continue
            if mtime < cutoff:
                continue
            t, _ = _stats_for_transcript(path)
            total_tokens += t
            if oldest_mtime is None or mtime < oldest_mtime:
                oldest_mtime = mtime
    from datetime import datetime, timedelta
    today = datetime.now()
    days_until_monday = (7 - today.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    next_monday = today.replace(hour=11, minute=0, second=0, microsecond=0) + timedelta(days=days_until_monday)
    secs_to_reset = (next_monday - today).total_seconds()
    reset_str = "resets " + _fmt_reset(secs_to_reset)
    WEEKLY_CACHE["total_tokens"] = total_tokens
    WEEKLY_CACHE["reset"] = reset_str
    pct = min(100, total_tokens / WEEKLY_LIMIT * 100) if WEEKLY_LIMIT else 0
    return total_tokens, pct, reset_str


def _price_for_model(model):
    for prefix, rates in PRICING.items():
        if model.startswith(prefix):
            return rates
    return PRICING["claude-opus"]


def _scan_session_stats(path, cache=None):
    """Read the full transcript and extract per-session stats. Caches by mtime."""
    if cache is None:
        cache = SESSION_CACHE
    if not path:
        return None
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    session_uuid = os.path.splitext(os.path.basename(path))[0]
    subagent_dir = os.path.join(os.path.dirname(path), session_uuid, "subagents")
    subagent_files = glob.glob(os.path.join(subagent_dir, "*.jsonl")) if os.path.isdir(subagent_dir) else []
    combined_mtime = mtime
    for sf in subagent_files:
        try:
            combined_mtime = max(combined_mtime, os.path.getmtime(sf))
        except OSError:
            pass
    if cache["path"] == path and cache["mtime"] == combined_mtime:
        return cache["stats"]

    first_ts = last_ts = None
    models = set()
    versions = set()
    session_id = None
    api_duration_ms = 0
    code_changes = 0
    tokens_in = tokens_out = tokens_cr = tokens_cc = 0
    cost = 0.0
    last_model = None
    seen_msg_ids = set()

    all_files = [path] + subagent_files
    for transcript_file in all_files:
        try:
            with open(transcript_file) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    ts = d.get("timestamp")
                    if ts:
                        if not first_ts:
                            first_ts = ts
                        last_ts = ts
                    if d.get("version"):
                        versions.add(d["version"])
                    if d.get("sessionId") and not session_id:
                        session_id = d["sessionId"]
                    if d.get("durationMs"):
                        api_duration_ms += d["durationMs"]
                    msg = d.get("message") if isinstance(d.get("message"), dict) else None
                    if msg:
                        model = msg.get("model")
                        if model:
                            models.add(model)
                            if transcript_file == path:
                                last_model = model
                        usage = msg.get("usage")
                        if isinstance(usage, dict):
                            msg_id = msg.get("id", "")
                            if msg_id in seen_msg_ids:
                                continue
                            seen_msg_ids.add(msg_id)
                            ti = usage.get("input_tokens", 0)
                            to = usage.get("output_tokens", 0)
                            tcc = usage.get("cache_creation_input_tokens", 0)
                            tcr = usage.get("cache_read_input_tokens", 0)
                            tokens_in += ti
                            tokens_out += to
                            tokens_cc += tcc
                            tokens_cr += tcr
                            rates = _price_for_model(model or "")
                            cost += (
                                ti * rates["input"]
                                + to * rates["output"]
                                + tcc * rates["cache_write"]
                                + tcr * rates["cache_read"]
                            ) / 1_000_000
                        content = msg.get("content")
                        if isinstance(content, list):
                            for c in content:
                                if isinstance(c, dict) and c.get("type") == "tool_use":
                                    name = c.get("name", "")
                                    if name in ("Edit", "Write", "NotebookEdit"):
                                        code_changes += 1
        except OSError:
            continue

    wall_ms = 0
    if first_ts and last_ts:
        from datetime import datetime
        try:
            a = datetime.fromisoformat(first_ts.replace("Z", "+00:00"))
            b = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
            wall_ms = int((b - a).total_seconds() * 1000)
        except ValueError:
            wall_ms = 0

    # Total billed tokens (includes cache_read — inflated by re-shipped history).
    total_tokens = tokens_in + tokens_out + tokens_cr + tokens_cc
    # Unique tokens produced in this session: exclude cache_read, which is the
    # same conversation history re-sent on every turn. This is the right basis
    # for the "Nx 1984" comparison — how much novel prose we actually generated.
    unique_tokens = tokens_in + tokens_out + tokens_cc

    stats = {
        "session_id": session_id,
        "model": last_model or (next(iter(models)) if models else None),
        "version": next(iter(sorted(versions))) if versions else None,
        "wall_ms": wall_ms,
        "api_ms": api_duration_ms,
        "code_changes": code_changes,
        "cost": cost,
        "total_tokens": total_tokens,
        "unique_tokens": unique_tokens,
        "ratio_1984": unique_tokens / TOKENS_PER_1984 if unique_tokens else 0,
    }
    cache["path"] = path
    cache["mtime"] = combined_mtime
    cache["stats"] = stats
    return stats


def _fmt_duration(ms):
    if not ms:
        return "—"
    s = ms // 1000
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}h {m}m {sec}s"
    if m:
        return f"{m}m {sec}s"
    return f"{sec}s"


class SessionPane(Static):
    """Renders session stats for a single session (API or Desktop)."""

    def __init__(self, entrypoint="cli", show_context_bar=False, show_budget=False, **kwargs):
        super().__init__(**kwargs)
        self.tokens = 0
        self.stats = None
        self.entrypoint = entrypoint
        self.show_context_bar = show_context_bar
        self.show_budget = show_budget

    def update_stats(self, stats, tokens=0):
        self.stats = stats
        self.tokens = tokens
        self.refresh()

    def render(self):
        from rich.text import Text

        out = Text()

        if not self.stats:
            out.append("  waiting for session...", style="dim")
            return out

        s = self.stats
        def row(label, value):
            out.append(f"  {label:<18}", style="dim")
            out.append(f"{value}\n")

        row("Model",                (s.get("model") or "—").removeprefix("claude-"))
        effort = _read_effort_level()
        if effort:
            row("Effort",            effort)
        out.append("\n")
        row("Session cost",         f"${s.get('cost', 0):.2f}")
        row("Tokens (session)",     f"{s.get('total_tokens', 0):,}")
        daily_tokens, daily_cost = _daily_totals(self.entrypoint)
        if daily_cost >= 90:
            budget_color = "red"
        elif daily_cost >= 75:
            budget_color = "orange1"
        elif daily_cost >= 50:
            budget_color = "yellow"
        else:
            budget_color = "green"
        out.append(f"  {'Cost (today)':<18}", style="dim")
        out.append(f"${daily_cost:.2f}\n", style=budget_color)
        out.append(f"  {'Tokens (today)':<18}", style="dim")
        out.append(f"{daily_tokens:,}\n", style=budget_color)

        if self.show_budget:
            billing_tokens, billing_cost = _billing_period_totals()
            billing_remaining = BILLING_BUDGET - billing_cost
            if billing_remaining <= 5:
                billing_color = "red"
            elif billing_remaining <= 15:
                billing_color = "orange1"
            elif billing_remaining <= 30:
                billing_color = "yellow"
            else:
                billing_color = "green"
            out.append(f"  {'Cost (period)':<18}", style="dim")
            out.append(f"${billing_cost:.2f}", style=billing_color)
            out.append(f" / ${BILLING_BUDGET:.0f}\n", style="dim")
            out.append(f"  {'Tokens (period)':<18}", style="dim")
            out.append(f"{billing_tokens:,}\n", style=billing_color)

        if self.entrypoint == "claude-desktop":
            monthly_tokens, monthly_cost = _desktop_monthly_totals()
            row("Cost (month)",         f"${monthly_cost:.2f}")
            row("Tokens (month)",       f"{monthly_tokens:,}")
            out.append("\n")
            tokens_5h, pct_5h, reset_5h = _desktop_5h_usage()
            if pct_5h >= 90:
                color_5h = "red"
            elif pct_5h >= 75:
                color_5h = "orange1"
            elif pct_5h >= 50:
                color_5h = "yellow"
            else:
                color_5h = "green"
            bar_w = 20
            filled_5h = max(0, min(bar_w, int(round((pct_5h / 100) * bar_w))))
            out.append(f"  {'5h limit':<18}", style="dim")
            out.append(f"{pct_5h:.0f}%\n", style=f"bold {color_5h}")
            out.append("  ", style="dim")
            out.append("█" * filled_5h, style=color_5h)
            out.append("░" * (bar_w - filled_5h), style="bright_black")
            out.append(f"\n  {reset_5h}\n", style="dim")
            tokens_wk, pct_wk, reset_wk = _weekly_usage()
            if pct_wk >= 90:
                color_wk = "red"
            elif pct_wk >= 75:
                color_wk = "orange1"
            elif pct_wk >= 50:
                color_wk = "yellow"
            else:
                color_wk = "green"
            filled_wk = max(0, min(bar_w, int(round((pct_wk / 100) * bar_w))))
            out.append(f"\n  {'Weekly (all)':<18}", style="dim")
            out.append(f"{pct_wk:.0f}%\n", style=f"bold {color_wk}")
            out.append("  ", style="dim")
            out.append("█" * filled_wk, style=color_wk)
            out.append("░" * (bar_w - filled_wk), style="bright_black")
            out.append(f"\n  {reset_wk}\n", style="dim")
        else:
            row("Duration (API)",       _fmt_duration(s.get("api_ms", 0)))
            row("Duration (wall)",      _fmt_duration(s.get("wall_ms", 0)))
        out.append("\n")
        row("Code changes",         str(s.get("code_changes", 0)))
        row("1984x",                f"{s.get('ratio_1984', 0):.1f}x Orwell")

        if self.show_context_bar and self.tokens:
            out.append("\n")
            window = _context_window_for(s.get("model"))
            compact_at = _auto_compact_threshold(window)
            pct = min(100, (self.tokens / window) * 100)
            width = 20
            filled = max(0, min(width, int(round((pct / 100) * width))))

            if self.tokens >= compact_at:
                color = "red"
            elif pct >= 75:
                color = "orange1"
            elif pct >= 50:
                color = "yellow"
            else:
                color = "green"

            out.append("  ctx ", style="dim")
            out.append(f"{pct:4.1f}% ", style=f"bold {color}")
            out.append("█" * filled, style=color)
            out.append("░" * (width - filled), style="dim")
            remaining_to_compact = compact_at - self.tokens
            if remaining_to_compact <= 0:
                out.append(f"\n  {self.tokens // 1000}K / {window // 1000}K tok", style="dim")
                out.append("\n  ⚠ auto-compact imminent", style="bold red")
            else:
                pct_to_compact = remaining_to_compact / window * 100
                warn_style = "bold yellow" if pct_to_compact < 10 else "dim"
                out.append(f"\n  {self.tokens // 1000}K / {window // 1000}K tok ", style="dim")
                out.append(f"({remaining_to_compact // 1000}K to go)", style=warn_style)
                out.append(
                    f"\n  auto-compact at {compact_at // 1000}K",
                    style=warn_style,
                )
        return out


# ── Play animation frames (per-species) ────────────────────────────────────

CAT_PLAY_FRAMES = [
    (["     ~ )(   ",
      "  /\\_/\\     ",
      "  ( o o )   ",
      "  (  w  )   ",
      '  (")_(")   '],
     "[dim italic]...spots a butterfly[/]"),
    (["      )(    ",
      "  /\\_/\\     ",
      "  ( O_O )   ",
      "~~(  w  )   ",
      '  (") (")   '],
     "[bold yellow]*wiggles butt*[/]"),
    (["  /\\_/\\ )(  ",
      "  ( >w< )   ",
      "  /|  |\\    ",
      "   /  \\     ",
      '    ~~      '],
     "[bold red]POUNCE![/]"),
    (["         )( ",
      "            ",
      "  \\/_\\/     ",
      "  ( x_x )   ",
      '  /") (")\\  '],
     "[dim]...missed![/]"),
    (["            ",
      "  /\\_/\\     ",
      "  ( @ @ )   ",
      "~  ( w  )   ",
      '  (")_(")   '],
     "[bold cyan]*chases tail*[/]"),
    (["            ",
      "     /\\_/\\  ",
      "    ( @.@ ) ",
      "    ( w )~  ",
      '    (")(")  '],
     "[bold cyan]*spins faster*[/]"),
    (["   *  *  *  ",
      "  /\\_/\\     ",
      "  ( x x )   ",
      "  (  ~  )   ",
      '  (")_(")   '],
     "[bold magenta]*seeing stars*[/]"),
    (["            ",
      "  /\\_/\\  !  ",
      "  ( o O )   ",
      "  (  w  )   ",
      '  (")_(")   '],
     "[yellow]*shakes it off*[/]"),
    (["            ",
      ")(          ",
      "  /\\_/\\     ",
      "  ( ^ ^ )   ",
      '  (  w  )   '],
     "[dim italic]oh, there you are...[/]"),
    (["  )(        ",
      "  /\\_/\\     ",
      "  ( - - )   ",
      "  (  w  )   ",
      '  (")_(")   '],
     "[bold green]*purrs smugly*[/]"),
]

GENERIC_PLAY_FRAMES = [
    (["     *      ",
      "            ",
      "    \\o/     ",
      "     |      ",
      "    / \\     "],
     "[bold yellow]*plays!*[/]"),
    (["            ",
      "      *     ",
      "     o      ",
      "    /|\\     ",
      "    / \\     "],
     "[bold cyan]*spins*[/]"),
    (["  *         ",
      "            ",
      "     o      ",
      "    /|\\     ",
      "    / \\     "],
     "[bold cyan]*twirls*[/]"),
    (["    *       ",
      "            ",
      "    \\o/     ",
      "     |      ",
      "    / \\     "],
     "[bold green]*ta-da!*[/]"),
]

CAT_PET_FRAMES = [
    (["            ",
      "   /\\_/\\    ",
      "  ( O O )   ",
      "  (  w  )   ",
      '  (")_(")   '],
     "[dim italic]hmm?[/]"),
    (["     ~      ",
      "   /\\_/\\    ",
      "  ( ^ ^ )   ",
      "  (  w  )   ",
      '  (")_(")   '],
     "[bold yellow]*leans into your hand*[/]"),
    (["    ~ ~     ",
      "   /\\_/\\    ",
      "  ( - - )   ",
      "  (  w  )   ",
      ' ~(")_(")   '],
     "[bold magenta]*purrrr*[/]"),
    (["   ~ ~ ~    ",
      "  ~/\\_/\\    ",
      "  ( - - )   ",
      "  (  w  )   ",
      '  (")_(")~  '],
     "[bold magenta]*purrrrrr*[/]"),
    (["   ~ ~ ~    ",
      "   /\\_/\\~   ",
      "  ( - - )   ",
      "  (  w  )   ",
      ' ~(")_(")   '],
     "[bold magenta]*PURRRRRR*[/]"),
    (["    <3      ",
      "   /\\_/\\    ",
      "  ( ^ ^ )   ",
      "  (  w  )   ",
      '  (")_(")   '],
     "[bold red]*happy wiggle*[/]"),
    (["            ",
      "   /\\_/\\    ",
      "  ( O O )   ",
      "  (  w  )   ",
      '  (")_(")   '],
     "[dim]*settles back down*[/]"),
]

GENERIC_PET_FRAMES = [
    (["            ",
      "            ",
      "     o      ",
      "    /|\\     ",
      "    / \\     "],
     "[bold yellow]*perks up*[/]"),
    (["     ~      ",
      "            ",
      "     o      ",
      "    /|\\     ",
      "    / \\     "],
     "[bold magenta]*happy*[/]"),
    (["    ~ ~     ",
      "            ",
      "     o      ",
      "    /|\\     ",
      "    / \\     "],
     "[bold magenta]*so happy*[/]"),
    (["            ",
      "            ",
      "     o      ",
      "    /|\\     ",
      "    / \\     "],
     "[dim]*settles*[/]"),
]

PLAY_FRAMES = {
    "cat": CAT_PLAY_FRAMES,
}

PET_FRAMES = {
    "cat": CAT_PET_FRAMES,
}

ANIMATION_INTERVAL = 0.45



class BuddyCard(Static):
    """Renders the Rich buddy card with animation frame cycling."""

    frame = reactive(0)

    def __init__(self, buddy_state=None, **kwargs):
        super().__init__(**kwargs)
        self.buddy_state = buddy_state
        self.play_art_override = None

    def render(self):
        if not self.buddy_state or not HAS_RICH:
            from rich.text import Text
            return Text("  No buddy hatched yet. Run /buddy first.", style="dim")
        return render_buddy_card_rich(
            self.buddy_state,
            frame=self.frame,
            art_lines=self.play_art_override,
        )

    def watch_frame(self, _old, _new):
        self.refresh()


class StateFileHandler(FileSystemEventHandler):
    """Watchdog handler that notifies the Textual app on state file changes."""

    def __init__(self, app):
        self.app = app
        self._last_mtime = 0

    def on_modified(self, event):
        if not event.src_path.endswith(".buddy_state.json"):
            return
        time.sleep(0.05)
        try:
            mtime = os.path.getmtime(event.src_path)
        except OSError:
            return
        if mtime == self._last_mtime:
            return
        self._last_mtime = mtime
        self.app.call_from_thread(self.app.reload_state)


def _is_play_reaction(reaction):
    """Check if a reaction text matches one of the play scenarios."""
    if not reaction:
        return False
    for scenario in PLAY_SCENARIOS:
        template_prefix = scenario.split("{name}")[0] if "{name}" in scenario else scenario[:20]
        if template_prefix and template_prefix in reaction:
            return True
        template_suffix = scenario.split("{name}")[-1] if "{name}" in scenario else ""
        if template_suffix and template_suffix.strip() and template_suffix.strip() in reaction:
            return True
    return False


def _is_pet_reaction(reaction):
    """Check if a reaction text matches one of the pet reactions."""
    return reaction in REACTIONS_PET if reaction else False


class BuddyWatch(App):
    """Live buddy viewer with animation and reaction log."""

    CSS = """
    Screen {
        layout: vertical;
        background: $surface;
        overflow: hidden;
    }
    #card-container {
        height: auto;
        margin: 1 2;
        overflow: hidden;
    }
    #session-tabs {
        height: auto;
        margin: 0 2 1 2;
        overflow: hidden;
    }
    Tab {
        background: transparent;
        color: $text-muted;
        padding: 0 2;
    }
    Tab:hover {
        background: transparent;
        color: $text;
    }
    Tab.-active {
        background: transparent;
        color: $text;
    }
    Tab:focus {
        text-style: none;
    }
    Tabs {
        background: transparent;
    }
    TabPane {
        padding: 0;
    }
    SessionPane {
        height: auto;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
    ]

    def __init__(self):
        super().__init__()
        self.buddy_state = None
        self._observer = None
        self._prev_reaction = None
        self._anim_active = False
        self._anim_frame = 0
        self._anim_timer = None
        self._anim_frames = []
        self._idle_timer = None

    def compose(self) -> ComposeResult:
        yield Vertical(
            BuddyCard(id="buddy-card"),
            id="card-container",
        )
        with TabbedContent(id="session-tabs"):
            with TabPane("API", id="tab-api"):
                yield SessionPane(entrypoint="cli", show_context_bar=True, show_budget=True, id="pane-api")
            with TabPane("Desktop", id="tab-desktop"):
                yield SessionPane(entrypoint="claude-desktop", id="pane-desktop")
        yield Footer()

    def on_mount(self):
        self._load_initial_state()
        self._idle_timer = self.set_interval(1.5, self._cycle_frame)
        self._poll_timer = self.set_interval(1.0, self._poll_for_changes)
        self._last_poll_mtime = self._get_state_mtime()
        self._session_timer = self.set_interval(2.0, self._update_session_status)
        self._update_session_status()
        self._start_watcher()

    def _update_session_status(self):
        path = _find_latest_transcript()
        usage = _read_last_usage(path)
        tokens = _context_tokens(usage)
        stats = _scan_session_stats(path)
        desktop_path = _find_latest_transcript(entrypoint="claude-desktop")
        desktop_usage = _read_last_usage(desktop_path)
        desktop_tokens = _context_tokens(desktop_usage)
        desktop_stats = _scan_session_stats(desktop_path, cache=DESKTOP_SESSION_CACHE) if desktop_path else None
        try:
            api_pane = self.query_one("#pane-api", SessionPane)
            api_pane.update_stats(stats, tokens)
        except Exception:
            pass
        try:
            desktop_pane = self.query_one("#pane-desktop", SessionPane)
            desktop_pane.update_stats(desktop_stats, desktop_tokens)
        except Exception:
            pass

    def _load_initial_state(self):
        self.buddy_state = load_state()
        card = self.query_one("#buddy-card", BuddyCard)
        card.buddy_state = self.buddy_state
        card.refresh(layout=True)
        if self.buddy_state:
            self._prev_reaction = self.buddy_state.get("last_reaction")

    def reload_state(self):
        old_state = self.buddy_state
        try:
            self.buddy_state = load_state()
        except Exception:
            return
        card = self.query_one("#buddy-card", BuddyCard)
        card.buddy_state = self.buddy_state
        card.refresh(layout=True)

        if not self.buddy_state:
            return

        new_reaction = self.buddy_state.get("last_reaction")
        if new_reaction and new_reaction != self._prev_reaction:
            self._prev_reaction = new_reaction

            if _is_play_reaction(new_reaction):
                species = self.buddy_state.get("species", "")
                frames = PLAY_FRAMES.get(species, GENERIC_PLAY_FRAMES)
                self._start_animation(frames, "playing")
            elif _is_pet_reaction(new_reaction):
                species = self.buddy_state.get("species", "")
                frames = PET_FRAMES.get(species, GENERIC_PET_FRAMES)
                self._start_animation(frames, "being petted")

    def _start_animation(self, frames, label="playing"):
        if self._anim_active:
            return
        if not frames:
            return

        self._anim_active = True
        self._anim_frame = 0
        self._anim_frames = frames

        if self._idle_timer:
            self._idle_timer.stop()

        self._advance_anim_frame()
        self._anim_timer = self.set_interval(
            ANIMATION_INTERVAL, self._advance_anim_frame
        )

    def _advance_anim_frame(self):
        card = self.query_one("#buddy-card", BuddyCard)

        if self._anim_frame >= len(self._anim_frames):
            self._end_animation()
            return

        art, _caption = self._anim_frames[self._anim_frame]
        card.play_art_override = art
        card.frame = card.frame + 1

        self._anim_frame += 1

    def _end_animation(self):
        self._anim_active = False
        if self._anim_timer:
            self._anim_timer.stop()
            self._anim_timer = None

        card = self.query_one("#buddy-card", BuddyCard)
        card.play_art_override = None
        card.refresh(layout=True)

        self._idle_timer = self.set_interval(1.5, self._cycle_frame)

    def _cycle_frame(self):
        if not self.buddy_state or self._anim_active:
            return
        card = self.query_one("#buddy-card", BuddyCard)
        card.frame = (card.frame + 1) % 3

    def _get_state_mtime(self):
        try:
            return os.path.getmtime(BUDDY_FILE)
        except OSError:
            return 0

    def _poll_for_changes(self):
        mtime = self._get_state_mtime()
        if mtime and mtime != self._last_poll_mtime:
            self._last_poll_mtime = mtime
            self.reload_state()

    def _start_watcher(self):
        handler = StateFileHandler(self)
        self._observer = Observer()
        self._observer.schedule(handler, BUDDY_DIR, recursive=False)
        self._observer.daemon = True
        self._observer.start()

    def on_unmount(self):
        if self._observer:
            self._observer.stop()


def main():
    app = BuddyWatch()
    app.run()


if __name__ == "__main__":
    main()
