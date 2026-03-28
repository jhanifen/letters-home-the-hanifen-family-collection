# Letters Home — The Hanifen Family Collection

A collection of ~84 handwritten family letters spanning the late 1930s through the mid-1940s, digitized and presented as an interactive web experience, a printed book, and an audiobook.

The letters follow Bob Hanifen from leaving home through college and WWII military service, written to and from his family — his brothers Jim and John, and their father James Sr. They were preserved for decades and delivered by Bob's son, Bob Jr., to be digitized for the family.

## The Site

**[View the live site](https://bobbyhanifen.com)** (or open `site/index.html` locally)

The interactive website lets you browse letters chronologically, search by keyword, explore a timeline, view original scans alongside transcriptions, and see family photographs.

## How It Was Built

This project was built almost entirely with AI assistance using [Claude Code](https://claude.ai/claude-code) and the [Claude API](https://docs.anthropic.com/en/docs/overview). The pipeline:

1. **Scan** — 304 page images were scanned from the original handwritten letters
2. **Transcribe** — Claude's vision model read each handwritten page and produced structured JSON with full text, metadata (sender, recipient, date, location), topics, and summaries
3. **Analyze** — Claude built a narrative timeline, inferred missing dates, and identified the overall story arc across all 84 letters
4. **Generate** — The structured data was used to produce:
   - An interactive single-page website (`site/index.html`)
   - A typeset PDF memoir with embedded scans (`Letters_Home_Hanifen.pdf`)
   - A narrated audiobook using ElevenLabs text-to-speech

## Project Structure

```
├── scripts/                  # Python pipeline scripts
│   ├── transcribe.py         # Scan → structured JSON via Claude Vision
│   ├── analyze_timeline.py   # Build narrative timeline across all letters
│   ├── apply_date_estimates.py  # Apply inferred dates back to letter data
│   ├── analyze_photos.py     # Catalog family photographs with AI
│   ├── generate_web.py       # Generate the interactive HTML site
│   ├── generate_book.py      # Generate the PDF memoir (WeasyPrint)
│   ├── generate_audiobook.py # Generate audiobook script + edge-tts audio
│   ├── generate_audiobook_11labs.py  # Alternative: ElevenLabs TTS
│   └── polish_script.py      # Editorial polish on the audiobook narration
├── data/                     # Processed letter data
│   ├── index.json            # Master index of all letters with metadata
│   ├── letters/              # Individual letter JSON files (letter_1.json–letter_84.json)
│   ├── timeline_analysis.json
│   ├── photo_manifest.json
│   └── audiobook_script*.txt
├── site/                     # Generated website output
│   ├── index.html            # Interactive web experience
│   ├── about.html            # About the project
│   ├── favicon.svg / .png
│   ├── Letters_Home_Hanifen.html  # Print-formatted HTML
│   ├── Letters_Home_Hanifen.pdf   # (gitignored, ~1GB)
│   └── audio/                     # (gitignored, ~41MB)
├── BobScans/                 # Original scanned images (Git LFS, ~325MB)
│   ├── letter*.jpg            # ~300 letter page scans
│   └── photos/               # ~100 family photographs
├── requirements.txt
└── .env                      # (gitignored) API keys
```

## Running the Pipeline

### Prerequisites

- Python 3.10+
- An [Anthropic API key](https://console.anthropic.com/)
- (Optional) An [ElevenLabs API key](https://elevenlabs.io/) for premium audiobook voices

### Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Add your API keys
```

### Pipeline Steps

The scripts are designed to run in order. Each reads from `data/` and writes its output there (or to `site/`).

```bash
# 1. Transcribe scanned letters (requires images in BobScans/)
python scripts/transcribe.py

# 2. Analyze the timeline and infer missing dates
python scripts/analyze_timeline.py
python scripts/apply_date_estimates.py

# 3. Catalog photographs
python scripts/analyze_photos.py

# 4. Generate outputs
python scripts/generate_web.py        # → site/index.html
python scripts/generate_book.py       # → site/Letters_Home_Hanifen.pdf
python scripts/generate_audiobook.py  # → site/audio/

# Optional: use ElevenLabs for higher-quality voice
python scripts/generate_audiobook_11labs.py
```

## Dependencies

- **[anthropic](https://github.com/anthropics/anthropic-sdk-python)** — Claude API client for transcription and analysis
- **[Pillow](https://python-pillow.org/)** — Image processing for scan preparation
- **[python-dotenv](https://github.com/theskumar/python-dotenv)** — Environment variable management
- **[WeasyPrint](https://weasyprint.org/)** — PDF generation (needed for `generate_book.py`)
- **[edge-tts](https://github.com/rany2/edge-tts)** — Free TTS option (needed for `generate_audiobook.py`)

## Large Files

The original letter scans and family photos (~325MB) are stored via [Git LFS](https://git-lfs.github.com/). Install Git LFS before cloning to pull them automatically.

The following generated outputs are not committed due to size:

| What | Size | How to Regenerate |
|------|------|-------------------|
| `site/Letters_Home_Hanifen.pdf` — the typeset PDF | ~1 GB | `python scripts/generate_book.py` |
| `site/audio/` — audiobook MP3 files | ~41 MB | `python scripts/generate_audiobook.py` |

## License

This is a personal family history project. The letter content, scans, and photographs are family materials shared here for preservation and educational purposes. The code is available under the [MIT License](LICENSE).
