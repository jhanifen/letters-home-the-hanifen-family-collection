#!/usr/bin/env python3
"""
Generate a narrated audiobook from the Hanifen letter collection.
Step 1: Use Claude to write the narration script
Step 2: Use edge-tts to generate audio
"""
import asyncio
import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = ROOT / "data"
INDEX_PATH = DATA_DIR / "index.json"
ANALYSIS_PATH = DATA_DIR / "timeline_analysis.json"
SCRIPT_PATH = DATA_DIR / "audiobook_script.txt"
AUDIO_DIR = ROOT / "site" / "audio"
OUTPUT_MP3 = AUDIO_DIR / "Letters_Home_Audiobook.mp3"

# edge-tts voice — warm, male, American narrator
NARRATOR_VOICE = "en-US-GuyNeural"


SCRIPT_PROMPT = """\
You are writing the narration script for a short audiobook (approximately 4,000–5,000 words, \
which will produce roughly 20–25 minutes of audio when read aloud).

The audiobook is called "Letters Home: The Wartime Correspondence of the Hanifen Brothers" \
and tells the story of the Hanifen family of Des Moines, Iowa through their letters from 1941–1976.

IMPORTANT GUIDELINES:
- Write for the EAR, not the eye. Use short, clear sentences. Avoid parentheticals.
- This is meant to be listened to, so flow and rhythm matter.
- Include direct quotes from the letters — these are the emotional heart of the piece. \
  When quoting, introduce who is speaking and to whom. Read the quotes as they were written, \
  including the rough grammar and spelling — that's what makes them real.
- Use pauses naturally. Insert "[pause]" markers where a beat of silence would feel right.
- Structure it as chapters with the narrator weaving context between letter excerpts.
- The tone should be warm, respectful, and intimate — like Ken Burns narrating a documentary. \
  Let the letters speak for themselves as much as possible.
- End with something that resonates — the arc from young soldiers to old age.

NARRATIVE OVERVIEW:
{narrative}

LIFE CHAPTERS:
{chapters}

HIGHLIGHTS (best excerpts — use many of these):
{highlights}

CHARACTER PROFILES:
{profiles}

KEY LETTER TRANSCRIPTIONS (use direct quotes from these):
{key_letters}

Write the complete narration script now. Use this format:

TITLE: Letters Home

CHAPTER 1: [chapter title]
[narration text with [pause] markers and direct quotes from letters]

CHAPTER 2: [chapter title]
[etc.]

EPILOGUE:
[closing narration]

Write ONLY the script. Make it compelling, emotional, and true to the material.\
"""


def load_data():
    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        index = json.load(f)
    with open(ANALYSIS_PATH, "r", encoding="utf-8") as f:
        analysis = json.load(f)
    return index, analysis


def get_key_letter_texts(index: dict) -> str:
    """Get full transcriptions of the most important letters."""
    # Key letters for the audiobook
    key_ids = {"1", "2", "3", "4", "7", "8", "9", "11", "16", "24", "28",
               "35", "45", "46", "51", "52", "55", "57", "58", "84"}
    texts = []
    for l in index["letters"]:
        if str(l["letter_id"]) in key_ids:
            meta = l.get("metadata", {})
            date = meta.get("date", "undated")
            frm = meta.get("from", "?")[:60]
            to = meta.get("to", "?")[:60]
            texts.append(f"=== Letter {l['letter_id']} ({date}) ===")
            texts.append(f"From: {frm}")
            texts.append(f"To: {to}")
            texts.append(f"Summary: {l.get('summary', '')}")
            texts.append(f"Full text:\n{l.get('full_transcription', '')}")
            texts.append("")
    return "\n".join(texts)


def get_highlights() -> str:
    """Get the highlights we already curated."""
    highlights = [
        {"id": "1", "text": "These chicken shit draft board have deferred every body with a pimple on their butt."},
        {"id": "2", "text": "I'm a big kid now, but right now I feel like crying."},
        {"id": "3", "text": "This Russian situation don't look to good to me, as we are in the hot spot right here. I was playing catch with the Lt. yesterday."},
        {"id": "4", "text": "Her name is Anna, she is really nice compared to this other woman mainly because she is clean, well clean anyway."},
        {"id": "7", "text": "She is going to have chicken for dinner. God help her if she don't. I have had chicken only 3 times since I left home."},
        {"id": "8", "text": "Give him a smoke and he will be your man for anything. They salute us all the time, what a life."},
        {"id": "16", "text": "Bob starts off at 6 AM and goes right thru until 10:30 PM. In about 3 weeks, He will know he is in Hell too. I'll bet a Buck."},
        {"id": "16", "text": "Bob don't get a dam penny while in school, even how to Send him Towels."},
        {"id": "24", "text": "I didn't know what to do exactly, so I asked the German. He handed me my 45 pistol. I said not yet, and put my tractor in 3rd and started plowing through."},
        {"id": "28", "text": "This new bomb might get me home a little quicker I hope. But I don't know."},
        {"id": "28", "text": "Just heard about the Japs wanting to surrender. Hope they do."},
        {"id": "46", "text": "No dance tonight on account of the president's death, sure hated to hear about it."},
        {"id": "51", "text": "I now work for Texaco gasoline making $206.50 a month, not bad for a nut like me."},
        {"id": "52", "text": "I was rudely awakened at 6:30 the yelling of a Dozen guys, yelling gas attack. Somebody said it was Memorial Day. Hell I didn't even know it."},
        {"id": "55", "text": "What are you doing in Korea, running the war all by yourself."},
        {"id": "57", "text": "This is the Day, The Republicans and Eisenhower are Shouting. If you got any Bitching to do, Put it in the Letter. Love Dad"},
        {"id": "84", "text": "ARRIVAL, NAPLES, ITALY: 19 February, 1300 hours. DISTANCE FROM NEW YORK: 4331 MILES. Keep this for me. Bobby"},
        {"id": "1", "text": "P.S. Keep your eyes open for those sneaking red bastards."},
        {"id": "9", "text": "The medicine to help my bones from degenerating has caused me to lose over half of my hair."},
    ]
    return "\n".join(f"Letter {h['id']}: \"{h['text']}\"" for h in highlights)


def generate_script(index: dict, analysis: dict) -> str:
    """Use Claude to write the narration script."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key or api_key == "your-api-key-here":
        raise SystemExit("Set ANTHROPIC_API_KEY in .env")

    import anthropic
    client = anthropic.Anthropic(api_key=api_key)

    chapters_text = ""
    for i, ch in enumerate(analysis.get("life_chapters", []), 1):
        desc = ch.get("description", "") + "\n" + ch.get("description_continued", "")
        chapters_text += f"\nChapter {i}: {ch.get('chapter_title', '')}\n"
        chapters_text += f"Date range: {ch.get('date_range', '')}\n"
        chapters_text += f"{desc}\n"

    profiles_text = "\n".join(
        f"- {p.get('name', '?')}: {p.get('description', '')[:200]}"
        for p in analysis.get("character_profiles", [])[:8]
    )

    prompt = SCRIPT_PROMPT.format(
        narrative=analysis.get("narrative_overview", ""),
        chapters=chapters_text,
        highlights=get_highlights(),
        profiles=profiles_text,
        key_letters=get_key_letter_texts(index),
    )

    print("Writing narration script with Claude...")
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
    print(f" ({len(text.split()):,} words)")

    return text


async def generate_audio(script: str):
    """Convert the script to audio using edge-tts."""
    import edge_tts

    AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    # Clean up the script for TTS
    # Remove chapter headers (we'll add pauses instead)
    lines = script.split("\n")
    tts_text = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("TITLE:"):
            tts_text.append(line.replace("TITLE:", "").strip() + ".")
            tts_text.append("[pause]")
            continue
        if line.startswith("CHAPTER") or line.startswith("EPILOGUE"):
            tts_text.append("[pause]")
            # Extract chapter title
            title = re.sub(r"^(CHAPTER \d+:|EPILOGUE:?)\s*", "", line).strip()
            if title:
                tts_text.append(title + ".")
            tts_text.append("[pause]")
            continue
        tts_text.append(line)

    # Join and process pause markers
    full_text = " ".join(tts_text)
    # Replace [pause] with SSML-like breaks (edge-tts supports this)
    full_text = full_text.replace("[pause]", " ... ")
    # Clean up multiple spaces
    full_text = re.sub(r"\s+", " ", full_text).strip()

    print(f"Generating audio ({len(full_text):,} characters)...")
    print(f"Voice: {NARRATOR_VOICE}")

    communicate = edge_tts.Communicate(full_text, NARRATOR_VOICE, rate="-5%")
    await communicate.save(str(OUTPUT_MP3))

    size_mb = OUTPUT_MP3.stat().st_size / (1024 * 1024)
    print(f"\nAudiobook saved: {OUTPUT_MP3}")
    print(f"  File size: {size_mb:.1f} MB")


def main():
    index, analysis = load_data()

    # Step 1: Generate or load script
    if SCRIPT_PATH.exists():
        print(f"Loading existing script from {SCRIPT_PATH}")
        script = SCRIPT_PATH.read_text(encoding="utf-8")
    else:
        script = generate_script(index, analysis)
        SCRIPT_PATH.write_text(script, encoding="utf-8")
        print(f"Script saved to {SCRIPT_PATH}")

    word_count = len(script.split())
    est_minutes = word_count / 150  # ~150 words per minute for narration
    print(f"Script: {word_count:,} words (~{est_minutes:.0f} minutes)")

    # Step 2: Generate audio
    asyncio.run(generate_audio(script))


if __name__ == "__main__":
    main()
