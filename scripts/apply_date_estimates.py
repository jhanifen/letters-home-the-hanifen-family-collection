#!/usr/bin/env python3
"""
Apply estimated dates from the timeline analysis back into individual letter JSON files.
Marks estimated dates clearly as approximate.
"""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = ROOT / "data"
LETTERS_DIR = DATA_DIR / "letters"
ANALYSIS_PATH = DATA_DIR / "timeline_analysis.json"
INDEX_PATH = DATA_DIR / "index.json"


def main():
    with open(ANALYSIS_PATH, "r", encoding="utf-8") as f:
        analysis = json.load(f)

    date_estimates = {d["letter_id"]: d for d in analysis.get("date_estimates", [])}
    chrono_order = {c["letter_id"]: c for c in analysis.get("chronological_order", [])}

    updated = 0
    for letter_file in sorted(LETTERS_DIR.glob("letter_*.json")):
        with open(letter_file, "r", encoding="utf-8") as f:
            letter = json.load(f)

        lid = letter["letter_id"]
        meta = letter.get("metadata", {})
        changed = False

        # Apply date estimates for undated letters
        if lid in date_estimates:
            est = date_estimates[lid]
            meta["date_estimated"] = est["estimated_date"]
            meta["date_estimated_confidence"] = est["confidence"]
            meta["date_estimation_reasoning"] = est["reasoning"]
            meta["date_is_approximate"] = True

            # If there's no normalized date, use the estimate
            if not meta.get("date_normalized"):
                meta["date_normalized"] = est["estimated_date"]

            changed = True

        # Add chronological position from the analysis
        if lid in chrono_order:
            entry = chrono_order[lid]
            meta["chronological_date"] = entry.get("date", "")
            meta["date_is_approximate"] = entry.get("date_is_approximate", False) or meta.get("date_is_approximate", False)
            changed = True

        if changed:
            letter["metadata"] = meta
            with open(letter_file, "w", encoding="utf-8") as f:
                json.dump(letter, f, indent=2, ensure_ascii=False)
            approx = " (APPROXIMATE)" if meta.get("date_is_approximate") else ""
            print(f"  Updated letter {lid}: {meta.get('date_normalized', '?')}{approx}")
            updated += 1

    print(f"\nUpdated {updated} letter files.")

    # Rebuild master index
    letters = []
    for path in sorted(LETTERS_DIR.glob("letter_*.json")):
        with open(path, "r", encoding="utf-8") as f:
            letters.append(json.load(f))

    import re
    def sort_key(d):
        m = re.match(r"(\d+)([a-z]?)", str(d.get("letter_id", "999")))
        return (int(m.group(1)), m.group(2)) if m else (9999, "")

    letters.sort(key=sort_key)
    index = {"total_letters": len(letters), "letters": letters}
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)

    print(f"Rebuilt index with {len(letters)} letters.")

    # Summary stats
    dated = sum(1 for l in letters if l.get("metadata", {}).get("date_normalized"))
    approx = sum(1 for l in letters if l.get("metadata", {}).get("date_is_approximate"))
    print(f"  {dated} letters have dates ({approx} approximate)")


if __name__ == "__main__":
    main()
