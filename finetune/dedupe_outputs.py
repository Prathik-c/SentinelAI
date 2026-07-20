"""
dedupe_outputs.py

Caps exact-duplicate 'output' values in a JSONL fine-tuning dataset to a
maximum number of occurrences. This prevents the model from over-learning
a small set of repeated answers (e.g. the same short phrase appearing
15-20+ times), which hurts generalization during LoRA fine-tuning.

For each group of records sharing the exact same 'output' text, this
script randomly keeps up to MAX_OUTPUT_OCCURRENCES of them and drops
the rest. Random selection (with a fixed seed) is used instead of just
keeping the first N, so the kept examples aren't biased toward whatever
happened to appear first after shuffling in merge_dataset.py.

Usage:
    python dedupe_outputs.py
    python dedupe_outputs.py path/to/input.jsonl path/to/output.jsonl

Only Python standard libraries are used: json, random, pathlib, sys,
collections.
"""

import json
import random
import sys
from collections import defaultdict
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Script's own directory = finetune/
SCRIPT_DIR = Path(__file__).resolve().parent

# Default input/output files
DEFAULT_INPUT_FILE = SCRIPT_DIR / "training_data.jsonl"
DEFAULT_OUTPUT_FILE = SCRIPT_DIR / "training_data_deduped.jsonl"

# Maximum number of times an identical 'output' string is allowed to appear
MAX_OUTPUT_OCCURRENCES = 3

# Fixed seed so which duplicates get kept/dropped is reproducible
RANDOM_SEED = 42


def load_records(file_path: Path) -> list:
    """
    Read and parse all valid JSON records from the input JSONL file.
    Lines that fail to parse are skipped with a warning (this script
    assumes the file already passed validate_dataset.py, so this is
    just a safety net).
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Input file not found: {file_path}")

    records = []
    with file_path.open("r", encoding="utf-8") as f:
        for line_num, raw_line in enumerate(f, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                print(f"[WARNING] Skipping malformed JSON at line {line_num}")
                continue
            records.append(record)

    return records


def cap_duplicate_outputs(records: list) -> tuple:
    """
    Group records by their exact 'output' text, then randomly cap each
    group at MAX_OUTPUT_OCCURRENCES. Returns (kept_records, stats).
    """
    # Group record indices by their output text
    groups = defaultdict(list)
    for idx, record in enumerate(records):
        output_text = record.get("output", "").strip()
        groups[output_text].append(idx)

    keep_indices = set()
    stats = {
        "total_groups": len(groups),
        "groups_over_limit": 0,
        "records_dropped": 0,
        "dropped_examples": [],  # (output_preview, original_count, kept_count)
    }

    for output_text, indices in groups.items():
        if len(indices) <= MAX_OUTPUT_OCCURRENCES:
            # Under the cap, keep all of them
            keep_indices.update(indices)
            continue

        # Over the cap: randomly sample which ones to keep
        stats["groups_over_limit"] += 1
        kept = set(random.sample(indices, MAX_OUTPUT_OCCURRENCES))
        keep_indices.update(kept)

        dropped_count = len(indices) - MAX_OUTPUT_OCCURRENCES
        stats["records_dropped"] += dropped_count

        preview = output_text[:80] + ("..." if len(output_text) > 80 else "")
        stats["dropped_examples"].append((preview, len(indices), MAX_OUTPUT_OCCURRENCES))

    # Preserve original relative order for the kept records
    kept_records = [records[i] for i in sorted(keep_indices)]

    return kept_records, stats


def write_records(records: list, output_file: Path) -> None:
    """
    Write records to the output JSONL file, one JSON object per line,
    preserving original data exactly.
    """
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def print_report(input_file: Path, output_file: Path, original_count: int,
                  final_count: int, stats: dict) -> None:
    """
    Print a summary of what was capped/dropped.
    """
    print("-----------------------------------------")
    print("Duplicate Output Capping Summary")
    print("-----------------------------------------")
    print(f"Input file: {input_file}")
    print(f"Original record count: {original_count}")
    print(f"Unique output groups: {stats['total_groups']}")
    print(f"Groups exceeding cap of {MAX_OUTPUT_OCCURRENCES}: {stats['groups_over_limit']}")
    print(f"Records dropped: {stats['records_dropped']}")
    print(f"Final record count: {final_count}")
    print()

    if stats["dropped_examples"]:
        print("Examples of capped output groups:")
        for preview, original_count_group, kept_count in stats["dropped_examples"][:10]:
            print(f"  '{preview}' -> kept {kept_count} of {original_count_group}")
        remaining = len(stats["dropped_examples"]) - 10
        if remaining > 0:
            print(f"  ... and {remaining} more groups capped")

    print()
    print(f"Output written to: {output_file}")
    print("-----------------------------------------")


def main():
    # Allow optional input/output paths via command line
    if len(sys.argv) >= 2:
        input_file = Path(sys.argv[1]).resolve()
    else:
        input_file = DEFAULT_INPUT_FILE

    if len(sys.argv) >= 3:
        output_file = Path(sys.argv[2]).resolve()
    else:
        output_file = DEFAULT_OUTPUT_FILE

    random.seed(RANDOM_SEED)

    try:
        records = load_records(input_file)
    except FileNotFoundError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)
    except OSError as e:
        print(f"[ERROR] Could not read file {input_file}: {e}")
        sys.exit(1)

    original_count = len(records)
    kept_records, stats = cap_duplicate_outputs(records)

    try:
        write_records(kept_records, output_file)
    except OSError as e:
        print(f"[ERROR] Failed to write output file {output_file}: {e}")
        sys.exit(1)

    print_report(input_file, output_file, original_count, len(kept_records), stats)


if __name__ == "__main__":
    main()