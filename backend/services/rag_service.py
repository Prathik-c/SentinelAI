import json
import ollama
from config import CHAT_MODEL

def fetch_relevant_context(db, question: str) -> str:
    """
    Fetches relevant health log data from SQLite
    and formats it as context for the LLM.
    """
    from models.tables import HealthLog

    # Always fetch recent logs as base context
    recent_logs = db.query(HealthLog).order_by(
        HealthLog.timestamp.desc()
    ).limit(20).all()

    # Also fetch high anomaly logs (high CPU or RAM)
    anomaly_logs = db.query(HealthLog).filter(
        HealthLog.cpu > 15
    ).order_by(HealthLog.timestamp.desc()).limit(10).all()

    # Format recent logs
    recent_context = "RECENT SYSTEM ACTIVITY (last 20 readings):\n"
    for log in recent_logs:
        processes = []
        if log.top_processes:
            procs = json.loads(log.top_processes)
            processes = [f"{p['name']}({p['cpu']}%)" for p in procs[:3]]

        recent_context += (
            f"- {log.timestamp}: CPU={log.cpu}%, "
            f"RAM={log.ram}%, "
            f"Idle={log.idle_seconds}s, "
            f"Top processes: {', '.join(processes)}\n"
        )

    # Format anomaly logs
    anomaly_context = "\nHIGH RESOURCE USAGE EVENTS:\n"
    if anomaly_logs:
        for log in anomaly_logs:
            anomaly_context += (
                f"- {log.timestamp}: CPU={log.cpu}%, RAM={log.ram}%\n"
            )
    else:
        anomaly_context += "- No significant resource spikes found\n"

    return recent_context + anomaly_context


def answer_question(db, question: str) -> str:
    """
    Takes a plain English question, fetches relevant data,
    and returns an LLM-generated answer grounded in real data.
    """
    context = fetch_relevant_context(db, question)

    prompt = f"""You are SentinelAI, an intelligent system monitor assistant.
Answer the user's question using ONLY the data provided below.
Do not guess or make up information not present in the data.
Be concise, specific, and helpful. Use actual numbers from the data.
If the data doesn't contain enough information to answer, say so honestly.

SYSTEM DATA:
{context}

USER QUESTION: {question}

Answer based only on the data above:"""

    response = ollama.chat(
        model=CHAT_MODEL,
        messages=[{"role": "user", "content": prompt}]
    )

    return response['message']['content']