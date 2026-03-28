#!/usr/bin/env python3
"""
Analyze photos to extract dates, categories, and letter connections.
Uses Claude to interpret filenames against the letter corpus context.
"""
import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

ROOT = Path(__file__).resolve().parent.parent

SCANS_DIR = ROOT / "BobScans"
PHOTOS_DIR = SCANS_DIR / "photos"
DATA_DIR = ROOT / "data"
INDEX_PATH = DATA_DIR / "index.json"
OUTPUT_PATH = DATA_DIR / "photo_manifest.json"
IMAGE_EXTS = {".png", ".jpg", ".jpeg"}

PROMPT = """\
You are analyzing a collection of family photographs from the Hanifen family of Des Moines, Iowa.

FAMILY CONTEXT:
- Three Hanifen brothers: Bob (Robert), Jim (James Edward Jr / Jimmy), John
- Their father: James Edward Hanifen Sr (also Jim Sr, Dad) — ran Hanifen Body & Paint Co. at 904 Keo Way, Des Moines
- Their mother: Pearl Miller Hanifen (died 1930)
- Bob's wife: Jan. Jim's wife: Helen. John's wife: Millie (Osterhort) and later Marion.
- Home address: 424 Virginia Avenue, Des Moines
- Aunt Pauline F. Hanifen (1904-1987)
- Extended family: Barquists, Zimmermans, Millers, Whitelocks, Crees
- Timeline: letters span 1941-1976, covering WWII, Korea, post-war life
- Bob served in AAF, stationed at Sheppard Field TX, U of Wyoming, Chanute Field IL, Italy
- John served in 439th Engineer Construction Battalion in Korea
- Jim served at Fort Riley KS

LETTER SUMMARIES (for linking photos to letters):
{letter_summaries}

PHOTO FILENAMES:
{photo_list}

For each photo, produce a JSON object with:
- "filename": the original filename
- "caption": a clean, human-readable caption (proper names capitalized, dates included when known)
- "date_estimate": best guess date as "YYYY" or "YYYY-MM" or null. Use filename clues, people identified, historical context.
- "date_confidence": "known" (date in filename), "high", "medium", "low", or null
- "categories": array from these options: ["brothers", "military", "family-gathering", "portrait", "location", "vehicle", "childhood", "document", "couple", "extended-family", "memorial"]
- "people": array of people identified (use full names where possible)
- "letter_id": letter ID this photo relates to, or null. Match based on people, places, events, or if the photo was clearly enclosed with a letter.
- "sort_order": integer for chronological sorting (0 = earliest, higher = later). Group unknowns at the end.

Return a JSON array of objects, one per photo. ONLY the JSON array, no other text.
"""


def main():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key or api_key == "your-api-key-here":
        print("Error: Set ANTHROPIC_API_KEY in .env")
        return

    # Collect photo filenames
    photos = []
    back_files = set()

    all_files = sorted(PHOTOS_DIR.iterdir()) if PHOTOS_DIR.exists() else []
    for f in all_files:
        if f.name.lower().endswith(('_back.png', '_back.jpg', ' back.png', ' back.jpg', '-back.png', '-back.jpg')):
            back_files.add(f.name)
        if f.name.startswith("11a "):
            back_files.add(f.name)

    for f in all_files:
        if not f.is_file() or f.suffix.lower() not in IMAGE_EXTS:
            continue
        if f.name in back_files:
            continue
        if f.name.startswith("Image_"):
            continue
        photos.append(f"photos/{f.name}")

    # Root-level non-letter photos
    for f in sorted(SCANS_DIR.iterdir()):
        if f.is_file() and f.suffix.lower() in IMAGE_EXTS:
            if not f.name.lower().startswith("letter") and not f.name.lower().startswith("page"):
                if "back" not in f.name.lower():
                    photos.append(f.name)

    print(f"Found {len(photos)} photos to analyze")

    # Build letter summaries for context
    with open(INDEX_PATH, "r") as f:
        index = json.load(f)

    summaries = []
    for l in index["letters"]:
        meta = l.get("metadata", {})
        lid = l["letter_id"]
        date = meta.get("date", "")
        frm = (meta.get("from", "") or "")[:60]
        to = (meta.get("to", "") or "")[:60]
        summary = (l.get("summary", "") or "")[:150]
        people = ", ".join(meta.get("people_mentioned", []))[:100]
        summaries.append(f"Letter {lid}: {date} | {frm} -> {to} | {summary} | People: {people}")

    prompt = PROMPT.format(
        letter_summaries="\n".join(summaries),
        photo_list="\n".join(photos),
    )

    import anthropic
    client = anthropic.Anthropic(api_key=api_key)

    print("Sending to Claude...")
    text = ""
    with client.messages.stream(
        model="claude-sonnet-4-6",
        max_tokens=16384,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for chunk in stream.text_stream:
            text += chunk
            if len(text) % 3000 < len(chunk):
                print(".", end="", flush=True)
    print(f" ({len(text):,} chars)")

    # Parse
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```\w*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        text = text.strip()

    try:
        manifest = json.loads(text)
    except json.JSONDecodeError:
        raw_path = DATA_DIR / "photo_raw_response.txt"
        raw_path.write_text(text)
        print(f"JSON parse error. Raw saved to {raw_path}")
        return

    # Add back-file references
    for entry in manifest:
        fname = entry.get("filename", "")
        stem = Path(fname).stem.lower()
        for bf in back_files:
            bs = Path(bf).stem.lower()
            if stem in bs or bs.replace('_back', '').replace(' back', '').replace('-back', '') == stem:
                entry["back"] = f"photos/{bf}" if not bf.startswith("photos/") else bf
                break

    # Sort by sort_order
    manifest.sort(key=lambda x: x.get("sort_order", 9999))

    with open(OUTPUT_PATH, "w") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    cats = set()
    for m in manifest:
        cats.update(m.get("categories", []))

    print(f"\nSaved {len(manifest)} photos to {OUTPUT_PATH}")
    print(f"Categories found: {', '.join(sorted(cats))}")
    dated = sum(1 for m in manifest if m.get("date_estimate"))
    linked = sum(1 for m in manifest if m.get("letter_id"))
    print(f"  {dated} with date estimates, {linked} linked to letters")


if __name__ == "__main__":
    main()
