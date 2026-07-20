"""
merge_dataset.py

Merges multiple JSONL datasets (used for LLM fine-tuning) into a single
deduplicated, shuffled training_data.jsonl file.

Usage:
    python merge_dataset.py

Only Python standard libraries are used: os, json, random, pathlib.
"""

import os
import json
import random
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Script's own directory = finetune/
SCRIPT_DIR = Path(__file__).resolve().parent

# Base directory where the source JSONL datasets live (finetune/dataset/)
DATASET_DIR = SCRIPT_DIR / "dataset"

# List of source files to merge, in the order they should be processed
SOURCE_FILES = [
    "windows_processes.jsonl",
    "windows_documentation.jsonl",
    "sysmon.jsonl",
    "sysinternals.jsonl",
    "mitre_attack.jsonl",
    "ETW.jsonl",
]

# Fields that every record must contain (with non-empty values)
REQUIRED_FIELDS = ("instruction", "input", "output")

# Output file path (finetune/training_data.jsonl)
OUTPUT_DIR = SCRIPT_DIR
OUTPUT_FILE = OUTPUT_DIR / "training_data.jsonl"

# Fixed seed for reproducible shuffling
RANDOM_SEED = 42


def load_and_validate_file(file_path: Path, stats: dict) -> list:
    """
    Read a single JSONL file, validate each line, and return a list of
    valid record dicts (as parsed from JSON, unmodified).

    Any malformed JSON lines or records missing required fields are
    skipped, and counters in `stats` are updated accordingly.
    """
    records = []

    # Handle missing files gracefully instead of crashing the whole merge
    if not file_path.exists():
        print(f"[WARNING] File not found, skipping: {file_path}")
        stats["per_file_counts"][file_path.name] = 0
        return records

    try:
        with file_path.open("r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError as e:
        print(f"[WARNING] Could not read file {file_path}: {e}")
        stats["per_file_counts"][file_path.name] = 0
        return records

    valid_count = 0

    for line_num, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()

        # Skip empty lines silently (not malformed, just blank)
        if not line:
            continue

        # --- Step 1: Validate JSON parsing ---
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            stats["malformed_skipped"] += 1
            continue

        # Records must be JSON objects (dicts) to have the required fields
        if not isinstance(record, dict):
            stats["malformed_skipped"] += 1
            continue

        # --- Step 2: Validate required fields are present and non-empty ---
        missing_or_empty = False
        for field in REQUIRED_FIELDS:
            value = record.get(field, None)
            if value is None or not isinstance(value, str) or value.strip() == "":
                missing_or_empty = True
                break

        if missing_or_empty:
            stats["missing_fields_skipped"] += 1
            continue

        # Record is valid; keep original data untouched
        records.append(record)
        valid_count += 1

    stats["per_file_counts"][file_path.name] = valid_count
    return records


def deduplicate_records(records: list, stats: dict) -> list:
    """
    Remove duplicate records based on the (instruction + input) key.
    The first occurrence of a duplicate is kept; subsequent ones are dropped.
    Original text/data is preserved exactly for kept records.
    """
    seen_keys = set()
    unique_records = []

    for record in records:
        # Build the uniqueness key from instruction + input (exact text)
        dedup_key = record["instruction"] + record["input"]

        if dedup_key in seen_keys:
            stats["duplicates_removed"] += 1
            continue

        seen_keys.add(dedup_key)
        unique_records.append(record)

    return unique_records


def write_output(records: list, output_file: Path) -> None:
    """
    Write the final list of records to the output JSONL file,
    one JSON object per line, preserving original data exactly.
    """
    # Ensure the output directory exists
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with output_file.open("w", encoding="utf-8") as f:
        for record in records:
            # ensure_ascii=False preserves original characters as-is;
            # separators keep formatting compact but content is unchanged
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def print_summary(stats: dict, final_size: int) -> None:
    """
    Print a detailed, formatted summary of the merge operation.
    """
    print("-----------------------------------------")
    print("Merge Summary")
    print("-----------------------------------------")

    for filename in SOURCE_FILES:
        count = stats["per_file_counts"].get(filename, 0)
        print(f"{filename}: {count} records")

    print(f"Malformed JSON skipped: {stats['malformed_skipped']}")
    print(f"Missing fields skipped: {stats['missing_fields_skipped']}")
    print(f"Duplicates removed: {stats['duplicates_removed']}")
    print(f"Final dataset size: {final_size} records")
    print("Output:")
    print(f"{OUTPUT_FILE.as_posix()}")
    print("-----------------------------------------")


def main():
    # Statistics tracked across the whole merge process
    stats = {
        "per_file_counts": {},      # valid record count per source file
        "malformed_skipped": 0,     # lines that failed JSON parsing
        "missing_fields_skipped": 0,  # records missing required fields
        "duplicates_removed": 0,    # records removed due to duplication
    }

    all_records = []

    # --- Step 1: Load, validate, and collect records from all source files ---
    for filename in SOURCE_FILES:
        file_path = DATASET_DIR / filename
        file_records = load_and_validate_file(file_path, stats)
        all_records.extend(file_records)

    # --- Step 2: Deduplicate based on (instruction + input) ---
    unique_records = deduplicate_records(all_records, stats)

    # --- Step 3: Shuffle deterministically using the fixed seed ---
    random.seed(RANDOM_SEED)
    random.shuffle(unique_records)

    # --- Step 4: Write the merged, deduplicated, shuffled dataset ---
    try:
        write_output(unique_records, OUTPUT_FILE)
    except OSError as e:
        print(f"[ERROR] Failed to write output file {OUTPUT_FILE}: {e}")
        return

    # --- Step 5: Print the final summary report ---
    print_summary(stats, final_size=len(unique_records))


if __name__ == "__main__":
    main()