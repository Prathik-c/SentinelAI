import ollama
from config import REPORT_MODEL

def explain_anomalies(anomalies: list, baseline: dict) -> str:
    if not anomalies:
        return "System is operating normally within your established baseline parameters."

    # Build a structured context for the LLM
    anomaly_summary = "\n".join([
        f"- [{a['severity'].upper()}] {a['type']}: {a['detail']} (at {a['timestamp']})"
        for a in anomalies
    ])

    prompt = f"""You are SentinelAI, an intelligent system health monitor.
    
Analyze the following anomalies detected on the user's system and explain them in clear, plain English.
Be specific, helpful, and concise. Mention what is normal for this user and why these readings are unusual.
Do not use technical jargon. End with a simple recommended action.

USER'S NORMAL BASELINE:
- Average CPU usage: {baseline['cpu_mean']}%
- Average RAM usage: {baseline['ram_mean']}%
- CPU alert threshold: {baseline['cpu_threshold']}%
- RAM alert threshold: {baseline['ram_threshold']}%
- Known processes learned from {baseline['baseline_samples']} observations

ANOMALIES DETECTED:
{anomaly_summary}

Provide a clear explanation in 3-4 sentences maximum."""

    response = ollama.chat(
        model=REPORT_MODEL,
        messages=[{"role": "user", "content": prompt}]
    )

    return response['message']['content']