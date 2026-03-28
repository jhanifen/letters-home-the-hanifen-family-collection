#!/usr/bin/env python3
"""
Generate audiobook using ElevenLabs TTS.

Usage:
  python generate_audiobook_11labs.py
  python generate_audiobook_11labs.py --voice "George"
  python generate_audiobook_11labs.py --list-voices
"""
import argparse
import os
import re
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = ROOT / "data"
SCRIPT_PATH = DATA_DIR / "audiobook_script_polished.txt"
AUDIO_DIR = ROOT / "site" / "audio"
OUTPUT_MP3 = AUDIO_DIR / "Letters_Home_ElevenLabs.mp3"

# Pre-built ElevenLabs voice IDs (no API call needed)
VOICE_MAP = {
    "Adam": "pNInz6obpgDQGcFmaJgB",
    "Antoni": "ErXwobaYiN019PkySvjV",
    "Arnold": "VR6AewLTigWG4xSOukaG",
    "Bill": "pqHfZKP75CvOlQylNhV4",
    "Brian": "nPczCjzI2devNBz1zQrb",
    "Charlie": "IKne3meq5aSn9XLyUdCD",
    "Chris": "iP95p4xoKVk53GoZ742B",
    "Daniel": "onwK4e9ZLuTAKqWW03F9",
    "Dave": "CYw3kZ02Hs0563khs1Fj",
    "George": "JBFqnCBsd6RMkjVDRZzb",
    "James": "ZQe5CZNOzWyzPSCn5a3c",
    "Josh": "TxGEqnHWrfWFTfGW9XjX",
    "Liam": "TX3LPaxmHKxFdv7VOQHJ",
    "Marcus": "1RQKlVrMm2npvWv87pfm",
    "Will": "bIHbv24MWmeRgasZH58o",
}

# Good narrator voices for documentary style:
# George — British, deep, authoritative (Ken Burns feel)
# Daniel — British, warm, narrative
# Brian — American, deep, warm narrator
# Bill — American, warm storyteller
# Adam — American, deep, clear


def clean_script_for_tts(text: str) -> str:
    """Clean the script for TTS — remove markdown, convert pauses."""
    lines = text.split("\n")
    output = []

    for line in lines:
        line = line.strip()

        # Skip markdown formatting lines
        if line.startswith("---"):
            continue
        if line.startswith("*A narration script"):
            continue
        if line == "*End.*":
            continue
        if line.startswith('*"Letters Home:'):
            continue

        # Chapter/section headers — add pauses and speak the title
        if line.startswith("# "):
            output.append("")
            output.append(line.lstrip("# ").strip())
            output.append("")
            continue
        if line.startswith("## "):
            output.append("")
            output.append("")
            title = line.lstrip("# ").strip()
            output.append(title)
            output.append("")
            continue
        if line.startswith("### "):
            subtitle = line.lstrip("# ").strip()
            output.append(subtitle)
            output.append("")
            continue

        # Convert [pause] and [long pause]
        line = line.replace("[long pause]", "")
        line = line.replace("[pause]", "")

        # Remove italic markers but keep the text
        line = line.replace("*", "")

        # Skip empty lines (will become natural pauses)
        if not line:
            output.append("")
            continue

        output.append(line)

    # Join and clean up excessive blank lines
    result = "\n".join(output)
    result = re.sub(r"\n{4,}", "\n\n\n", result)
    return result.strip()


def main():
    parser = argparse.ArgumentParser(description="Generate audiobook with ElevenLabs")
    parser.add_argument("--voice", default="Brian",
                        help=f"Voice name. Options: {', '.join(sorted(VOICE_MAP.keys()))}")
    parser.add_argument("--list-voices", action="store_true",
                        help="List available voices and exit")
    parser.add_argument("--model", default="eleven_multilingual_v2",
                        help="ElevenLabs model (default: eleven_multilingual_v2)")
    args = parser.parse_args()

    if args.list_voices:
        print("Available voices:")
        for name in sorted(VOICE_MAP.keys()):
            marker = " <-- recommended" if name in ("Brian", "George", "Daniel", "Bill") else ""
            print(f"  {name}{marker}")
        return

    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        print("Error: Set ELEVENLABS_API_KEY in .env")
        return

    voice_name = args.voice
    voice_id = VOICE_MAP.get(voice_name)
    if not voice_id:
        print(f"Unknown voice '{voice_name}'. Available: {', '.join(sorted(VOICE_MAP.keys()))}")
        return

    # Load and clean script
    script = SCRIPT_PATH.read_text(encoding="utf-8")
    tts_text = clean_script_for_tts(script)

    print(f"Script: {len(tts_text):,} characters")
    print(f"Voice: {voice_name} ({voice_id})")
    print(f"Model: {args.model}")

    AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    from elevenlabs import ElevenLabs

    client = ElevenLabs(api_key=api_key)

    # Split into chunks at paragraph boundaries (max ~8000 chars each)
    MAX_CHUNK = 8000
    paragraphs = tts_text.split("\n\n")
    chunks = []
    current_chunk = ""

    for para in paragraphs:
        if len(current_chunk) + len(para) + 2 > MAX_CHUNK and current_chunk:
            chunks.append(current_chunk.strip())
            current_chunk = para
        else:
            current_chunk += "\n\n" + para if current_chunk else para
    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    print(f"Split into {len(chunks)} chunks")
    print("Generating audio (this may take a few minutes)...")

    # Generate audio for each chunk
    audio_parts = []
    for i, chunk in enumerate(chunks, 1):
        print(f"  Chunk {i}/{len(chunks)} ({len(chunk):,} chars)...", end=" ", flush=True)
        audio_generator = client.text_to_speech.convert(
            voice_id=voice_id,
            text=chunk,
            model_id=args.model,
            output_format="mp3_44100_128",
        )
        chunk_path = AUDIO_DIR / f"_chunk_{i:02d}.mp3"
        with open(chunk_path, "wb") as f:
            for audio_chunk in audio_generator:
                f.write(audio_chunk)
        audio_parts.append(chunk_path)
        print("OK")

    # Concatenate all chunks
    print("Combining audio chunks...")
    with open(OUTPUT_MP3, "wb") as out:
        for part_path in audio_parts:
            out.write(part_path.read_bytes())

    # Clean up chunk files
    for part_path in audio_parts:
        part_path.unlink()

    size_mb = OUTPUT_MP3.stat().st_size / (1024 * 1024)
    print(f"\nAudiobook saved: {OUTPUT_MP3}")
    print(f"  File size: {size_mb:.1f} MB")
    print(f"  Voice: {voice_name}")
    print(f"\nTo try a different voice:")
    print(f"  python generate_audiobook_11labs.py --voice George")
    print(f"  python generate_audiobook_11labs.py --list-voices")


if __name__ == "__main__":
    main()
