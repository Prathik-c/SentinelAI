import json, glob

files = glob.glob("dataset/*.jsonl")
found_anywhere = False

for filepath in files:
    with open(filepath, encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue  # skip malformed lines, don't crash
            text = json.dumps(record)
            if "HKLM\\System" in text or "HKLM\\\\System" in text or "HKEY_LOCAL_MACHINE\\System" in text:
                print(f"{filepath} line {i}: {record}")
                found_anywhere = True

if not found_anywhere:
    print("Not found in any dataset file (that parsed successfully).")