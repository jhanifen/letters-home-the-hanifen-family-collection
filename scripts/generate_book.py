#!/usr/bin/env python3
"""
Generate a professional historical memoir PDF from the Hanifen letter collection.

Usage:
  DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib python generate_book.py
"""
import json
import os
import re
import html as html_module
from pathlib import Path

os.environ.setdefault("DYLD_FALLBACK_LIBRARY_PATH", "/opt/homebrew/lib")

from weasyprint import HTML
from weasyprint.text.fonts import FontConfiguration

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = ROOT / "data"
SCANS_DIR = (ROOT / "BobScans").resolve()
INDEX_PATH = DATA_DIR / "index.json"
ANALYSIS_PATH = DATA_DIR / "timeline_analysis.json"
OUTPUT_PATH = ROOT / "site" / "Letters_Home_Hanifen.pdf"
HTML_PATH = ROOT / "site" / "Letters_Home_Hanifen.html"

# ---------------------------------------------------------------------------
# Book dimensions: 8.5 x 11 inches (US Letter — good for showing scans)
# ---------------------------------------------------------------------------
PAGE_WIDTH = "8.5in"
PAGE_HEIGHT = "11in"

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
def load_data():
    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        index = json.load(f)
    with open(ANALYSIS_PATH, "r", encoding="utf-8") as f:
        analysis = json.load(f)
    return index, analysis


def sort_key(letter_id: str) -> tuple:
    m = re.match(r"(\d+)([a-z]?)", str(letter_id))
    return (int(m.group(1)), m.group(2)) if m else (9999, "")


def get_chrono_order(analysis: dict) -> list[dict]:
    """Get letters in chronological order from analysis."""
    return analysis.get("chronological_order", [])


def get_chapter_letters(chapter: dict, letters_by_id: dict, chrono: list[dict]) -> list[dict]:
    """Get letters for a chapter, in chronological order."""
    key_ids = set(str(k) for k in chapter.get("key_letters", []))
    # Get chronological entries that match this chapter
    chrono_in_chapter = [c for c in chrono if str(c.get("letter_id", "")) in key_ids]
    # Build full letter data in chrono order
    result = []
    seen = set()
    for entry in chrono_in_chapter:
        lid = str(entry.get("letter_id", ""))
        if lid in letters_by_id and lid not in seen:
            result.append(letters_by_id[lid])
            seen.add(lid)
    # Add any key letters not in chrono order
    for lid in chapter.get("key_letters", []):
        lid = str(lid)
        if lid not in seen and lid in letters_by_id:
            result.append(letters_by_id[lid])
            seen.add(lid)
    return result


def esc(text: str) -> str:
    """HTML-escape text."""
    if not text:
        return ""
    return html_module.escape(str(text))


def format_date_display(meta: dict) -> str:
    """Format a human-readable date with approximate marker."""
    date = meta.get("date", "")
    if date and date != "NO DATE":
        result = esc(date)
        if meta.get("date_is_approximate"):
            result += ' <span class="approximate">[estimated]</span>'
        return result
    estimated = meta.get("date_estimated", "")
    if estimated:
        return f'{esc(estimated)} <span class="approximate">[estimated]</span>'
    return '<span class="undated">Date unknown</span>'


def clean_sender(raw: str) -> str:
    """Extract just the name from verbose sender fields."""
    if not raw:
        return "Unknown"
    # Take text before the first dash or parenthetical
    name = re.split(r"\s*[—–\-]\s*", raw)[0]
    name = re.split(r"\s*\(", name)[0]
    # Remove rank prefixes for cleaner display
    name = re.sub(r"^(Pvt\.|PFC|Cpl\.|Sgt\.|Lt\.|Capt\.|Col\.)\s*", "", name).strip()
    return name if name else raw[:50]


def get_scan_files(letter: dict) -> list[str]:
    """Get list of scan file paths for a letter."""
    pages = letter.get("pages", [])
    files = []
    for page in pages:
        source = page.get("source_file", "")
        if source:
            # Handle both full paths and just filenames
            fname = Path(source).name
            full_path = SCANS_DIR / fname
            if full_path.exists():
                files.append(str(full_path))
    return files


def nl2br(text: str) -> str:
    """Convert newlines to <br> tags, preserving paragraph breaks."""
    if not text:
        return ""
    text = esc(text)
    # Double newlines become paragraph breaks
    text = re.sub(r'\n\n+', '</p><p class="transcript-para">', text)
    # Single newlines become line breaks
    text = text.replace('\n', '<br>\n')
    return f'<p class="transcript-para">{text}</p>'


# ---------------------------------------------------------------------------
# CSS Stylesheet — Ken Burns historical memoir aesthetic
# ---------------------------------------------------------------------------
CSS = f"""
@import url('https://fonts.googleapis.com/css2?family=EB+Garamond:ital,wght@0,400;0,500;0,600;0,700;1,400;1,500&family=Cormorant+Garamond:ital,wght@0,300;0,400;0,500;0,600;1,300;1,400&family=Spectral:ital,wght@0,300;0,400;0,500;1,300;1,400&display=swap');

@page {{
    size: {PAGE_WIDTH} {PAGE_HEIGHT};
    margin: 0.9in 1in 1in 1in;

    @bottom-center {{
        content: counter(page);
        font-family: 'EB Garamond', 'Georgia', serif;
        font-size: 10pt;
        color: #6b5b4f;
    }}
}}

@page :first {{
    margin: 0;
    @bottom-center {{ content: none; }}
}}

@page cover {{
    margin: 0;
    @bottom-center {{ content: none; }}
}}

@page chapter-start {{
    @bottom-center {{ content: none; }}
}}

@page blank {{
    @bottom-center {{ content: none; }}
}}

/* ---- Base ---- */
* {{ box-sizing: border-box; }}

body {{
    font-family: 'EB Garamond', 'Georgia', 'Times New Roman', serif;
    font-size: 11pt;
    line-height: 1.55;
    color: #2c2416;
    background: #faf6f0;
}}

/* ---- Cover Page ---- */
.cover-page {{
    page: cover;
    page-break-after: always;
    width: {PAGE_WIDTH};
    height: {PAGE_HEIGHT};
    background: #1a1510;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    text-align: center;
    padding: 2in 1.5in;
    position: relative;
}}

.cover-page::before {{
    content: "";
    position: absolute;
    top: 0.6in;
    left: 0.8in;
    right: 0.8in;
    bottom: 0.6in;
    border: 1px solid #8b7355;
    opacity: 0.4;
}}

.cover-title {{
    font-family: 'Cormorant Garamond', 'EB Garamond', serif;
    font-size: 42pt;
    font-weight: 300;
    color: #d4c5a9;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    margin-bottom: 0.15in;
    line-height: 1.15;
}}

.cover-subtitle {{
    font-family: 'EB Garamond', serif;
    font-size: 15pt;
    font-style: italic;
    color: #a89578;
    margin-bottom: 0.6in;
    letter-spacing: 0.04em;
}}

.cover-rule {{
    width: 2.5in;
    height: 1px;
    background: #8b7355;
    margin: 0 auto 0.5in auto;
    opacity: 0.6;
}}

.cover-author {{
    font-family: 'Cormorant Garamond', serif;
    font-size: 13pt;
    font-weight: 400;
    color: #a89578;
    letter-spacing: 0.15em;
    text-transform: uppercase;
}}

.cover-years {{
    font-family: 'EB Garamond', serif;
    font-size: 12pt;
    color: #8b7355;
    margin-top: 0.4in;
    letter-spacing: 0.08em;
}}

/* ---- Half Title / Frontmatter ---- */
.half-title-page {{
    page-break-after: always;
    text-align: center;
    padding-top: 3.5in;
}}

.half-title {{
    font-family: 'Cormorant Garamond', serif;
    font-size: 28pt;
    font-weight: 300;
    color: #4a3f30;
    letter-spacing: 0.1em;
    text-transform: uppercase;
}}

/* ---- Dedication ---- */
.dedication-page {{
    page-break-after: always;
    text-align: center;
    padding-top: 3in;
}}

.dedication-text {{
    font-style: italic;
    font-size: 13pt;
    color: #5a4e3a;
    line-height: 1.8;
    max-width: 4in;
    margin: 0 auto;
}}

/* ---- Table of Contents ---- */
.toc-page {{
    page-break-after: always;
    padding-top: 1.2in;
}}

.toc-title {{
    font-family: 'Cormorant Garamond', serif;
    font-size: 22pt;
    font-weight: 400;
    color: #4a3f30;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    text-align: center;
    margin-bottom: 0.6in;
}}

.toc-chapter {{
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    padding: 0.12in 0;
    border-bottom: 1px dotted #c5b89a;
}}

.toc-chapter-title {{
    font-size: 12pt;
    color: #3a3020;
    font-weight: 500;
}}

.toc-chapter-dates {{
    font-size: 10pt;
    font-style: italic;
    color: #7a6b55;
    margin-left: 0.3in;
    white-space: nowrap;
}}

/* ---- Narrative Overview ---- */
.overview-page {{
    page-break-after: always;
    padding-top: 1in;
}}

.overview-title {{
    font-family: 'Cormorant Garamond', serif;
    font-size: 22pt;
    font-weight: 400;
    color: #4a3f30;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    text-align: center;
    margin-bottom: 0.2in;
}}

.overview-rule {{
    width: 1.5in;
    height: 1px;
    background: #b5a68a;
    margin: 0 auto 0.5in auto;
}}

.overview-text {{
    font-size: 11.5pt;
    line-height: 1.65;
    color: #3a3020;
    text-align: justify;
    hyphens: auto;
}}

.overview-text p {{
    margin-bottom: 0.18in;
    text-indent: 0.3in;
}}

.overview-text p:first-child {{
    text-indent: 0;
}}

/* ---- Chapter Title Pages ---- */
.chapter-title-page {{
    page: chapter-start;
    page-break-before: right;
    page-break-after: always;
    padding-top: 2.5in;
    text-align: center;
}}

.chapter-number {{
    font-family: 'Cormorant Garamond', serif;
    font-size: 11pt;
    font-weight: 400;
    color: #8b7355;
    text-transform: uppercase;
    letter-spacing: 0.25em;
    margin-bottom: 0.25in;
}}

.chapter-name {{
    font-family: 'Cormorant Garamond', serif;
    font-size: 26pt;
    font-weight: 400;
    color: #3a3020;
    line-height: 1.25;
    margin-bottom: 0.2in;
}}

.chapter-dates {{
    font-family: 'EB Garamond', serif;
    font-size: 12pt;
    font-style: italic;
    color: #8b7355;
    margin-bottom: 0.4in;
}}

.chapter-rule {{
    width: 1.5in;
    height: 1px;
    background: #b5a68a;
    margin: 0 auto 0.5in auto;
}}

.chapter-description {{
    font-size: 11pt;
    line-height: 1.6;
    color: #4a3f30;
    text-align: justify;
    hyphens: auto;
    max-width: 5.5in;
    margin: 0 auto;
}}

.chapter-description p {{
    margin-bottom: 0.15in;
}}

/* ---- Letter Entries ---- */
.letter-entry {{
    page-break-before: always;
    padding-top: 0.2in;
}}

.letter-header {{
    text-align: center;
    margin-bottom: 0.4in;
    padding-bottom: 0.25in;
    border-bottom: 1px solid #d4c5a9;
}}

.letter-date {{
    font-family: 'Cormorant Garamond', serif;
    font-size: 18pt;
    font-weight: 400;
    color: #3a3020;
    margin-bottom: 0.08in;
}}

.letter-correspondents {{
    font-size: 11pt;
    font-style: italic;
    color: #6b5b4f;
    margin-bottom: 0.06in;
}}

.letter-location {{
    font-size: 10pt;
    color: #8b7355;
}}

.approximate {{
    font-size: 8pt;
    font-style: italic;
    color: #a0876b;
    vertical-align: super;
}}

.undated {{
    font-style: italic;
    color: #a0876b;
}}

/* ---- Letter Metadata Box ---- */
.letter-meta-box {{
    background: #f0ebe2;
    border-left: 3px solid #b5a68a;
    padding: 0.2in 0.25in;
    margin-bottom: 0.35in;
    font-size: 9.5pt;
    line-height: 1.5;
    color: #5a4e3a;
}}

.letter-meta-box .meta-label {{
    font-weight: 600;
    color: #4a3f30;
    font-variant: small-caps;
    letter-spacing: 0.03em;
}}

.letter-meta-box .meta-row {{
    margin-bottom: 0.04in;
}}

/* ---- Scan Images ---- */
.letter-scans {{
    margin-bottom: 0.4in;
}}

.scan-group {{
    text-align: center;
    margin-bottom: 0.3in;
}}

.scan-image {{
    max-width: 100%;
    max-height: 7.5in;
    border: 1px solid #d4c5a9;
    box-shadow: 2px 2px 8px rgba(0,0,0,0.08);
}}

.scan-caption {{
    font-size: 8.5pt;
    font-style: italic;
    color: #8b7355;
    margin-top: 0.06in;
}}

.scan-page-break {{
    page-break-before: always;
}}

/* ---- Transcription ---- */
.transcription-section {{
    page-break-before: always;
}}

.transcription-label {{
    font-family: 'Cormorant Garamond', serif;
    font-size: 13pt;
    font-weight: 400;
    color: #6b5b4f;
    text-transform: uppercase;
    letter-spacing: 0.15em;
    text-align: center;
    margin-bottom: 0.15in;
}}

.transcription-rule {{
    width: 1in;
    height: 1px;
    background: #c5b89a;
    margin: 0 auto 0.3in auto;
}}

.transcript-para {{
    font-size: 11pt;
    line-height: 1.6;
    color: #3a3020;
    text-align: justify;
    hyphens: auto;
    margin-bottom: 0.12in;
}}

/* ---- Summary Box ---- */
.letter-summary {{
    background: #f5f0e8;
    padding: 0.2in 0.3in;
    margin-top: 0.3in;
    border-top: 1px solid #d4c5a9;
    border-bottom: 1px solid #d4c5a9;
}}

.summary-label {{
    font-size: 9pt;
    font-weight: 600;
    color: #6b5b4f;
    font-variant: small-caps;
    letter-spacing: 0.06em;
    margin-bottom: 0.06in;
}}

.summary-text {{
    font-size: 10pt;
    font-style: italic;
    line-height: 1.55;
    color: #4a3f30;
}}

/* ---- Historical Context callout ---- */
.historical-note {{
    font-size: 9.5pt;
    font-style: italic;
    color: #6b5b4f;
    margin-top: 0.2in;
    padding-left: 0.2in;
    border-left: 2px solid #c5b89a;
}}

/* ---- People & Places appendix ---- */
.appendix-title {{
    font-family: 'Cormorant Garamond', serif;
    font-size: 22pt;
    font-weight: 400;
    color: #4a3f30;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    text-align: center;
    margin-bottom: 0.15in;
    padding-top: 1in;
}}

.appendix-rule {{
    width: 1.5in;
    height: 1px;
    background: #b5a68a;
    margin: 0 auto 0.5in auto;
}}

.profile-entry {{
    margin-bottom: 0.3in;
}}

.profile-name {{
    font-size: 13pt;
    font-weight: 600;
    color: #3a3020;
    margin-bottom: 0.04in;
}}

.profile-role {{
    font-size: 10pt;
    font-style: italic;
    color: #6b5b4f;
    margin-bottom: 0.06in;
}}

.profile-desc {{
    font-size: 10pt;
    color: #4a3f30;
    line-height: 1.5;
}}

/* ---- Colophon ---- */
.colophon {{
    page-break-before: always;
    text-align: center;
    padding-top: 3in;
    font-size: 9pt;
    color: #8b7355;
    line-height: 1.8;
}}
"""


# ---------------------------------------------------------------------------
# HTML generation
# ---------------------------------------------------------------------------
def build_cover() -> str:
    return f"""
    <div class="cover-page">
        <div class="cover-title">Letters Home</div>
        <div class="cover-subtitle">The Wartime Correspondence of the Hanifen Brothers</div>
        <div class="cover-rule"></div>
        <div class="cover-author">The Hanifen Family Collection</div>
        <div class="cover-years">1941 &mdash; 1976</div>
    </div>
    """


def build_half_title() -> str:
    return """
    <div class="half-title-page">
        <div class="half-title">Letters Home</div>
    </div>
    """


def build_dedication() -> str:
    return """
    <div class="dedication-page">
        <div class="dedication-text">
            For Bob, Jim, and John Hanifen&mdash;<br>
            and for the father who waited for their letters home.
        </div>
    </div>
    """


def build_toc(chapters: list[dict]) -> str:
    entries = ""
    for i, ch in enumerate(chapters, 1):
        title = esc(ch.get("chapter_title", f"Chapter {i}"))
        dates = esc(ch.get("date_range", ""))
        entries += f"""
        <div class="toc-chapter">
            <span class="toc-chapter-title">Chapter {i}: {title}</span>
            <span class="toc-chapter-dates">{dates}</span>
        </div>
        """

    return f"""
    <div class="toc-page">
        <div class="toc-title">Contents</div>
        {entries}
        <div class="toc-chapter" style="margin-top: 0.2in;">
            <span class="toc-chapter-title">Appendix: The People in These Letters</span>
            <span class="toc-chapter-dates"></span>
        </div>
    </div>
    """


def build_overview(narrative: str) -> str:
    paragraphs = narrative.split("\n\n")
    body = "\n".join(f"<p>{esc(p.strip())}</p>" for p in paragraphs if p.strip())
    return f"""
    <div class="overview-page">
        <div class="overview-title">Foreword</div>
        <div class="overview-rule"></div>
        <div class="overview-text">
            {body}
        </div>
    </div>
    """


def build_chapter(chapter: dict, chapter_num: int, letters: list[dict]) -> str:
    title = esc(chapter.get("chapter_title", f"Chapter {chapter_num}"))
    dates = esc(chapter.get("date_range", ""))

    # Combine description fields
    desc_parts = []
    for key in ("description", "description_continued"):
        text = chapter.get(key, "")
        if text:
            desc_parts.append(text)
    desc_html = "\n".join(f"<p>{esc(p.strip())}</p>" for part in desc_parts for p in part.split("\n\n") if p.strip())

    # Chapter title page
    html = f"""
    <div class="chapter-title-page">
        <div class="chapter-number">Chapter {chapter_num}</div>
        <div class="chapter-name">{title}</div>
        <div class="chapter-dates">{dates}</div>
        <div class="chapter-rule"></div>
        <div class="chapter-description">
            {desc_html}
        </div>
    </div>
    """

    # Individual letters
    for letter in letters:
        html += build_letter_entry(letter)

    return html


def build_letter_entry(letter: dict) -> str:
    meta = letter.get("metadata", {})
    lid = letter.get("letter_id", "?")

    # Header info
    date_html = format_date_display(meta)
    sender = clean_sender(meta.get("from", "Unknown"))
    recipient = clean_sender(meta.get("to", "Unknown"))
    location = meta.get("location_written_from", "")

    html = f"""
    <div class="letter-entry">
        <div class="letter-header">
            <div class="letter-date">{date_html}</div>
            <div class="letter-correspondents">From {esc(sender)} to {esc(recipient)}</div>
            {"<div class='letter-location'>" + esc(location) + "</div>" if location and location != "null" else ""}
        </div>
    """

    # Metadata box
    topics = meta.get("topics", [])
    people = meta.get("people_mentioned", [])
    hist = meta.get("historical_context", "")
    mood = meta.get("mood_tone", "")

    meta_rows = ""
    if topics:
        meta_rows += f'<div class="meta-row"><span class="meta-label">Topics:</span> {esc(", ".join(topics[:8]))}</div>'
    if mood and mood != "null":
        meta_rows += f'<div class="meta-row"><span class="meta-label">Tone:</span> {esc(mood)}</div>'
    if meta.get("postmark") and meta["postmark"] != "null":
        meta_rows += f'<div class="meta-row"><span class="meta-label">Postmark:</span> {esc(meta["postmark"])}</div>'
    if meta.get("envelope_notes") and meta["envelope_notes"] != "null":
        notes = meta["envelope_notes"]
        if len(notes) > 200:
            notes = notes[:200] + "..."
        meta_rows += f'<div class="meta-row"><span class="meta-label">Envelope:</span> {esc(notes)}</div>'

    if meta_rows:
        html += f'<div class="letter-meta-box">{meta_rows}</div>'

    # Scan images — first scan inline, rest on new pages
    scan_files = get_scan_files(letter)
    if scan_files:
        html += '<div class="letter-scans">'
        for i, scan_path in enumerate(scan_files):
            page_info = letter.get("pages", [{}])
            label = page_info[i].get("page_label", f"Page {i+1}") if i < len(page_info) else f"Page {i+1}"

            if i > 0:
                html += '<div class="scan-page-break"></div>'

            html += f"""
            <div class="scan-group">
                <img class="scan-image" src="file://{scan_path}" alt="Letter {lid} - {esc(label)}">
                <div class="scan-caption">Letter {esc(str(lid))} &mdash; {esc(label)}</div>
            </div>
            """
        html += '</div>'

    # Transcription
    full_text = letter.get("full_transcription", "")
    if full_text:
        html += f"""
        <div class="transcription-section">
            <div class="transcription-label">Transcription</div>
            <div class="transcription-rule"></div>
            {nl2br(full_text)}
        </div>
        """

    # Summary
    summary = letter.get("summary", "")
    if summary:
        html += f"""
        <div class="letter-summary">
            <div class="summary-label">Editor&rsquo;s Note</div>
            <div class="summary-text">{esc(summary)}</div>
        </div>
        """

    # Historical context
    if hist and hist != "null" and len(str(hist)) > 10:
        html += f"""
        <div class="historical-note">
            <strong>Historical Context:</strong> {esc(hist)}
        </div>
        """

    html += "</div>"  # close letter-entry
    return html


def build_appendix_people(profiles: list[dict]) -> str:
    html = """
    <div style="page-break-before: always;">
        <div class="appendix-title">The People in These Letters</div>
        <div class="appendix-rule"></div>
    """

    for profile in profiles:
        name = esc(profile.get("name", "Unknown"))
        aliases = profile.get("aliases", [])
        role = esc(profile.get("role", ""))
        desc = esc(profile.get("description", ""))
        alias_str = f' <span style="font-size:9pt;color:#8b7355;">({esc(", ".join(aliases[:5]))})</span>' if aliases else ""

        html += f"""
        <div class="profile-entry">
            <div class="profile-name">{name}{alias_str}</div>
            <div class="profile-role">{role}</div>
            <div class="profile-desc">{desc}</div>
        </div>
        """

    html += "</div>"
    return html


def build_colophon() -> str:
    return """
    <div class="colophon">
        <p><em>Letters Home: The Wartime Correspondence of the Hanifen Brothers</em></p>
        <p>Original letters from the collection of Bob Hanifen Jr.</p>
        <p>Transcribed and compiled with the assistance of artificial intelligence.</p>
        <p style="margin-top: 0.3in;">&bull;</p>
        <p style="margin-top: 0.3in; font-size: 8pt;">
            Letters were transcribed using Claude (Anthropic) from original scanned documents.<br>
            Dates marked [estimated] were inferred from contextual evidence within the letters.<br>
            Every effort has been made to preserve the original text faithfully.
        </p>
    </div>
    """


def generate_html(index: dict, analysis: dict) -> str:
    letters = index.get("letters", [])
    letters_by_id = {str(l["letter_id"]): l for l in letters}
    chapters = analysis.get("life_chapters", [])
    profiles = analysis.get("character_profiles", [])
    narrative = analysis.get("narrative_overview", "")
    chrono = get_chrono_order(analysis)

    # Track which letters are placed in chapters
    placed = set()

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <style>{CSS}</style>
</head>
<body>
"""

    # Front matter
    html += build_cover()
    html += build_half_title()
    html += build_dedication()
    html += build_toc(chapters)
    html += build_overview(narrative)

    # Chapters with their letters
    for i, chapter in enumerate(chapters, 1):
        chapter_letters = get_chapter_letters(chapter, letters_by_id, chrono)
        for l in chapter_letters:
            placed.add(str(l["letter_id"]))
        html += build_chapter(chapter, i, chapter_letters)

    # Any letters not assigned to chapters — put in an "Additional Letters" section
    unplaced = [l for l in letters if str(l["letter_id"]) not in placed]
    if unplaced:
        # Sort by date
        def date_sort(l):
            d = l.get("metadata", {}).get("date_normalized", "") or "9999"
            return d
        unplaced.sort(key=date_sort)

        additional_chapter = {
            "chapter_title": "Additional Correspondence",
            "date_range": "Various dates",
            "description": "The following letters, while not featured in the main narrative chapters, form part of the broader tapestry of the Hanifen family's correspondence. Each adds its own thread to the family story.",
        }
        html += build_chapter(additional_chapter, len(chapters) + 1, unplaced)

    # Appendix
    if profiles:
        html += build_appendix_people(profiles)

    # Colophon
    html += build_colophon()

    html += """
</body>
</html>
"""
    return html


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("Loading data...")
    index, analysis = load_data()
    print(f"  {index['total_letters']} letters, {len(analysis.get('life_chapters', []))} chapters")

    print("Generating HTML...")
    html = generate_html(index, analysis)

    # Ensure output directory exists
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Save HTML for debugging/preview
    HTML_PATH.write_text(html, encoding="utf-8")
    print(f"  HTML saved to {HTML_PATH}")

    print("Rendering PDF (this may take several minutes for 88 letters with images)...")
    font_config = FontConfiguration()
    doc = HTML(string=html, base_url=str(ROOT))
    doc.write_pdf(
        str(OUTPUT_PATH),
        font_config=font_config,
    )
    print(f"\nBook generated: {OUTPUT_PATH}")
    file_size = OUTPUT_PATH.stat().st_size / (1024 * 1024)
    print(f"  File size: {file_size:.1f} MB")


if __name__ == "__main__":
    main()
