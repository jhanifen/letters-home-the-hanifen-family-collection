#!/usr/bin/env python3
"""
Analyze the full letter corpus to build a narrative timeline,
infer missing dates, and identify the overall story arc.
"""
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = ROOT / "data"
INDEX_PATH = DATA_DIR / "index.json"
OUTPUT_PATH = DATA_DIR / "timeline_analysis.json"

def build_corpus_summary(letters: list[dict]) -> str:
    """Build a concise but complete summary of every letter for analysis."""
    lines = []
    for l in letters:
        lid = l["letter_id"]
        meta = l.get("metadata", {})
        date = meta.get("date", "NO DATE")
        date_norm = meta.get("date_normalized", "")
        frm = meta.get("from", "?")
        to = meta.get("to", "?")
        loc = meta.get("location_written_from", "?")
        summary = l.get("summary", "")
        topics = ", ".join(meta.get("topics", []))
        people = ", ".join(meta.get("people_mentioned", []))
        places = ", ".join(meta.get("places_mentioned", []))
        hist = meta.get("historical_context", "") or ""
        mood = meta.get("mood_tone", "") or ""
        full_text = l.get("full_transcription", "")

        lines.append(f"=== LETTER {lid} ===")
        lines.append(f"Date: {date} | Normalized: {date_norm}")
        lines.append(f"From: {frm}")
        lines.append(f"To: {to}")
        lines.append(f"Written from: {loc}")
        lines.append(f"Topics: {topics}")
        lines.append(f"People mentioned: {people}")
        lines.append(f"Places mentioned: {places}")
        lines.append(f"Historical context: {hist}")
        lines.append(f"Mood/tone: {mood}")
        lines.append(f"Summary: {summary}")
        lines.append(f"Full transcription:\n{full_text}")
        lines.append("")

    return "\n".join(lines)


ANALYSIS_PROMPT = """\
You are a historian and literary analyst specializing in American family correspondence \
from the WWII era. You have been given the complete transcriptions and metadata of 88 \
letters from the Hanifen family collection.

FAMILY CONTEXT:
- Three Hanifen brothers: Bob (Robert), Jim (James Edward Jr / Jimmy), John
- Their father: James Edward Hanifen Sr (also called Jim Sr, Dad, James)
- Bob's wife: likely Helen. Jim's wife: possibly referenced.
- Common locations: Des Moines, Iowa (home); Dallas, Texas (Bob's work); various military postings
- Timeline spans roughly 1941-1976, covering college, WWII service, Korean War era, and post-war life
- Bob Hanifen is the central figure of this collection

TASK:
Analyze the entire collection and produce a JSON response with this structure:

{{
  "narrative_overview": "A 3-5 paragraph narrative overview of the entire collection — what story do these letters tell? What are the major themes, turning points, and emotional arcs?",

  "life_chapters": [
    {{
      "chapter_title": "descriptive title for this period",
      "date_range": "approximate start - end",
      "description": "2-3 paragraph description of this chapter of the story",
      "key_letters": ["letter IDs that are most significant for this chapter"],
      "themes": ["major themes"],
      "key_events": ["important events referenced or occurring"]
    }}
  ],

  "date_estimates": [
    {{
      "letter_id": "ID of undated letter",
      "estimated_date": "YYYY-MM-DD or YYYY-MM or YYYY",
      "confidence": "high / medium / low",
      "reasoning": "why you think this date — references to events, context clues, position in sequence, writing style, locations mentioned, etc."
    }}
  ],

  "character_profiles": [
    {{
      "name": "full name",
      "aliases": ["nicknames, alternate references in letters"],
      "role": "relationship to the collection / family role",
      "description": "who they are based on the letters",
      "letters_appeared_in": ["letter IDs where they appear or are mentioned"]
    }}
  ],

  "recurring_themes": [
    {{
      "theme": "theme name",
      "description": "how this theme manifests across the letters",
      "relevant_letters": ["letter IDs"]
    }}
  ],

  "historical_events_referenced": [
    {{
      "event": "event name",
      "date_range": "when it occurred",
      "letters_referencing": ["letter IDs"],
      "how_it_affected_family": "brief description"
    }}
  ],

  "chronological_order": [
    {{
      "letter_id": "letter ID",
      "date": "known or estimated date (YYYY-MM-DD format where possible)",
      "date_is_approximate": true/false,
      "from": "sender",
      "to": "recipient",
      "one_line_summary": "single sentence summary"
    }}
  ]
}}

Be thorough. For undated letters, use every clue available: references to seasons, \
holidays, events, military ranks/postings, addresses, other letters in the sequence, \
handwriting style notes, paper type, and any internal references. Mark your confidence \
level honestly.

LETTER CORPUS:
{corpus}

Respond with ONLY the JSON object.\
"""


def main():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key or api_key == "your-api-key-here":
        print("Error: Set ANTHROPIC_API_KEY in .env file.")
        sys.exit(1)

    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        index = json.load(f)

    letters = index["letters"]
    print(f"Analyzing {len(letters)} letters...")

    corpus = build_corpus_summary(letters)
    print(f"Corpus size: {len(corpus):,} characters")

    import anthropic
    client = anthropic.Anthropic(api_key=api_key)

    prompt = ANALYSIS_PROMPT.format(corpus=corpus)

    print("Sending to Claude (this may take a few minutes with the full corpus)...")
    text = ""
    with client.messages.stream(
        model="claude-sonnet-4-6",
        max_tokens=65536,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for chunk in stream.text_stream:
            text += chunk
            # Print progress dots
            if len(text) % 5000 < len(chunk):
                print(".", end="", flush=True)
    print(f" ({len(text):,} chars)")

    # Clean markdown fences if present
    text = text.strip()
    if text.startswith("```"):
        import re
        text = re.sub(r"^```\w*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        text = text.strip()

    try:
        analysis = json.loads(text)
    except json.JSONDecodeError:
        # Save raw response for debugging
        raw_path = DATA_DIR / "timeline_raw_response.txt"
        with open(raw_path, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"Warning: Could not parse JSON. Raw response saved to {raw_path}")
        print(f"Response length: {len(text)} chars")
        sys.exit(1)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(analysis, f, indent=2, ensure_ascii=False)

    print(f"\nAnalysis saved to {OUTPUT_PATH}")
    print(f"  - {len(analysis.get('life_chapters', []))} life chapters identified")
    print(f"  - {len(analysis.get('date_estimates', []))} date estimates for undated letters")
    print(f"  - {len(analysis.get('character_profiles', []))} character profiles")
    print(f"  - {len(analysis.get('recurring_themes', []))} recurring themes")
    print(f"  - {len(analysis.get('historical_events_referenced', []))} historical events")
    print(f"  - {len(analysis.get('chronological_order', []))} letters in chronological order")


if __name__ == "__main__":
    main()
