#!/usr/bin/env python3
"""
Transcribe scanned Hanifen family letters using Claude's vision API.

Usage:
  # Dry run — verify letter grouping without calling the API
  python transcribe.py --dry-run

  # Transcribe all letters
  python transcribe.py

  # Transcribe specific letters
  python transcribe.py --letters 1 2 3

  # Resume (skips already-transcribed letters)
  python transcribe.py  # resume is automatic
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import io
import json
import mimetypes
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from PIL import Image

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent

SCANS_DIR = ROOT / "BobScans"
DATA_DIR = ROOT / "data"
LETTERS_DIR = DATA_DIR / "letters"
INDEX_PATH = DATA_DIR / "index.json"

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}

# Page ordering: envelope/cover images sort before content pages, backs sort last
SECTION_ORDER = {
    "front": 0,
    "cover": 0,
    "envelope": 0,
    "inside": 5,
    "inside_sheet": 6,
    "inside_sheet_back": 7,
    "back": 99,
}

MAX_DIMENSION = 2000  # longest side in pixels
JPEG_QUALITY = 85

# ---------------------------------------------------------------------------
# Family context for the transcription prompt
# ---------------------------------------------------------------------------
FAMILY_CONTEXT = """\
These are letters from the Hanifen family, primarily from the late 1930s through \
the late 1940s and into the 1950s. The family includes three brothers:

- Bob (Robert) Hanifen — the central figure. These letters follow his life \
  leaving home, going to college, serving in WWII, and returning home.
- Jim (James/Jimmy) Hanifen — Bob's brother. Full name: James Edward Hanifen Jr. \
  Also called "Jim" or "Jimmy."
- John Hanifen — Bob's brother.

Their father is James Edward Hanifen Sr, sometimes called "Jim Sr" or "Dad" or \
"James." When a letter mentions "Jim" or "Jimmy," use context clues (age references, \
tone, role as parent vs. sibling) to determine whether it refers to the father (Sr) \
or the brother (Jr). Note your reasoning in the metadata if ambiguous.

Bob has a son named Bob Jr (Robert Jr) who appears in later correspondence.

Other family members who may appear: Edith (mother?), Helen, Marion, Millie, \
Pearl Miller Hanifen, Pauline Hanifen, various aunts/uncles/cousins.

Common locations: Des Moines (Iowa), possibly military bases during WWII.\
"""

TRANSCRIPTION_PROMPT = """\
You are an expert archivist transcribing historical handwritten letters. \
You will be shown scanned pages of a single letter.

FAMILY CONTEXT:
{family_context}

INSTRUCTIONS:
1. Transcribe each page faithfully, preserving paragraph breaks, punctuation, \
   and spelling as written (including misspellings — note them but don't correct).
2. If text is illegible, use [illegible] or [illegible word]. If you can make a \
   guess, use [word?] with a question mark.
3. For envelope/cover images, note any visible addresses, postmarks, stamps, or \
   annotations.

Return a JSON object with this exact structure:
{{
  "letter_id": "{letter_id}",
  "metadata": {{
    "from": "sender's name (best guess, with reasoning if ambiguous)",
    "to": "recipient's name",
    "date": "date as written on the letter, or null",
    "date_normalized": "YYYY-MM-DD format if possible, or null",
    "location_written_from": "where the sender was when writing, or null",
    "location_sent_to": "recipient's address if visible, or null",
    "postmark": "postmark text if visible on envelope, or null",
    "envelope_notes": "any other envelope observations, or null",
    "topics": ["array", "of", "key", "topics"],
    "people_mentioned": ["names of people mentioned in the letter"],
    "places_mentioned": ["places mentioned in the letter"],
    "mood_tone": "brief description of the letter's emotional tone",
    "legibility": "good / fair / poor",
    "legibility_notes": "specific legibility issues, or null",
    "historical_context": "any references to historical events (war, etc.), or null"
  }},
  "pages": [
    {{
      "page_label": "page identifier",
      "source_file": "original filename",
      "transcription": "full transcription of this page"
    }}
  ],
  "full_transcription": "all pages combined into one continuous text",
  "summary": "2-4 sentence summary of the letter's content and significance"
}}

Respond with ONLY the JSON object, no other text.\
"""


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class LetterPage:
    letter_id: str
    page_label: str
    page_order: float
    path: Path


@dataclass
class Letter:
    letter_id: str
    pages: list[LetterPage] = field(default_factory=list)

    @property
    def sort_key(self) -> tuple:
        """Natural sort: numeric part first, then variant letter."""
        m = re.match(r"(\d+)([a-z]?)", self.letter_id)
        if m:
            return (int(m.group(1)), m.group(2))
        return (9999, self.letter_id)


# ---------------------------------------------------------------------------
# Image discovery and grouping
# ---------------------------------------------------------------------------
def discover_images(scans_dir: Path) -> list[Path]:
    """Find all image files under scans_dir (non-recursive for letter files)."""
    images = []
    for path in sorted(scans_dir.iterdir()):
        if path.is_file() and path.suffix.lower() in IMAGE_EXTS:
            images.append(path)
    return images


def parse_filename(path: Path) -> Optional[LetterPage]:
    """Parse a scan filename into letter ID and page info."""
    stem = path.stem.lower()
    if not stem.startswith("letter"):
        return None

    # Match: letter<number><optional variant letter>
    prefix = re.match(r"letter(?P<num>\d+)(?P<variant>[a-z]?)", stem)
    if not prefix:
        return None

    letter_id = f"{prefix.group('num')}{prefix.group('variant')}"
    remainder = stem[prefix.end():].lstrip("-_")

    if not remainder:
        # Bare envelope/cover image like "letter5.jpg"
        return LetterPage(
            letter_id=letter_id,
            page_label="envelope",
            page_order=-1.0,
            path=path,
        )

    # Split on hyphens or underscores
    tokens = [t for t in re.split(r"[-_]", remainder) if t]

    # Check for page number: "page1", "page2b", etc.
    page_match = re.match(r"page(?P<num>\d+)(?P<suffix>[a-z]?)", tokens[0])
    if page_match:
        num = int(page_match.group("num"))
        suffix = page_match.group("suffix")
        suffix_offset = (ord(suffix) - ord("a") + 1) * 0.01 if suffix else 0.0
        page_order = float(num) + suffix_offset
        page_label = tokens[0]
        # Check for trailing qualifiers like "page1b" being a back side
        if len(tokens) > 1:
            page_label = "_".join(tokens)
        return LetterPage(
            letter_id=letter_id,
            page_label=page_label,
            page_order=page_order,
            path=path,
        )

    # Named section: front, back, inside, inside_sheet, etc.
    section = "_".join(tokens)
    base_token = tokens[0]
    page_order = float(SECTION_ORDER.get(section, SECTION_ORDER.get(base_token, 50.0)))

    return LetterPage(
        letter_id=letter_id,
        page_label=section,
        page_order=page_order,
        path=path,
    )


def group_letters(scans_dir: Path) -> list[Letter]:
    """Group scan images into letters, sorted naturally."""
    groups: dict[str, Letter] = {}

    for image_path in discover_images(scans_dir):
        parsed = parse_filename(image_path)
        if not parsed:
            continue
        if parsed.letter_id not in groups:
            groups[parsed.letter_id] = Letter(letter_id=parsed.letter_id)
        groups[parsed.letter_id].pages.append(parsed)

    # Sort pages within each letter
    for letter in groups.values():
        letter.pages.sort(key=lambda p: (p.page_order, p.page_label, p.path.name))

    # Sort letters naturally
    letters = sorted(groups.values(), key=lambda l: l.sort_key)
    return letters


# ---------------------------------------------------------------------------
# Image encoding
# ---------------------------------------------------------------------------
def encode_image(path: Path) -> tuple[str, str]:
    """Load, resize, compress an image and return (media_type, base64_data)."""
    try:
        with Image.open(path) as img:
            img = img.convert("RGB")
            w, h = img.size
            scale = min(1.0, MAX_DIMENSION / max(w, h))
            if scale < 1.0:
                img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
            data = base64.standard_b64encode(buf.getvalue()).decode("ascii")
            return "image/jpeg", data
    except Exception:
        # Fallback: send raw bytes
        raw = path.read_bytes()
        mime = mimetypes.guess_type(path.name)[0] or "image/png"
        data = base64.standard_b64encode(raw).decode("ascii")
        return mime, data


# ---------------------------------------------------------------------------
# Claude API interaction
# ---------------------------------------------------------------------------
def build_messages(letter: Letter) -> list[dict]:
    """Build the messages payload for Claude's API."""
    content = []

    # Add each page image with a label
    for page in letter.pages:
        content.append({
            "type": "text",
            "text": f"--- {page.page_label} (file: {page.path.name}) ---",
        })
        media_type, b64_data = encode_image(page.path)
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": b64_data,
            },
        })

    # Final instruction
    prompt = TRANSCRIPTION_PROMPT.format(
        family_context=FAMILY_CONTEXT,
        letter_id=letter.letter_id,
    )
    content.append({"type": "text", "text": prompt})

    return [{"role": "user", "content": content}]


def transcribe_letter(client, letter: Letter, model: str) -> dict:
    """Send a letter's pages to Claude and return structured JSON."""
    messages = build_messages(letter)

    # Scale max_tokens based on page count — large letters need more room
    max_tokens = min(16384, 4096 + len(letter.pages) * 1500)

    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=messages,
    )

    # Extract text from response
    text = ""
    for block in response.content:
        if block.type == "text":
            text += block.text

    # Parse JSON from response — handle markdown code fences
    text = text.strip()
    if text.startswith("```"):
        # Remove opening fence (```json or ```)
        text = re.sub(r"^```\w*\n?", "", text)
        # Remove closing fence
        text = re.sub(r"\n?```$", "", text)
        text = text.strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        print(f"  WARNING: Could not parse JSON for letter {letter.letter_id}")
        print(f"  Response text: {text[:500]}")
        raise ValueError(
            f"Model did not return valid JSON for letter {letter.letter_id}"
        ) from exc

    # Ensure letter_id is set
    data["letter_id"] = letter.letter_id

    # Attach source file paths to pages
    for i, page in enumerate(letter.pages):
        if i < len(data.get("pages", [])):
            data["pages"][i]["source_file"] = page.path.name

    return data


# ---------------------------------------------------------------------------
# Data persistence
# ---------------------------------------------------------------------------
def save_letter(letter_id: str, data: dict) -> Path:
    """Save a single letter's data to its own JSON file."""
    LETTERS_DIR.mkdir(parents=True, exist_ok=True)
    path = LETTERS_DIR / f"letter_{letter_id}.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def build_index() -> dict:
    """Rebuild the master index from individual letter files."""
    LETTERS_DIR.mkdir(parents=True, exist_ok=True)
    letters = []

    for path in sorted(LETTERS_DIR.glob("letter_*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            letters.append(data)
        except (json.JSONDecodeError, OSError) as exc:
            print(f"  Warning: skipping {path.name}: {exc}")

    # Sort naturally by letter_id
    def sort_key(d):
        m = re.match(r"(\d+)([a-z]?)", str(d.get("letter_id", "999")))
        return (int(m.group(1)), m.group(2)) if m else (9999, "")

    letters.sort(key=sort_key)

    index = {
        "total_letters": len(letters),
        "letters": letters,
    }
    INDEX_PATH.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    return index


def get_completed_ids() -> set[str]:
    """Return set of letter IDs that have already been transcribed."""
    LETTERS_DIR.mkdir(parents=True, exist_ok=True)
    ids = set()
    for path in LETTERS_DIR.glob("letter_*.json"):
        m = re.match(r"letter_(.+)\.json", path.name)
        if m:
            ids.add(m.group(1))
    return ids


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Transcribe Hanifen family letter scans using Claude."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show letter grouping without calling the API.",
    )
    parser.add_argument(
        "--letters", nargs="+",
        help="Only process specific letter IDs (e.g., 1 2 18a).",
    )
    parser.add_argument(
        "--model", default="claude-sonnet-4-6",
        help="Claude model to use (default: claude-sonnet-4-6).",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Re-transcribe even if letter already has data.",
    )
    parser.add_argument(
        "--workers", type=int, default=5,
        help="Number of parallel API requests (default: 5).",
    )
    parser.add_argument(
        "--list", action="store_true", dest="list_letters",
        help="Just list all discovered letters and their pages.",
    )
    args = parser.parse_args()

    # Discover and group
    if not SCANS_DIR.exists():
        print(f"Error: Scans directory not found: {SCANS_DIR}")
        sys.exit(1)

    letters = group_letters(SCANS_DIR)
    print(f"Found {len(letters)} letters in {SCANS_DIR}/\n")

    # List mode
    if args.list_letters:
        for letter in letters:
            pages_str = ", ".join(f"{p.page_label} ({p.path.name})" for p in letter.pages)
            print(f"  Letter {letter.letter_id}: {len(letter.pages)} pages — {pages_str}")
        return

    # Filter to specific letters if requested
    if args.letters:
        requested = set(args.letters)
        letters = [l for l in letters if l.letter_id in requested]
        if not letters:
            print(f"No matching letters found for: {args.letters}")
            sys.exit(1)

    # Dry run
    if args.dry_run:
        print("DRY RUN — showing letter grouping:\n")
        for letter in letters:
            print(f"  Letter {letter.letter_id} ({len(letter.pages)} pages):")
            for page in letter.pages:
                print(f"    {page.page_order:6.2f}  {page.page_label:20s}  {page.path.name}")
            print()
        print(f"Total: {len(letters)} letters")
        return

    # Check API key
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key or api_key == "your-api-key-here":
        print("Error: Set ANTHROPIC_API_KEY in .env file.")
        sys.exit(1)

    import anthropic
    client = anthropic.Anthropic(api_key=api_key)

    # Determine which letters need processing
    completed = get_completed_ids()
    if not args.force:
        pending = [l for l in letters if l.letter_id not in completed]
        skipped = len(letters) - len(pending)
        if skipped:
            print(f"Skipping {skipped} already-transcribed letters (use --force to redo).")
        letters = pending

    if not letters:
        print("All letters already transcribed! Use --force to re-process.")
        build_index()
        return

    workers = args.workers
    print(f"Transcribing {len(letters)} letters using {args.model} ({workers} parallel workers)...\n")

    success = 0
    errors = 0
    error_ids = []

    def process_one(letter: Letter) -> tuple[str, bool, str]:
        """Process a single letter. Returns (letter_id, ok, message)."""
        try:
            data = transcribe_letter(client, letter, args.model)
            save_letter(letter.letter_id, data)
            return (letter.letter_id, True, "")
        except Exception as exc:
            return (letter.letter_id, False, str(exc))

    done_count = 0
    total = len(letters)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(process_one, l): l for l in letters}
        for future in as_completed(futures):
            letter = futures[future]
            lid, ok, msg = future.result()
            done_count += 1
            if ok:
                success += 1
                print(f"  [{done_count}/{total}] Letter {lid} ({len(letter.pages)} pages) — OK")
            else:
                errors += 1
                error_ids.append(lid)
                print(f"  [{done_count}/{total}] Letter {lid} — ERROR: {msg}")

    # Rebuild master index
    print(f"\nDone: {success} transcribed, {errors} errors.")
    if error_ids:
        print(f"Failed letters: {', '.join(error_ids)}")
        print(f"Re-run with: python transcribe.py --letters {' '.join(error_ids)} --force")
    index = build_index()
    print(f"Master index: {INDEX_PATH} ({index['total_letters']} total letters)")


if __name__ == "__main__":
    main()
