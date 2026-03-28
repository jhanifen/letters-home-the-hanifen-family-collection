#!/usr/bin/env python3
"""Polish the audiobook script with a careful editorial pass."""
import json
import os
import re
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = ROOT / "data"
SCRIPT_PATH = DATA_DIR / "audiobook_script.txt"
POLISHED_PATH = DATA_DIR / "audiobook_script_polished.txt"
INDEX_PATH = DATA_DIR / "index.json"
ANALYSIS_PATH = DATA_DIR / "timeline_analysis.json"

POLISH_PROMPT = """\
You are a world-class audiobook editor and literary nonfiction writer. Your style models \
are Ken Burns documentaries, David Grann's narrative nonfiction, and the best of NPR's \
storytelling. You are editing a narration script for a family history audiobook.

Below is the current draft, followed by the source letter data for fact-checking.

YOUR TASK — perform a careful editorial polish:

1. RHYTHM & FLOW: This is for the ear. Every sentence should sound natural spoken aloud. \
   Vary sentence length. Short sentences hit hard. Longer ones carry the reader forward. \
   Read each paragraph mentally aloud — does it flow? Fix anything that stumbles.

2. FACT-CHECK: Compare every direct quote against the actual letter transcriptions provided. \
   Fix any misquotations. Ensure dates, ranks, locations, and names are accurate.

3. TIGHTEN: Cut anything that drags. If a passage restates what the letters already said \
   beautifully, get out of the way and let the letters speak. The narrator should set up \
   the quotes and then step back.

4. EMOTIONAL BEATS: Make sure the big moments land. The atomic bomb letter. Jim's crying \
   letter. The Naples riot. Aunt Pauline's closing. These deserve space — a pause before, \
   the quote, a pause after, and then one sentence of reflection. No more.

5. TRANSITIONS: Chapter transitions should feel like a breath, not a break. The listener \
   shouldn't feel jolted. Consider how each chapter ending echoes into the next opening.

6. [pause] MARKERS: Keep them, but use them with intention. A [pause] after a powerful \
   quote is a beat of silence for it to sink in. Don't overuse them. Remove any that \
   feel mechanical. Add a [long pause] between chapters.

7. OPENING & CLOSING: The prologue is strong. The epilogue is strong. Polish both but \
   don't overwork them. The ending — "They were real." — is perfect. Don't change it.

8. LENGTH: Keep it roughly the same length (4,500–5,500 words). Don't pad. Don't cut \
   dramatically. Just make every word earn its place.

9. ACCURACY NOTES: If you find factual errors or uncertain attributions, fix them silently. \
   If Bob is described as "the youngest" but the record is ambiguous, just say "one of \
   the three brothers" instead.

IMPORTANT: Return the COMPLETE polished script. Don't summarize or truncate. Every chapter, \
every quote, every [pause] marker. The full thing, beginning to end.

===== CURRENT DRAFT =====
{script}

===== SOURCE LETTER DATA (for fact-checking quotes) =====
{letter_data}

Return the complete polished script now.\
"""


def get_key_letter_data():
    with open(INDEX_PATH, "r") as f:
        index = json.load(f)

    key_ids = {"1", "2", "3", "4", "7", "8", "9", "11", "16", "24", "28",
               "35", "45", "46", "51", "52", "55", "57", "58", "84"}
    texts = []
    for l in index["letters"]:
        if str(l["letter_id"]) in key_ids:
            meta = l.get("metadata", {})
            texts.append(f"=== Letter {l['letter_id']} ({meta.get('date','?')}) ===")
            texts.append(f"From: {meta.get('from','?')[:80]}")
            texts.append(f"To: {meta.get('to','?')[:80]}")
            texts.append(l.get("full_transcription", ""))
            texts.append("")
    return "\n".join(texts)


def main():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise SystemExit("Set ANTHROPIC_API_KEY")

    script = SCRIPT_PATH.read_text(encoding="utf-8")
    letter_data = get_key_letter_data()

    prompt = POLISH_PROMPT.format(script=script, letter_data=letter_data)

    import anthropic
    client = anthropic.Anthropic(api_key=api_key)

    print(f"Polishing script ({len(script.split())} words)...")
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
    print(f" done ({len(text.split())} words)")

    POLISHED_PATH.write_text(text, encoding="utf-8")
    print(f"Polished script saved to {POLISHED_PATH}")

    # Show a diff summary
    orig_words = len(script.split())
    new_words = len(text.split())
    print(f"  Original: {orig_words} words")
    print(f"  Polished: {new_words} words")
    print(f"  Change: {new_words - orig_words:+d} words")


if __name__ == "__main__":
    main()
