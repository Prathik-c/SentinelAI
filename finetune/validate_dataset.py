"""
validate_dataset.py

Validates a JSONL fine-tuning dataset (e.g. finetune/training_data.jsonl)
and reports data-quality issues before training.

Checks performed:
    - Total number of examples
    - Invalid / malformed JSON lines
    - Empty or missing required fields (instruction, input, output)
    - Duplicate instructions
    - Exact duplicate outputs
    - Average lengths (instruction, input, output) in words/characters
    - Topic distribution (keyword-based, across known dataset categories)
    - Suspiciously short or overly long answers

Usage:
    python validate_dataset.py
    python validate_dataset.py path/to/other_dataset.jsonl

Only Python standard libraries are used: json, re, statistics,
collections, pathlib, sys.
"""

import json
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Script's own directory = finetune/
SCRIPT_DIR = Path(__file__).resolve().parent

# Default file to validate (finetune/training_data.jsonl)
DEFAULT_TARGET_FILE = SCRIPT_DIR / "training_data.jsonl"

# Fields that every record must contain (with non-empty values)
REQUIRED_FIELDS = ("instruction", "input", "output")

# Thresholds for flagging suspicious "output" answer lengths (in characters)
SHORT_ANSWER_CHAR_THRESHOLD = 20      # answers shorter than this are "too short"
LONG_ANSWER_CHAR_THRESHOLD = 4000     # answers longer than this are "too long"

# How many example issues to print per category (avoid flooding the terminal)
MAX_EXAMPLES_TO_SHOW = 5

# Keyword map used to bucket records into topics for distribution reporting.
# This mirrors the original source datasets used during merging, but works
# purely on record content, so it works on any merged/shuffled file.
TOPIC_KEYWORDS = {
    "windows_processes": [
        "process", "pid", "task manager", "cpu usage",
        "thread", "process tree", "parent process"
    ],

    "windows_documentation": [
        "microsoft docs", "documentation",
        "windows api", "registry key",
        "windows internals", "win32"
    ],

    "sysmon": [
        "sysmon", "event id", "eventid",
        "microsoft-windows-sysmon",
        "sysmon event"
    ],

    "sysinternals": [
        "sysinternals", "procmon",
        "procexp", "psexec",
        "autoruns", "tcpview",
        "process explorer",
        "process monitor"
    ],

    "mitre_attack": [
        "mitre", "att&ck",
        "attack technique", "tactic",
        "adversary", "tactic id",
        "technique", "persistence",
        "credential access"
    ],

    "etw": [
        "etw",
        "event tracing",
        "event tracing for windows",
        "provider",
        "consumer",
        "controller",
        "trace session",
        "trace provider",
        "trace consumer",
        "trace logging",
        "event provider",
        "event consumer",
        "event tracing api",
        "etl file",
        "windows performance recorder",
        "windows performance analyzer",
        "wpr",
        "wpa"
    ],

    "other": [],
}


def load_lines(file_path: Path):
    """
    Read raw lines from the target file.
    Raises FileNotFoundError if the file does not exist.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Dataset file not found: {file_path}")

    with file_path.open("r", encoding="utf-8") as f:
        return f.readlines()


def classify_topic(record: dict) -> str:
    """
    Assign a record to a topic bucket based on simple keyword matching
    against its instruction + input + output text (case-insensitive).
    Falls back to 'other' if nothing matches.
    """
    combined_text = " ".join(
        str(record.get(field, "")) for field in ("instruction", "input", "output")
    ).lower()

    for topic, keywords in TOPIC_KEYWORDS.items():
        if topic == "other":
            continue
        if any(keyword in combined_text for keyword in keywords):
            return topic

    return "other"


def validate_dataset(file_path: Path) -> dict:
    """
    Run all validation checks against the dataset file and return a
    results dictionary containing every metric needed for the report.
    """
    raw_lines = load_lines(file_path)

    results = {
        "total_lines": 0,
        "invalid_json_lines": [],       # list of (line_number, error_message)
        "empty_field_records": [],      # list of (line_number, missing_field_names)
        "valid_records": [],            # list of (line_number, record)
        "instruction_counter": Counter(),
        "output_counter": Counter(),
        "topic_counter": Counter(),
        "instruction_lengths": [],      # word counts
        "input_lengths": [],            # word counts
        "output_lengths_words": [],     # word counts
        "output_lengths_chars": [],     # character counts (for short/long flags)
        "short_answers": [],            # list of (line_number, char_count, instruction_preview)
        "long_answers": [],             # list of (line_number, char_count, instruction_preview)
    }

    # --- Step 1: Parse each line, validating JSON and required fields ---
    for line_num, raw_line in enumerate(raw_lines, start=1):
        line = raw_line.strip()

        # Skip blank lines without counting them as "invalid"
        if not line:
            continue

        results["total_lines"] += 1

        # Validate JSON parsing
        try:
            record = json.loads(line)
        except json.JSONDecodeError as e:
            results["invalid_json_lines"].append((line_num, str(e)))
            continue

        if not isinstance(record, dict):
            results["invalid_json_lines"].append((line_num, "Top-level JSON is not an object"))
            continue

        # Validate required fields are present and non-empty (after stripping)
        missing_fields = []
        for field in REQUIRED_FIELDS:
            value = record.get(field, None)
            if value is None or not isinstance(value, str) or value.strip() == "":
                missing_fields.append(field)

        if missing_fields:
            results["empty_field_records"].append((line_num, missing_fields))
            continue

        # Record is structurally valid; keep it for further analysis
        results["valid_records"].append((line_num, record))

    # --- Step 2: Analyze valid records ---
    for line_num, record in results["valid_records"]:
        instruction = record["instruction"].strip()
        input_text = record["input"].strip()
        output_text = record["output"].strip()

        # Duplicate tracking
        results["instruction_counter"][instruction] += 1
        results["output_counter"][output_text] += 1

        # Length tracking (word counts for general stats)
        results["instruction_lengths"].append(len(instruction.split()))
        results["input_lengths"].append(len(input_text.split()))
        results["output_lengths_words"].append(len(output_text.split()))
        results["output_lengths_chars"].append(len(output_text))

        # Topic classification
        topic = classify_topic(record)
        results["topic_counter"][topic] += 1

        # Suspiciously short / long answers
        char_len = len(output_text)
        preview = instruction[:80] + ("..." if len(instruction) > 80 else "")

        if char_len < SHORT_ANSWER_CHAR_THRESHOLD:
            results["short_answers"].append((line_num, char_len, preview))
        elif char_len > LONG_ANSWER_CHAR_THRESHOLD:
            results["long_answers"].append((line_num, char_len, preview))

    return results


def safe_mean(values):
    """Return the mean of a list, or 0 if the list is empty (avoids ZeroDivisionError)."""
    return round(statistics.mean(values), 2) if values else 0


def print_report(file_path: Path, results: dict) -> None:
    """
    Print a detailed, human-readable validation report to stdout.
    """
    valid_count = len(results["valid_records"])
    duplicate_instructions = {
        text: count for text, count in results["instruction_counter"].items() if count > 1
    }
    duplicate_outputs = {
        text: count for text, count in results["output_counter"].items() if count > 1
    }

    print("=" * 60)
    print("Dataset Validation Report")
    print("=" * 60)
    print(f"File: {file_path}")
    print("-" * 60)

    # --- Overall counts ---
    print("\n[1] Record Counts")
    print(f"  Total non-blank lines scanned : {results['total_lines']}")
    print(f"  Valid records                 : {valid_count}")
    print(f"  Invalid JSON lines            : {len(results['invalid_json_lines'])}")
    print(f"  Records with empty/missing fields : {len(results['empty_field_records'])}")

    # --- Invalid JSON details ---
    print("\n[2] Invalid JSON Lines")
    if results["invalid_json_lines"]:
        for line_num, err in results["invalid_json_lines"][:MAX_EXAMPLES_TO_SHOW]:
            print(f"  Line {line_num}: {err}")
        remaining = len(results["invalid_json_lines"]) - MAX_EXAMPLES_TO_SHOW
        if remaining > 0:
            print(f"  ... and {remaining} more")
    else:
        print("  None found.")

    # --- Empty field details ---
    print("\n[3] Records with Empty/Missing Fields")
    if results["empty_field_records"]:
        for line_num, fields in results["empty_field_records"][:MAX_EXAMPLES_TO_SHOW]:
            print(f"  Line {line_num}: missing/empty -> {', '.join(fields)}")
        remaining = len(results["empty_field_records"]) - MAX_EXAMPLES_TO_SHOW
        if remaining > 0:
            print(f"  ... and {remaining} more")
    else:
        print("  None found.")

    # --- Duplicate instructions ---
    print("\n[4] Duplicate Instructions")
    print(f"  Unique instructions with duplicates: {len(duplicate_instructions)}")
    if duplicate_instructions:
        shown = 0
        for text, count in duplicate_instructions.items():
            if shown >= MAX_EXAMPLES_TO_SHOW:
                break
            preview = text[:80] + ("..." if len(text) > 80 else "")
            print(f"  x{count}: {preview}")
            shown += 1
        remaining = len(duplicate_instructions) - MAX_EXAMPLES_TO_SHOW
        if remaining > 0:
            print(f"  ... and {remaining} more")

    # --- Exact duplicate outputs ---
    print("\n[5] Exact Duplicate Outputs")
    print(f"  Unique outputs with duplicates: {len(duplicate_outputs)}")
    if duplicate_outputs:
        shown = 0
        for text, count in duplicate_outputs.items():
            if shown >= MAX_EXAMPLES_TO_SHOW:
                break
            preview = text[:80] + ("..." if len(text) > 80 else "")
            print(f"  x{count}: {preview}")
            shown += 1
        remaining = len(duplicate_outputs) - MAX_EXAMPLES_TO_SHOW
        if remaining > 0:
            print(f"  ... and {remaining} more")

    # --- Average lengths ---
    print("\n[6] Average Lengths (valid records only)")
    print(f"  Instruction avg word count : {safe_mean(results['instruction_lengths'])}")
    print(f"  Input avg word count       : {safe_mean(results['input_lengths'])}")
    print(f"  Output avg word count      : {safe_mean(results['output_lengths_words'])}")
    print(f"  Output avg character count : {safe_mean(results['output_lengths_chars'])}")

    # --- Topic distribution ---
    print("\n[7] Topic Distribution")
    if valid_count > 0:
        for topic, count in results["topic_counter"].most_common():
            pct = round((count / valid_count) * 100, 1)
            print(f"  {topic:25s}: {count:5d} ({pct}%)")
    else:
        print("  No valid records to classify.")

    # --- Suspiciously short answers ---
    print(f"\n[8] Suspiciously Short Answers (< {SHORT_ANSWER_CHAR_THRESHOLD} chars)")
    print(f"  Count: {len(results['short_answers'])}")
    for line_num, char_len, preview in results["short_answers"][:MAX_EXAMPLES_TO_SHOW]:
        print(f"  Line {line_num} ({char_len} chars) - instruction: {preview}")
    remaining = len(results["short_answers"]) - MAX_EXAMPLES_TO_SHOW
    if remaining > 0:
        print(f"  ... and {remaining} more")

    # --- Overly long answers ---
    print(f"\n[9] Overly Long Answers (> {LONG_ANSWER_CHAR_THRESHOLD} chars)")
    print(f"  Count: {len(results['long_answers'])}")
    for line_num, char_len, preview in results["long_answers"][:MAX_EXAMPLES_TO_SHOW]:
        print(f"  Line {line_num} ({char_len} chars) - instruction: {preview}")
    remaining = len(results["long_answers"]) - MAX_EXAMPLES_TO_SHOW
    if remaining > 0:
        print(f"  ... and {remaining} more")

    print("\n" + "=" * 60)
    print("Validation Complete")
    print("=" * 60)


def main():
    # Allow an optional command-line argument to validate a different file,
    # otherwise default to finetune/training_data.jsonl
    if len(sys.argv) > 1:
        target_file = Path(sys.argv[1]).resolve()
    else:
        target_file = DEFAULT_TARGET_FILE

    try:
        results = validate_dataset(target_file)
    except FileNotFoundError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)
    except OSError as e:
        print(f"[ERROR] Could not read file {target_file}: {e}")
        sys.exit(1)

    print_report(target_file, results)


if __name__ == "__main__":
    main()