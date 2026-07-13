"""
SentinelAI — Intent Classifier

A fast, dependency-free keyword classifier that routes user questions to the
correct RAG data retrieval strategy before any DB query or LLM call is made.

Why keyword-based (not another LLM call)?
- Zero latency: classification is a dictionary lookup.
- Deterministic: the same question always maps to the same intent.
- No circular dependency: we can't use the LLM to route LLM queries.

Intent → DB strategy mapping:
  RAM_SPIKE      → HealthLog WHERE ram > threshold ORDER BY timestamp DESC
  CPU_QUERY      → HealthLog top_processes, recent 24h
  DISK_QUERY     → HealthLog disk column, recent 24h
  TIME_QUERY     → HealthLog WHERE timestamp BETWEEN parsed_start AND parsed_end
  PROCESS_QUERY  → HealthLog WHERE top_processes LIKE '%<name>%'
  INCIDENT_QUERY → Incident table, recent records
  HEALTH_CHECK   → Latest 5 logs + baseline stats
  GENERAL        → Latest 10 logs + recent incidents
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Tuple


# ── Intent Enum ───────────────────────────────────────────────────────────────

class Intent(str, Enum):
    # Fast-path intents — these NEVER call the LLM
    GREETING       = "GREETING"
    HELP           = "HELP"
    SIMPLE_STATUS  = "SIMPLE_STATUS"   # pure Python answer from live metrics
    # RAG intents — fetch DB context, then call LLM
    RAM_SPIKE      = "RAM_SPIKE"
    CPU_QUERY      = "CPU_QUERY"
    DISK_QUERY     = "DISK_QUERY"
    TIME_QUERY     = "TIME_QUERY"
    PROCESS_QUERY  = "PROCESS_QUERY"
    INCIDENT_QUERY = "INCIDENT_QUERY"
    HEALTH_CHECK   = "HEALTH_CHECK"
    GENERAL        = "GENERAL"


# ── Keyword maps ──────────────────────────────────────────────────────────────

# Each tuple: (intent, set_of_keywords_or_phrases)
# Evaluated in order; first match wins.
_KEYWORD_RULES: list[Tuple[Intent, list[str]]] = [
    # ── Fast-path rules (evaluated first — no DB, no LLM) ─────────────────
    (Intent.GREETING, [
        "hello", "hi", "hey", "good morning", "good evening", "good afternoon",
        "good night", "greetings", "howdy", "sup", "what's up", "whats up",
        "thanks", "thank you", "cheers", "bye", "goodbye", "see you",
        "who are you", "what are you",
    ]),
    (Intent.HELP, [
        "help", "what can you do", "what can i ask", "commands",
        "capabilities", "features", "guide", "tutorial", "how do i",
        "how to use", "what do you know",
    ]),
    (Intent.SIMPLE_STATUS, [
        "current cpu", "current ram", "current memory", "current disk",
        "cpu now", "ram now", "disk now",
        "what is cpu", "what is ram", "what is disk",
        "cpu right now", "ram right now", "disk right now",
        "live cpu", "live ram", "live metrics", "live stats",
    ]),
    (Intent.INCIDENT_QUERY, [
        "anomal", "incident", "alert", "warning", "threat", "suspicious",
        "flag", "detect", "unauthorised", "malware", "attack",
        "unusual", "strange", "weird", "odd behav",
    ]),
    (Intent.RAM_SPIKE, [
        "ram", "memory", "mem spike", "memory spike", "memory high",
        "memory usage", "out of memory", "ram usage", "ram spike",
    ]),
    (Intent.CPU_QUERY, [
        "cpu", "processor", "top process", "most cpu", "highest cpu",
        "cpu usage", "cpu spike", "cpu high", "cpu intensive",
    ]),
    (Intent.DISK_QUERY, [
        "disk", "storage", "drive", "space", "c:", "disk usage",
        "disk full", "disk high", "ssd", "hdd",
    ]),
    (Intent.HEALTH_CHECK, [
        "health", "status", "normal", "ok", "fine", "stable",
        "overall", "summary", "how is", "how's my", "is my system",
        "system ok", "everything ok", "general", "overview",
    ]),
    (Intent.PROCESS_QUERY, [
        "process", "program", "application", " service",
        "running", "what is running", "which process", ".exe",
    ]),
    (Intent.TIME_QUERY, [
        "yesterday", "last night", "this morning",
        "hours ago", "days ago", "week ago", "last week", "last month",
        "what happened", "what was running",
        "at 1 ", "at 2 ", "at 3 ", "at 4 ", "at 5 ", "at 6 ",
        "at 7 ", "at 8 ", "at 9 ", "at 10", "at 11", "at 12",
        " pm", " am ",
    ]),
]


# ── Time expression patterns ──────────────────────────────────────────────────

_TIME_PATTERNS = [
    # "yesterday at 3 PM", "yesterday at 15:00"
    (
        re.compile(r"yesterday\s+at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", re.I),
        "yesterday_at",
    ),
    # "X hours ago"
    (re.compile(r"(\d+)\s+hours?\s+ago", re.I), "hours_ago"),
    # "X days ago"
    (re.compile(r"(\d+)\s+days?\s+ago",  re.I), "days_ago"),
    # "at 3 PM", "at 15:30"
    (re.compile(r"\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", re.I), "at_time"),
    # "last night" → 21:00–03:00 yesterday
    (re.compile(r"last\s+night", re.I), "last_night"),
    # "this morning"
    (re.compile(r"this\s+morning", re.I), "this_morning"),
    # "today"
    (re.compile(r"\btoday\b", re.I), "today"),
    # "yesterday" (alone)
    (re.compile(r"\byesterday\b(?!.*\bat\b)", re.I), "yesterday"),
]


# Pre-compiled word-boundary patterns for fast-path intents.
# Short keywords like "hi", "hey", "sup" would otherwise match inside
# "history", "they", "support" with naive substring matching.
_FAST_PATH_INTENTS = {Intent.GREETING, Intent.HELP, Intent.SIMPLE_STATUS}

_WORD_BOUNDARY_CACHE: dict[str, re.Pattern] = {}

def _word_match(keyword: str, text: str) -> bool:
    """Returns True if `keyword` appears as a whole word/phrase in `text`."""
    pat = _WORD_BOUNDARY_CACHE.get(keyword)
    if pat is None:
        pat = re.compile(r"\b" + re.escape(keyword) + r"\b", re.I)
        _WORD_BOUNDARY_CACHE[keyword] = pat
    return pat.search(text) is not None


def classify(question: str) -> Intent:
    """
    Returns the most specific Intent for the given user question.
    Falls through to GENERAL if no keyword matches.

    Fast-path intents (GREETING, HELP, SIMPLE_STATUS) use word-boundary
    matching to avoid false positives on substrings (e.g. "hi" in "history").
    RAG intents use fast substring matching (safe because their keywords
    are long enough to be unambiguous).
    """
    q = question.lower().strip()

    # Very short messages (≤ 4 chars) are almost always greetings
    if len(q) <= 4 and q in {"hi", "hey", "sup", "yo", "hii", "hiii", "thx", "bye"}:
        return Intent.GREETING

    for intent, keywords in _KEYWORD_RULES:
        if intent in _FAST_PATH_INTENTS:
            # Word-boundary matching — "hi" won't match inside "history"
            if any(_word_match(kw, q) for kw in keywords):
                return intent
        else:
            # Substring matching — fast and safe for longer keywords
            if any(kw in q for kw in keywords):
                return intent

    return Intent.GENERAL


def extract_time_window(
    question: str,
    window_minutes: int = 30,
) -> Optional[Tuple[datetime, datetime]]:
    """
    Attempts to parse a time window from the user's question.
    Returns (start_dt, end_dt) in UTC if a time expression is found,
    otherwise returns None.

    Args:
        question: The raw user question string.
        window_minutes: How many minutes either side of the mentioned time
                        to include in the DB query window.
    """
    q = question.lower()
    now = datetime.utcnow()

    for pattern, label in _TIME_PATTERNS:
        m = pattern.search(q)
        if not m:
            continue

        try:
            if label == "yesterday_at":
                hour = int(m.group(1))
                minute = int(m.group(2)) if m.group(2) else 0
                ampm = (m.group(3) or "").lower()
                if ampm == "pm" and hour < 12:
                    hour += 12
                elif ampm == "am" and hour == 12:
                    hour = 0
                anchor = (now - timedelta(days=1)).replace(
                    hour=hour, minute=minute, second=0, microsecond=0
                )

            elif label == "hours_ago":
                hours = int(m.group(1))
                anchor = now - timedelta(hours=hours)

            elif label == "days_ago":
                days = int(m.group(1))
                anchor = now - timedelta(days=days)

            elif label == "at_time":
                hour = int(m.group(1))
                minute = int(m.group(2)) if m.group(2) else 0
                ampm = (m.group(3) or "").lower()
                if ampm == "pm" and hour < 12:
                    hour += 12
                elif ampm == "am" and hour == 12:
                    hour = 0
                anchor = now.replace(
                    hour=hour, minute=minute, second=0, microsecond=0
                )
                # If the time is in the future (e.g. "at 11 PM" and it's noon),
                # assume they mean yesterday.
                if anchor > now:
                    anchor -= timedelta(days=1)

            elif label == "last_night":
                anchor = (now - timedelta(days=1)).replace(
                    hour=21, minute=0, second=0, microsecond=0
                )
                # Return a 6-hour window for "last night"
                return anchor, anchor + timedelta(hours=6)

            elif label == "this_morning":
                anchor = now.replace(
                    hour=6, minute=0, second=0, microsecond=0
                )
                # Return from 6 AM to noon
                return anchor, anchor + timedelta(hours=6)

            elif label == "today":
                anchor = now.replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                # Return from midnight today until now
                return anchor, now

            elif label == "yesterday":
                anchor = (now - timedelta(days=1)).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                # Return from midnight yesterday until midnight today
                return anchor, anchor + timedelta(days=1)

            else:
                continue

            return (
                anchor - timedelta(minutes=window_minutes),
                anchor + timedelta(minutes=window_minutes),
            )

        except (ValueError, IndexError, AttributeError):
            continue

    return None


def extract_process_name(question: str) -> Optional[str]:
    """
    Attempts to extract a process name from the question.
    Looks for patterns like "what is chrome.exe doing?" or "tell me about python.exe"
    Returns the extracted name (lowercase) or None.
    """
    # Match explicit .exe names
    m = re.search(r"([\w\-]+\.exe)", question, re.I)
    if m:
        return m.group(1).lower()

    # Match "about <word>" or "is <word> doing"
    m = re.search(r"(?:about|is|what is)\s+([\w\-]+)\s+(?:doing|running|using)", question, re.I)
    if m:
        return m.group(1).lower()

    return None
