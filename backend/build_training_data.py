"""
SentinelAI - Training Data Builder
Converts sentinelai.db (incidents, health_logs, chat_history) into
instruction/output JSONL pairs for LoRA fine-tuning.

Usage:
    python build_training_data.py --db sentinelai.db --out training_data.jsonl
"""

import sqlite3
import json
import argparse
import statistics
import random


def load_rows(conn, query):
    cursor = conn.cursor()
    cursor.execute(query)
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def build_chat_pairs(conn):
    """chat_history.question/answer -> direct instruction/output pairs"""
    rows = load_rows(conn, "SELECT question, answer FROM chat_history WHERE question IS NOT NULL AND answer IS NOT NULL")
    pairs = []
    for r in rows:
        q = (r["question"] or "").strip()
        a = (r["answer"] or "").strip()
        if len(q) < 3 or len(a) < 3:
            continue
        pairs.append({
            "instruction": q,
            "output": a,
            "source": "chat_history"
        })
    return pairs


def build_incident_pairs(conn):
    """
    incidents: description + snapshot -> report
    report is assumed to be the Phase 4c LLM-generated explanation.
    """
    rows = load_rows(conn, """
        SELECT type, severity, description, snapshot, report
        FROM incidents
        WHERE report IS NOT NULL AND report != ''
    """)
    pairs = []
    for r in rows:
        snapshot = r["snapshot"] or ""
        desc = r["description"] or ""
        instruction = (
            f"An anomaly was detected on this system.\n"
            f"Type: {r['type']}\n"
            f"Severity: {r['severity']}\n"
            f"Description: {desc}\n"
            f"System snapshot: {snapshot}\n"
            f"Explain what this means and whether the user should be concerned."
        )
        output = (r["report"] or "").strip()
        if len(output) < 10:
            continue
        pairs.append({
            "instruction": instruction,
            "output": output,
            "source": "incidents"
        })
    return pairs


def build_baseline_normal_pairs(conn, sample_size=60):
    """
    health_logs: sample 'normal' looking rows (no wild deviation from mean)
    and generate simple 'is this normal?' pairs so the model learns
    restraint, not just anomaly-flagging.
    """
    rows = load_rows(conn, "SELECT cpu, ram, disk, top_processes, idle_seconds FROM health_logs")
    if not rows:
        return []

    cpu_vals = [r["cpu"] for r in rows if r["cpu"] is not None]
    ram_vals = [r["ram"] for r in rows if r["ram"] is not None]
    if not cpu_vals or not ram_vals:
        return []

    cpu_mean = statistics.mean(cpu_vals)
    ram_mean = statistics.mean(ram_vals)

    normal_rows = [
        r for r in rows
        if r["cpu"] is not None and r["ram"] is not None
        and r["cpu"] < cpu_mean * 1.5
        and r["ram"] < ram_mean * 1.2
    ]

    sample = random.sample(normal_rows, min(sample_size, len(normal_rows)))

    pairs = []
    for r in sample:
        instruction = (
            f"Current system state -> CPU: {r['cpu']:.1f}%, RAM: {r['ram']:.1f}%, "
            f"Disk: {r['disk']:.1f}%, Idle: {r['idle_seconds']:.0f}s, "
            f"Top processes: {r['top_processes']}. "
            f"Is this normal for this system's baseline "
            f"(baseline CPU ~{cpu_mean:.1f}%, RAM ~{ram_mean:.1f}%)?"
        )
        output = (
            f"Yes, this is within normal range. CPU at {r['cpu']:.1f}% and RAM at {r['ram']:.1f}% "
            f"are close to your typical baseline (CPU ~{cpu_mean:.1f}%, RAM ~{ram_mean:.1f}%). "
            f"No anomaly detected."
        )
        pairs.append({
            "instruction": instruction,
            "output": output,
            "source": "health_logs_normal"
        })
    return pairs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="sentinelai.db")
    parser.add_argument("--out", default="training_data.jsonl")
    parser.add_argument("--normal-sample-size", type=int, default=60)
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)

    chat_pairs = build_chat_pairs(conn)
    incident_pairs = build_incident_pairs(conn)
    normal_pairs = build_baseline_normal_pairs(conn, args.normal_sample_size)

    all_pairs = chat_pairs + incident_pairs + normal_pairs
    random.shuffle(all_pairs)

    with open(args.out, "w", encoding="utf-8") as f:
        for p in all_pairs:
            f.write(json.dumps({"instruction": p["instruction"], "output": p["output"]}, ensure_ascii=False) + "\n")

    print(f"chat_history pairs:   {len(chat_pairs)}")
    print(f"incident pairs:       {len(incident_pairs)}")
    print(f"normal-state pairs:   {len(normal_pairs)}")
    print(f"TOTAL:                {len(all_pairs)}")
    print(f"Written to: {args.out}")

    conn.close()


if __name__ == "__main__":
    main()