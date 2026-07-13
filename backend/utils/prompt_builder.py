"""
SentinelAI — Prompt Builder

All prompts in one place for easy tuning. Keeps LLM calls in services thin.

Design principles:
  - Tight prompts: every prompt has an explicit output format constraint.
  - Role + task: every prompt starts with a clear system role.
  - No filler: no "please", "thank you", or boilerplate text.
  - Max 3-4 sentence outputs requested to keep responses concise.
  - Intent-aware: RAG prompt adapts tone/focus based on classified intent.
"""
from __future__ import annotations

from typing import Any, Dict, List


# ── Incident Explanation Prompt ───────────────────────────────────────────────

def build_incident_prompt(incident: Dict[str, Any]) -> str:
    """
    Builds a tight prompt for explaining a single structured incident.
    Input is pre-structured by Python — no guessing needed by LLM.
    Expected output: 2–3 sentences, plain English, actionable.
    """
    reasons_str = "\n".join(
        f"  - {r}" for r in (incident.get("reasons") or [])
    )
    process_line = (
        f"Involved process: {incident['process_name']}\n"
        if incident.get("process_name") else ""
    )
    cpu_line = (
        f"CPU at detection: {incident.get('cpu', 'N/A')}%\n"
        if incident.get("cpu") is not None else ""
    )
    ram_line = (
        f"RAM at detection: {incident.get('ram', 'N/A')}%\n"
        if incident.get("ram") is not None else ""
    )

    # Load snapshot safely
    snapshot = incident.get("snapshot") or {}
    snapshot_str = ""
    if snapshot:
        snapshot_str = f"Baseline context: {snapshot}\n"

    return f"""You are SentinelAI, a local AI security monitor.
A behavioural anomaly was detected on this system by our Python engine. Explain it to the user.

ANOMALY DETAILS:
Type: {incident.get('incident_type', 'unknown')}
Severity: {incident.get('severity', 'medium').upper()}
Risk score: {incident.get('risk_score', 0)}/100
{process_line}{cpu_line}{ram_line}{snapshot_str}
Detection reasons:
{reasons_str}

Instructions:
- Write exactly 2–3 sentences. No bullet points.
- Explain why this was detected, why it is unusual based on the baseline context, and possible causes.
- End with one clear recommended action.
- Use plain English. No technical jargon.
- Do NOT perform detection yourself; explain the detection already done by the Python engine.
- Do NOT invent data not shown above.

Explanation:"""


# ── Legacy Anomaly Prompt (backwards compat) ──────────────────────────────────

def build_anomaly_prompt(anomalies: List[Dict], baseline: Dict) -> str:
    """
    Legacy prompt format for the old explain_anomalies() interface.
    Still used when the full incident list needs a single explanation.
    """
    anomaly_summary = "\n".join([
        f"  - [{a.get('severity', 'medium').upper()}] "
        f"{a.get('type', 'anomaly')}: {a.get('detail', a.get('description', ''))}"
        f" (at {a.get('timestamp', 'unknown')})"
        for a in anomalies
    ])

    return f"""You are SentinelAI. Analyse these system anomalies and explain them briefly.

BASELINE:
- Average CPU: {baseline.get('cpu_mean', '?')}%
- Average RAM: {baseline.get('ram_mean', '?')}%
- CPU alert threshold: {baseline.get('cpu_threshold', '?')}%
- RAM alert threshold: {baseline.get('ram_threshold', '?')}%
- Samples: {baseline.get('baseline_samples', '?')}

ANOMALIES:
{anomaly_summary}

Write 2–3 sentences. Plain English. End with one recommended action. No jargon.

Explanation:"""


# ── RAG Chat Prompt ───────────────────────────────────────────────────────────

def build_rag_prompt(context: str, question: str, intent: str = "") -> str:
    """
    Builds a prompt for answering user questions grounded in retrieved data.
    Intent is used to tune the tone and focus of the answer.
    """
    intent_instruction = _intent_instruction(intent)

    return f"""You are SentinelAI, an intelligent system monitor assistant.
Answer the user's question using ONLY the data provided. Do not guess or invent.
Be concise (max 4 sentences). Use real numbers from the data.
If the data is insufficient, say so honestly.
{intent_instruction}

SYSTEM DATA:
{context}

USER QUESTION: {question}

Answer:"""


def _intent_instruction(intent: str) -> str:
    """Returns a short intent-specific instruction to focus the LLM."""
    instructions = {
        "RAM_SPIKE":      "Focus on RAM usage values and when they peaked.",
        "CPU_QUERY":      "Focus on CPU percentages and process names.",
        "DISK_QUERY":     "Focus on disk usage percentages.",
        "TIME_QUERY":     "Focus on data from the specific time period mentioned.",
        "PROCESS_QUERY":  "Focus on the specific process name, its CPU and RAM usage.",
        "INCIDENT_QUERY": "Focus on detected anomalies, their type, and severity.",
        "HEALTH_CHECK":   "Give an overall health summary comparing current vs baseline.",
        "GENERAL":        "",
    }
    return instructions.get(intent, "")


# ── Weekly Report Prompt ──────────────────────────────────────────────────────

def build_weekly_report_prompt(stats: Dict[str, Any]) -> str:
    """
    Builds a prompt for the AI narrative section of the weekly report.
    All quantitative analysis is pre-computed by Python — LLM only narrates.
    """
    anomaly_count  = stats.get("total_anomalies", 0)
    health_score   = stats.get("health_score", 0)
    risk_score     = stats.get("risk_score", 0)
    avg_cpu        = stats.get("avg_cpu", 0)
    avg_ram        = stats.get("avg_ram", 0)
    top_proc       = stats.get("most_frequent_process", "unknown")
    recommendations = stats.get("recommendations", [])
    recs_str = "\n".join(f"  - {r}" for r in recommendations[:5])

    return f"""You are SentinelAI generating a weekly security report narrative.

WEEKLY STATISTICS:
- Health score: {health_score}/100
- Risk score: {risk_score}/100
- Average CPU: {avg_cpu:.1f}%
- Average RAM: {avg_ram:.1f}%
- Total anomalies detected: {anomaly_count}
- Most frequent process: {top_proc}
- Recommendations identified: {len(recommendations)}
{recs_str}

Write a 2–3 paragraph executive summary of this week's system health and security posture.
Be factual, concise, and professional. Reference the actual numbers.
End with a brief "What to watch next week" section.

Report:"""
