#!/usr/bin/env python3
"""
Generate an interactive web experience for the Hanifen letter collection.
Produces a single self-contained HTML file with embedded data.
"""
import json
import re
import base64
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = ROOT / "data"
SCANS_DIR = ROOT / "BobScans"
PHOTOS_DIR = SCANS_DIR / "photos"
INDEX_PATH = DATA_DIR / "index.json"
ANALYSIS_PATH = DATA_DIR / "timeline_analysis.json"
OUTPUT_PATH = ROOT / "site" / "index.html"

IMAGE_EXTS = {".png", ".jpg", ".jpeg"}
AUDIOBOOK_SCRIPT_PATH = DATA_DIR / "audiobook_script_polished.txt"

PHOTO_MANIFEST_PATH = DATA_DIR / "photo_manifest.json"

def build_photo_manifest() -> list[dict]:
    """Load AI-generated photo manifest, or fall back to filename-based."""
    if PHOTO_MANIFEST_PATH.exists():
        with open(PHOTO_MANIFEST_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    # Fallback: shouldn't happen after running analyze_photos.py
    print("  Warning: photo_manifest.json not found. Run analyze_photos.py first.")
    return []


def load_data():
    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        index = json.load(f)
    with open(ANALYSIS_PATH, "r", encoding="utf-8") as f:
        analysis = json.load(f)
    return index, analysis


def build_scan_manifest(letters: list[dict]) -> dict:
    """Build a mapping of letter_id -> list of {label, filename} for scans."""
    manifest = {}
    for letter in letters:
        lid = str(letter["letter_id"])
        pages = []
        for page in letter.get("pages", []):
            source = page.get("source_file", "")
            if source:
                fname = Path(source).name
                if (SCANS_DIR / fname).exists():
                    pages.append({
                        "label": page.get("page_label", "page"),
                        "filename": fname,
                    })
        manifest[lid] = pages
    return manifest


def clean_sender(raw: str) -> str:
    if not raw:
        return "Unknown"
    name = re.split(r"\s*[—–\-]\s*", raw)[0]
    name = re.split(r"\s*\(", name)[0]
    name = re.sub(r"^(Pvt\.|PFC|Cpl\.|Sgt\.|Lt\.|Capt\.|Col\.)\s*", "", name).strip()
    return name if name else raw[:50]


def prepare_letters_data(letters: list[dict]) -> list[dict]:
    """Prepare a lighter version of letter data for the web app."""
    result = []
    for l in letters:
        meta = l.get("metadata", {})
        result.append({
            "id": str(l["letter_id"]),
            "date": meta.get("date", ""),
            "date_normalized": meta.get("date_normalized", ""),
            "date_is_approximate": meta.get("date_is_approximate", False),
            "from_raw": meta.get("from", ""),
            "to_raw": meta.get("to", ""),
            "from": clean_sender(meta.get("from", "")),
            "to": clean_sender(meta.get("to", "")),
            "location": meta.get("location_written_from", "") or "",
            "location_to": meta.get("location_sent_to", "") or "",
            "postmark": meta.get("postmark", "") or "",
            "envelope_notes": meta.get("envelope_notes", "") or "",
            "topics": meta.get("topics", []),
            "people": meta.get("people_mentioned", []),
            "places": meta.get("places_mentioned", []),
            "mood": meta.get("mood_tone", "") or "",
            "legibility": meta.get("legibility", "") or "",
            "legibility_notes": meta.get("legibility_notes", "") or "",
            "historical_context": meta.get("historical_context", "") or "",
            "transcription": l.get("full_transcription", ""),
            "summary": l.get("summary", ""),
            "pages": [
                {"label": p.get("page_label", ""), "file": Path(p.get("source_file", "")).name}
                for p in l.get("pages", [])
            ],
        })
    return result


def build_transcript_html() -> str:
    """Convert the polished audiobook script to HTML."""
    raw = AUDIOBOOK_SCRIPT_PATH.read_text(encoding="utf-8")
    lines = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            lines.append("")
            continue
        # Skip markdown meta lines
        if stripped == "---":
            lines.append('<hr class="transcript-rule">')
            continue
        if stripped.startswith("# "):
            lines.append(f'<h2 class="transcript-h2">{stripped[2:]}</h2>')
        elif stripped.startswith("## "):
            lines.append(f'<h3 class="transcript-h3">{stripped[3:]}</h3>')
        elif stripped.startswith("### "):
            lines.append(f'<h4 class="transcript-h4">{stripped[4:]}</h4>')
        elif stripped.startswith("[") and stripped.endswith("]"):
            # Stage directions like [pause]
            lines.append(f'<p class="transcript-direction">{stripped}</p>')
        elif stripped.startswith("*") and stripped.endswith("*"):
            lines.append(f'<p class="transcript-italic"><em>{stripped.strip("*")}</em></p>')
        else:
            lines.append(f"<p>{stripped}</p>")
    return "\n".join(lines)


def main():
    print("Loading data...")
    index, analysis = load_data()
    letters = index["letters"]
    scan_manifest = build_scan_manifest(letters)
    letters_data = prepare_letters_data(letters)
    chapters = analysis.get("life_chapters", [])
    profiles = analysis.get("character_profiles", [])
    narrative = analysis.get("narrative_overview", "")
    chrono = analysis.get("chronological_order", [])
    themes = analysis.get("recurring_themes", [])
    events = analysis.get("historical_events_referenced", [])

    # Sort chrono
    def chrono_sort(c):
        d = c.get("date", "") or "9999"
        return d
    chrono.sort(key=chrono_sort)

    # Build photo manifest
    photos = build_photo_manifest()

    # Build JS data blob
    js_data = {
        "letters": letters_data,
        "chapters": chapters,
        "profiles": profiles,
        "narrative": narrative,
        "chronological_order": chrono,
        "themes": themes,
        "events": events,
        "scan_manifest": scan_manifest,
        "photos": photos,
    }

    js_data_json = json.dumps(js_data, ensure_ascii=False)

    print(f"  {len(letters)} letters, {len(chapters)} chapters, {len(profiles)} profiles, {len(photos)} photos")
    print(f"  Data size: {len(js_data_json) / 1024:.0f} KB")

    # Load audiobook transcript
    transcript_html = build_transcript_html()

    html = build_html(js_data_json, transcript_html)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    print(f"\nWeb app generated: {OUTPUT_PATH}")
    print(f"  Open in browser: file://{OUTPUT_PATH.resolve()}")
    print(f"  Scans must be in: {SCANS_DIR.resolve()}/")


def build_html(js_data_json: str, transcript_html: str = "") -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Letters Home — The Hanifen Family Collection</title>
<meta name="description" content="A digital archive of 88 handwritten letters from the Hanifen brothers spanning 1941–1976. Read, search, and listen to the wartime correspondence of Bob, Jim, and John Hanifen.">
<!-- Open Graph -->
<meta property="og:type" content="website">
<meta property="og:title" content="Letters Home — The Hanifen Family Collection">
<meta property="og:description" content="88 handwritten letters spanning 1941–1976. The wartime correspondence of the Hanifen brothers — Bob, Jim, and John — from Des Moines to the front lines and back.">
<meta property="og:image" content="https://letters-home.hanifen-family-collection.com/og-image.jpg">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:url" content="https://letters-home.hanifen-family-collection.com/">
<meta property="og:site_name" content="Letters Home">
<!-- Twitter Card -->
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="Letters Home — The Hanifen Family Collection">
<meta name="twitter:description" content="88 handwritten letters spanning 1941–1976. The wartime correspondence of the Hanifen brothers from Des Moines.">
<meta name="twitter:image" content="https://letters-home.hanifen-family-collection.com/og-image.jpg">
<link rel="icon" type="image/svg+xml" href="favicon.svg">
<link rel="icon" type="image/png" href="favicon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;0,500;0,600;0,700;1,300;1,400;1,500&family=EB+Garamond:ital,wght@0,400;0,500;0,600;0,700;1,400;1,500&family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdn.plyr.io/3.7.8/plyr.css">
<style>
{CSS_CONTENT}
</style>
</head>
<body>

<!-- ===== TOP NAV ===== -->
<nav id="topnav">
  <div class="nav-inner">
    <a href="#" class="nav-brand" onclick="showSection('hero');return false;">Letters Home</a>
    <div class="nav-links">
      <a href="#" onclick="showSection('overview');return false;">Story</a>
      <a href="#" onclick="showSection('timeline');return false;">Timeline</a>
      <a href="#" onclick="showSection('chapters');return false;">Chapters</a>
      <a href="#" onclick="showSection('highlights');return false;">Highlights</a>
      <a href="#" onclick="showSection('photos');return false;">Photos</a>
      <a href="#" onclick="showSection('search');return false;" class="nav-search-link">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
        Search
      </a>
      <a href="#" onclick="showSection('about');return false;">About</a>
    </div>
    <button class="nav-mobile-toggle" onclick="toggleMobileMenu()">&#9776;</button>
  </div>
</nav>

<!-- ===== HERO ===== -->
<section id="hero" class="section active">
  <div class="hero-bg">
    <div class="hero-overlay"></div>
    <div class="hero-content">
      <div class="hero-pretitle">The Hanifen Family Collection</div>
      <h1 class="hero-title">Letters Home</h1>
      <p class="hero-subtitle">The Wartime Correspondence of the Hanifen Brothers</p>
      <div class="hero-rule"></div>
      <p class="hero-dates">1941 &mdash; 1976</p>
      <div class="hero-stats">
        <div class="stat"><span class="stat-num" id="stat-letters">88</span><span class="stat-label">Letters</span></div>
        <div class="stat"><span class="stat-num">35</span><span class="stat-label">Years</span></div>
        <div class="stat"><span class="stat-num">5</span><span class="stat-label">Chapters</span></div>
        <div class="stat"><span class="stat-num" id="stat-pages">505</span><span class="stat-label">Pages</span></div>
      </div>
      <button class="hero-cta" onclick="showSection('overview')">Begin Reading &darr;</button>
    </div>
  </div>
</section>

<!-- ===== OVERVIEW ===== -->
<section id="overview" class="section">
  <div class="container">
    <div class="section-photo">
      <img src="photos_web/photos/hanifen_brothers_lookin_cool.jpg" alt="The Hanifen Brothers">
      <span class="section-photo-caption">The Hanifen Brothers &mdash; Bob, Jim, and John</span>
    </div>
    <div class="section-header">
      <div class="section-label">Foreword</div>
      <h2 class="section-title">The Story of These Letters</h2>
      <div class="section-rule"></div>
    </div>
    <div id="narrative-text" class="narrative-text"></div>
    <div class="overview-nav">
      <button class="btn-secondary" onclick="showSection('timeline')">View Timeline &rarr;</button>
    </div>
  </div>
</section>

<!-- ===== TIMELINE ===== -->
<section id="timeline" class="section">
  <div class="container">
    <div class="section-photo">
      <img src="photos_web/photos/hanifen_brothers_lookin_cool.jpg" alt="The Hanifen Brothers">
      <span class="section-photo-caption">The Hanifen Brothers &mdash; Bob, Jim, and John</span>
    </div>
    <div class="section-header">
      <div class="section-label">Chronology</div>
      <h2 class="section-title">Timeline</h2>
      <div class="section-rule"></div>
    </div>
    <div class="timeline-filters">
      <button class="filter-btn active" data-filter="all" onclick="filterTimeline('all',this)">All</button>
      <button class="filter-btn" data-filter="bob" onclick="filterTimeline('bob',this)">From Bob</button>
      <button class="filter-btn" data-filter="dad" onclick="filterTimeline('dad',this)">From Dad</button>
      <button class="filter-btn" data-filter="official" onclick="filterTimeline('official',this)">Official</button>
    </div>
    <div class="timeline-year-nav" id="year-nav"></div>
    <div id="timeline-container" class="timeline-track"></div>
  </div>
</section>

<!-- ===== CHAPTERS ===== -->
<section id="chapters" class="section">
  <div class="container">
    <div class="section-photo">
      <img src="photos_web/photos/hanifen_brothers_lookin_cool.jpg" alt="The Hanifen Brothers">
      <span class="section-photo-caption">The Hanifen Brothers &mdash; Bob, Jim, and John</span>
    </div>
    <div class="section-header">
      <div class="section-label">The Narrative</div>
      <h2 class="section-title">Chapters</h2>
      <div class="section-rule"></div>
    </div>
    <div id="chapters-grid" class="chapters-grid"></div>
    <div id="chapter-detail" class="chapter-detail" style="display:none;"></div>
  </div>
</section>

<!-- ===== HIGHLIGHTS ===== -->
<section id="highlights" class="section">
  <div class="container">
    <div class="section-photo">
      <img src="photos_web/photos/hanifen_brothers_lookin_cool.jpg" alt="The Hanifen Brothers">
      <span class="section-photo-caption">The Hanifen Brothers &mdash; Bob, Jim, and John</span>
    </div>
    <div class="section-header">
      <div class="section-label">In Their Own Words</div>
      <h2 class="section-title">Highlights</h2>
      <div class="section-rule"></div>
      <p class="highlights-intro">The most vivid, funny, heartbreaking, and historically remarkable passages from thirty-five years of family letters.</p>
    </div>
    <div class="highlights-filters">
      <button class="filter-btn active" onclick="filterHighlights('all',this)">All</button>
      <button class="filter-btn" onclick="filterHighlights('humor',this)">Humor</button>
      <button class="filter-btn" onclick="filterHighlights('emotion',this)">Emotion</button>
      <button class="filter-btn" onclick="filterHighlights('history',this)">History</button>
      <button class="filter-btn" onclick="filterHighlights('military-life',this)">Military Life</button>
      <button class="filter-btn" onclick="filterHighlights('family',this)">Family</button>
      <button class="filter-btn" onclick="filterHighlights('adventure',this)">Adventure</button>
      <button class="filter-btn" onclick="filterHighlights('home-front',this)">Home Front</button>
    </div>
    <div id="highlights-list" class="highlights-list"></div>
  </div>
</section>

<!-- ===== PHOTOS ===== -->
<section id="photos" class="section">
  <div class="container container-wide">
    <div class="section-photo">
      <img src="photos_web/photos/hanifen_brothers_lookin_cool.jpg" alt="The Hanifen Brothers">
      <span class="section-photo-caption">The Hanifen Brothers &mdash; Bob, Jim, and John</span>
    </div>
    <div class="section-header">
      <div class="section-label">Family Album</div>
      <h2 class="section-title">Photographs</h2>
      <div class="section-rule"></div>
      <p class="photos-intro">Family photographs from the Hanifen collection, spanning generations.</p>
    </div>
    <div class="photos-filters" id="photo-filters"></div>
    <div id="photos-grid" class="photos-grid"></div>
  </div>
</section>


<!-- ===== SEARCH ===== -->
<section id="search" class="section">
  <div class="container">
    <div class="section-photo">
      <img src="photos_web/photos/hanifen_brothers_lookin_cool.jpg" alt="The Hanifen Brothers">
      <span class="section-photo-caption">The Hanifen Brothers &mdash; Bob, Jim, and John</span>
    </div>
    <div class="section-header">
      <div class="section-label">Explore</div>
      <h2 class="section-title">Search the Collection</h2>
      <div class="section-rule"></div>
    </div>
    <div class="search-box">
      <input type="text" id="search-input" placeholder="Search letters, people, places, topics..." autocomplete="off">
      <div class="search-hint">Try: "Italy", "Christmas", "Indianapolis", "draft board", "Sheppard Field"</div>
    </div>
    <div id="search-results" class="search-results"></div>
  </div>
</section>

<!-- ===== TRANSCRIPT ===== -->
<section id="transcript" class="section">
  <div class="container">
    <div class="section-photo">
      <img src="photos_web/photos/hanifen_brothers_lookin_cool.jpg" alt="The Hanifen Brothers">
      <span class="section-photo-caption">The Hanifen Brothers &mdash; Bob, Jim, and John</span>
    </div>
    <div class="section-header">
      <div class="section-label">Audiobook</div>
      <h2 class="section-title">Audio Transcript</h2>
      <div class="section-rule"></div>
      <p class="transcript-intro">The full text of the narrated audiobook. <a href="audio/Letters_Home_Audiobook.mp3" target="_blank">Listen to the audio &rarr;</a></p>
    </div>
    <div class="transcript-content">
      {transcript_html}
    </div>
  </div>
</section>

<!-- ===== ABOUT ===== -->
<section id="about" class="section">
  <div class="container">
    <div class="section-photo">
      <img src="photos_web/photos/hanifen_brothers_lookin_cool.jpg" alt="The Hanifen Brothers — Bob, Jim, and John">
      <span class="section-photo-caption">The Hanifen Brothers &mdash; Bob, Jim, and John</span>
    </div>
    <div class="section-header">
      <div class="section-label">Behind the Project</div>
      <h2 class="section-title">About This Collection</h2>
      <div class="section-rule"></div>
    </div>
    <div class="about-content">
      <h3>How This Site Was Created</h3>
      <p>This digital archive began with a box of handwritten letters spanning thirty-five years of Hanifen family correspondence. The letters &mdash; primarily written by Bob Hanifen and his father James Edward Hanifen Sr. &mdash; were carefully preserved by the family and eventually scanned at high resolution to create a permanent digital record.</p>

      <h3>The Digitization Process</h3>
      <p>Each of the 88 letters was scanned page by page, producing over 500 individual page images. The handwritten text was then transcribed using a combination of AI-assisted optical character recognition and manual review. Every transcription was checked against the original scans to ensure accuracy, though some passages remain difficult to decipher due to the age and condition of the originals.</p>

      <h3>The Interactive Experience</h3>
      <p>The web application you are using was built with Python and vanilla JavaScript. It uses Claude, Anthropic's AI assistant, to help analyze the letters &mdash; identifying people, places, dates, topics, and moods &mdash; and to generate the timeline, chapter groupings, and historical context that make the collection navigable. The entire site is self-contained in a single HTML file with no server required.</p>

      <h3>The Audiobook</h3>
      <p>An audiobook version of the collection was produced using AI text-to-speech technology, bringing the letters to life as a narrated experience. The audiobook script was carefully edited to read naturally when spoken aloud, with contextual introductions for each letter and smooth transitions between them. You can read the full text on the <a href="#" onclick="showSection('transcript');return false;">Transcript</a> page.</p>

      <h3>Family Photographs</h3>
      <p>The photograph collection was assembled from family albums and loose prints spanning from the 1910s through the 1990s. Each photo was scanned, cataloged, and annotated with AI-assisted identification of the people, places, and approximate dates.</p>

      <h3>Source Code</h3>
      <p>This project is open source. The full code, data, and generation scripts are available on <a href="https://github.com/jhanifen/letters-home-the-hanifen-family-collection" target="_blank" rel="noopener">GitHub</a>.</p>

      <h3>Feedback &amp; Corrections</h3>
      <p>If you spot an error, have additional context about the letters, or would like to contribute, there are two ways to help:</p>
      <ul>
        <li>Reach out directly to Jimmy Hanifen IV (Jim's son)</li>
        <li>Create a <a href="https://github.com/jhanifen/letters-home-the-hanifen-family-collection/pulls" target="_blank" rel="noopener">pull request</a> on GitHub</li>
      </ul>

      <p class="about-note">This project was created by Jim Hanifen as a memorial to his uncle Bob and a way to preserve the family's written history for future generations.</p>
    </div>
  </div>
</section>


<!-- ===== LETTER MODAL ===== -->
<div id="letter-modal" class="modal" style="display:none;">
  <div class="modal-backdrop" onclick="closeModal()"></div>
  <div class="modal-content">
    <button class="modal-close" onclick="closeModal()">&times;</button>
    <div class="modal-nav">
      <button class="modal-nav-btn" id="modal-prev" onclick="navigateLetter(-1)">&larr; Previous</button>
      <button class="modal-nav-btn" id="modal-next" onclick="navigateLetter(1)">Next &rarr;</button>
    </div>
    <div id="modal-body"></div>
  </div>
</div>


<!-- ===== AUDIO PLAYER ===== -->
<div id="audio-player" class="audio-player-bar">
  <div class="audio-player-inner">
    <span class="audio-player-label">Letters Home &mdash; Audiobook</span>
    <audio id="audio-el" preload="metadata">
      <source src="audio/Letters_Home_ElevenLabs.mp3" type="audio/mpeg">
    </audio>
  </div>
</div>
<script src="https://cdn.plyr.io/3.7.8/plyr.polyfilled.js"></script>

<script>
const DATA = {js_data_json};
{JS_CONTENT}
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------
CSS_CONTENT = r"""
:root {
  --bg: #faf6f0;
  --bg-dark: #1a1510;
  --bg-card: #f5f0e8;
  --bg-card-hover: #f0ebe2;
  --text: #2c2416;
  --text-secondary: #5a4e3a;
  --text-muted: #8b7355;
  --accent: #6b5b4f;
  --accent-gold: #b5a68a;
  --accent-warm: #a0876b;
  --border: #d4c5a9;
  --border-light: #e8e0d0;
  --serif: 'EB Garamond', 'Georgia', serif;
  --display: 'Cormorant Garamond', 'Georgia', serif;
  --sans: 'Inter', -apple-system, system-ui, sans-serif;
  --shadow: 0 2px 12px rgba(42, 36, 22, 0.08);
  --shadow-lg: 0 8px 32px rgba(42, 36, 22, 0.12);
  --transition: 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

*, *::before, *::after { box-sizing: border-box; }

body {
  margin: 0; padding: 0;
  font-family: var(--serif);
  font-size: 19px;
  line-height: 1.7;
  color: var(--text);
  background: var(--bg-dark);
  -webkit-font-smoothing: antialiased;
}

.container { max-width: 960px; margin: 0 auto; padding: 0 28px; }

/* === NAV === */
#topnav {
  position: fixed; top: 0; left: 0; right: 0; z-index: 1000;
  background: rgba(26, 21, 16, 0.95);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid rgba(139, 115, 85, 0.2);
  transition: transform var(--transition);
}
#topnav.hidden { transform: translateY(-100%); }
.nav-inner {
  max-width: 1100px; margin: 0 auto;
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 24px; height: 56px;
}
.nav-brand {
  font-family: var(--display); font-size: 18px; font-weight: 500;
  color: var(--accent-gold); text-decoration: none; letter-spacing: 0.06em;
}
.nav-links { display: flex; gap: 28px; align-items: center; }
.nav-links a {
  font-family: var(--sans); font-size: 15px; font-weight: 400;
  color: #a89578; text-decoration: none; letter-spacing: 0.04em;
  transition: color var(--transition); display: flex; align-items: center; gap: 5px;
}
.nav-links a:hover { color: #d4c5a9; }
.nav-mobile-toggle {
  display: none; background: none; border: none; color: #a89578;
  font-size: 22px; cursor: pointer;
}
@media (max-width: 700px) {
  .nav-links { display: none; }
  .nav-links.open {
    display: flex; flex-direction: column; position: absolute;
    top: 56px; left: 0; right: 0; background: rgba(26,21,16,0.98);
    padding: 16px 24px; gap: 16px;
  }
  .nav-mobile-toggle { display: block; }
}

/* === SECTIONS === */
.section { display: none; min-height: 100vh; padding: 100px 0 80px; }
.section.active { display: block; }

.section-header { text-align: center; margin-bottom: 48px; }
.section-label {
  font-family: var(--sans); font-size: 13px; font-weight: 500;
  text-transform: uppercase; letter-spacing: 0.2em; color: var(--accent-warm);
  margin-bottom: 8px;
}
.section-title {
  font-family: var(--display); font-size: 40px; font-weight: 400;
  color: var(--text); margin: 0 0 12px; letter-spacing: 0.04em;
}
.section-rule {
  width: 60px; height: 1px; background: var(--accent-gold);
  margin: 0 auto;
}

/* === SECTION PHOTO === */
.section-photo {
  text-align: center;
  margin-bottom: 36px;
}
.section-photo img {
  width: 180px;
  height: 180px;
  object-fit: cover;
  object-position: top;
  border-radius: 50%;
  border: 3px solid var(--border-light);
  box-shadow: var(--shadow);
}
.section-photo-caption {
  display: block;
  font-family: var(--sans);
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 10px;
  letter-spacing: 0.04em;
}

/* === ABOUT === */
.about-content {
  max-width: 740px;
  margin: 0 auto;
  font-size: 19px;
  line-height: 1.8;
  color: var(--text-secondary);
}
.about-content h3 {
  font-family: var(--display);
  font-size: 26px;
  font-weight: 500;
  color: var(--text);
  margin: 36px 0 12px;
  letter-spacing: 0.03em;
}
.about-content h3:first-child { margin-top: 0; }
.about-content p {
  margin-bottom: 16px;
}
.about-note {
  margin-top: 40px;
  padding: 20px 24px;
  background: var(--bg-card);
  border-left: 3px solid var(--accent-gold);
  font-style: italic;
  color: var(--text-muted);
}


/* === TRANSCRIPT === */
.transcript-intro {
  font-family: var(--serif);
  font-size: 17px;
  color: var(--text-muted);
  margin-top: 12px;
}
.transcript-intro a {
  color: var(--accent-warm);
  text-decoration: none;
  border-bottom: 1px solid var(--border-light);
}
.transcript-intro a:hover { color: var(--accent); }
.transcript-content {
  max-width: 740px;
  margin: 0 auto;
  font-size: 19px;
  line-height: 1.8;
  color: var(--text-secondary);
}
.transcript-content p {
  margin-bottom: 16px;
}
.transcript-h2 {
  font-family: var(--display);
  font-size: 32px;
  font-weight: 400;
  color: var(--text);
  text-align: center;
  margin: 48px 0 8px;
  letter-spacing: 0.06em;
}
.transcript-h3 {
  font-family: var(--display);
  font-size: 26px;
  font-weight: 500;
  color: var(--text);
  margin: 40px 0 12px;
  letter-spacing: 0.03em;
}
.transcript-h4 {
  font-family: var(--sans);
  font-size: 15px;
  font-weight: 500;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.1em;
  margin: 32px 0 8px;
}
.transcript-direction {
  font-family: var(--sans);
  font-size: 13px;
  color: var(--text-muted);
  font-style: italic;
  letter-spacing: 0.04em;
  margin: 12px 0;
}
.transcript-italic {
  font-style: italic;
  color: var(--text-muted);
}
.transcript-rule {
  width: 60px;
  height: 1px;
  background: var(--accent-gold);
  margin: 32px auto;
  border: none;
}
.about-content ul {
  margin: 0 0 16px 24px;
  padding: 0;
}
.about-content li {
  margin-bottom: 8px;
}
.about-content a {
  color: var(--accent-warm);
  text-decoration: none;
  border-bottom: 1px solid var(--border-light);
}
.about-content a:hover { color: var(--accent); }

/* === AUDIO PLAYER === */
.audio-player-bar {
  position: fixed;
  bottom: 0; left: 0; right: 0;
  z-index: 1100;
  background: rgba(26, 21, 16, 0.97);
  backdrop-filter: blur(12px);
  border-top: 1px solid rgba(139, 115, 85, 0.25);
  padding: 8px 20px;
}
.audio-player-inner {
  max-width: 960px;
  margin: 0 auto;
  display: flex;
  align-items: center;
  gap: 16px;
}
.audio-player-label {
  font-family: var(--sans); font-size: 12px; font-weight: 500;
  color: #a89578; letter-spacing: 0.04em;
  white-space: nowrap; flex-shrink: 0;
}
.audio-player-inner .plyr {
  flex: 1;
  min-width: 0;
}
/* Theme Plyr to match site */
.audio-player-bar .plyr--audio .plyr__controls {
  background: transparent;
  color: #a89578;
  padding: 0;
}
.audio-player-bar .plyr--audio .plyr__control:hover {
  background: rgba(181,166,138,0.15);
}
.audio-player-bar .plyr--audio .plyr__control.plyr__tab-focus {
  box-shadow: 0 0 0 3px rgba(181,166,138,0.3);
}
:root {
  --plyr-color-main: #b5a68a;
  --plyr-audio-control-color: #a89578;
  --plyr-audio-control-color-hover: #d4c5a9;
  --plyr-range-thumb-background: #b5a68a;
  --plyr-range-fill-background: #b5a68a;
  --plyr-range-track-height: 5px;
  --plyr-range-thumb-height: 14px;
}
body { padding-bottom: 64px; }
.section { background: var(--bg); }

@media (max-width: 600px) {
  .audio-player-bar { padding: 6px 12px; }
  .audio-player-label { display: none; }
}

/* === HERO === */
#hero { padding: 0; background: var(--bg); }
.hero-bg {
  min-height: 100vh; display: flex; align-items: center; justify-content: center;
  background: var(--bg-dark); position: relative; overflow: hidden;
}
.hero-bg::before {
  content: '';
  position: absolute; inset: 0;
  background: url('photos_web/photos/hanifen_brothers_lookin_cool.jpg') center 15% / cover no-repeat;
  opacity: 0.12;
  filter: sepia(1) saturate(0.3) contrast(1.1) brightness(0.9);
  mix-blend-mode: luminosity;
}
.hero-overlay {
  position: absolute; inset: 0;
  background:
    radial-gradient(ellipse at center, rgba(26,21,16,0.2) 0%, rgba(26,21,16,0.85) 70%, rgba(26,21,16,0.97) 100%);
}
.hero-content { position: relative; text-align: center; padding: 40px; }
.hero-pretitle {
  font-family: var(--sans); font-size: 11px; font-weight: 500;
  text-transform: uppercase; letter-spacing: 0.25em; color: var(--accent-warm);
  margin-bottom: 20px;
}
.hero-title {
  font-family: var(--display); font-size: clamp(48px, 8vw, 80px); font-weight: 300;
  color: #d4c5a9; letter-spacing: 0.1em; text-transform: uppercase;
  margin: 0 0 8px; line-height: 1.1;
}
.hero-subtitle {
  font-family: var(--serif); font-size: clamp(16px, 2.5vw, 20px); font-style: italic;
  color: var(--accent-warm); margin: 0 0 24px; letter-spacing: 0.03em;
}
.hero-rule { width: 100px; height: 1px; background: var(--accent-gold); margin: 0 auto 20px; opacity: 0.5; }
.hero-dates {
  font-family: var(--serif); font-size: 14px; color: var(--text-muted);
  letter-spacing: 0.1em; margin: 0 0 48px;
}
.hero-stats {
  display: flex; gap: 40px; justify-content: center; margin-bottom: 48px;
  flex-wrap: wrap;
}
.stat { text-align: center; }
.stat-num {
  display: block; font-family: var(--display); font-size: 36px; font-weight: 300;
  color: #d4c5a9; line-height: 1;
}
.stat-label {
  font-family: var(--sans); font-size: 10px; text-transform: uppercase;
  letter-spacing: 0.15em; color: var(--text-muted); margin-top: 4px; display: block;
}
.hero-cta {
  font-family: var(--sans); font-size: 13px; font-weight: 500;
  text-transform: uppercase; letter-spacing: 0.15em;
  color: var(--accent-gold); background: transparent;
  border: 1px solid rgba(181,166,138,0.3); padding: 14px 36px;
  cursor: pointer; transition: all var(--transition);
}
.hero-cta:hover { background: rgba(181,166,138,0.1); border-color: var(--accent-gold); }

/* === NARRATIVE === */
.narrative-text {
  max-width: 740px; margin: 0 auto;
  font-size: 20px; line-height: 1.8; color: var(--text-secondary);
}
.narrative-text p { margin-bottom: 20px; text-indent: 24px; }
.narrative-text p:first-child { text-indent: 0; }
.narrative-text p:first-child::first-letter {
  font-family: var(--display); font-size: 56px; float: left;
  line-height: 0.85; margin: 4px 8px 0 0; color: var(--accent);
  font-weight: 400;
}
.overview-nav { text-align: center; margin-top: 48px; }
.btn-secondary {
  font-family: var(--sans); font-size: 15px; font-weight: 500;
  color: var(--accent); background: transparent;
  border: 1px solid var(--border); padding: 12px 28px;
  cursor: pointer; letter-spacing: 0.06em; transition: all var(--transition);
}
.btn-secondary:hover { background: var(--bg-card); }

/* === TIMELINE === */
.timeline-filters {
  display: flex; gap: 8px; justify-content: center; margin-bottom: 24px;
  flex-wrap: wrap;
}
.filter-btn {
  font-family: var(--sans); font-size: 14px; font-weight: 400;
  padding: 8px 20px; border: 1px solid var(--border);
  background: transparent; color: var(--text-secondary);
  cursor: pointer; transition: all var(--transition);
}
.filter-btn.active { background: var(--accent); color: #fff; border-color: var(--accent); }
.filter-btn:hover:not(.active) { background: var(--bg-card); }

.timeline-year-nav {
  display: flex; gap: 6px; justify-content: center; margin-bottom: 32px;
  flex-wrap: wrap;
}
.year-btn {
  font-family: var(--sans); font-size: 13px; font-weight: 500;
  padding: 6px 12px; border: none; background: var(--bg-card);
  color: var(--text-secondary); cursor: pointer; transition: all var(--transition);
}
.year-btn:hover { background: var(--accent-gold); color: #fff; }

.timeline-track { position: relative; padding-left: 40px; }
.timeline-track::before {
  content: ''; position: absolute; left: 16px; top: 0; bottom: 0;
  width: 2px; background: var(--border);
}
.timeline-year-marker {
  position: relative; margin: 32px 0 16px -40px; padding-left: 40px;
}
.timeline-year-marker .year-label {
  font-family: var(--display); font-size: 28px; font-weight: 400;
  color: var(--accent); letter-spacing: 0.05em;
}
.timeline-year-marker::before {
  content: ''; position: absolute; left: 10px; top: 50%; transform: translateY(-50%);
  width: 14px; height: 14px; border-radius: 50%;
  background: var(--accent); border: 3px solid var(--bg);
}

.tl-card {
  position: relative; background: #fff; border: 1px solid var(--border-light);
  padding: 16px 20px; margin-bottom: 12px; cursor: pointer;
  transition: all var(--transition);
}
.tl-card:hover { background: var(--bg-card-hover); box-shadow: var(--shadow); transform: translateX(4px); }
.tl-card::before {
  content: ''; position: absolute; left: -28px; top: 20px;
  width: 8px; height: 8px; border-radius: 50%;
  background: var(--accent-gold); border: 2px solid var(--bg);
}
.tl-card.approximate::before { background: var(--accent-warm); border-style: dashed; }
.tl-card-date {
  font-family: var(--sans); font-size: 13px; font-weight: 500;
  color: var(--accent-warm); text-transform: uppercase; letter-spacing: 0.06em;
}
.tl-card-date .approx-badge {
  font-size: 11px; background: rgba(160,135,107,0.15); color: var(--accent-warm);
  padding: 2px 8px; margin-left: 6px; vertical-align: middle;
}
.tl-card-title {
  font-family: var(--serif); font-size: 18px; color: var(--text);
  margin: 4px 0;
}
.tl-card-summary {
  font-size: 15px; color: var(--text-secondary); line-height: 1.55;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  overflow: hidden;
}
.tl-card-tags {
  display: flex; gap: 6px; margin-top: 8px; flex-wrap: wrap;
}
.tl-tag {
  font-family: var(--sans); font-size: 12px; padding: 3px 10px;
  background: var(--bg-card); color: var(--text-muted); border-radius: 2px;
}
.tl-card[data-hidden="true"] { display: none; }

/* === CHAPTERS === */
.chapters-grid {
  display: grid; grid-template-columns: 1fr; gap: 24px;
}
.chapter-card {
  background: #fff; border: 1px solid var(--border-light);
  padding: 32px; cursor: pointer; transition: all var(--transition);
  position: relative; overflow: hidden;
}
.chapter-card:hover { box-shadow: var(--shadow-lg); transform: translateY(-2px); }
.chapter-card::before {
  content: ''; position: absolute; left: 0; top: 0; bottom: 0;
  width: 4px; background: var(--accent-gold);
}
.chapter-card .ch-num {
  font-family: var(--sans); font-size: 13px; font-weight: 500;
  text-transform: uppercase; letter-spacing: 0.2em; color: var(--accent-warm);
}
.chapter-card .ch-title {
  font-family: var(--display); font-size: 28px; font-weight: 400;
  color: var(--text); margin: 6px 0;
}
.chapter-card .ch-dates {
  font-family: var(--serif); font-size: 16px; font-style: italic;
  color: var(--text-muted); margin-bottom: 12px;
}
.chapter-card .ch-desc {
  font-size: 16px; color: var(--text-secondary); line-height: 1.65;
  display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical;
  overflow: hidden;
}
.chapter-card .ch-count {
  font-family: var(--sans); font-size: 14px; color: var(--accent-warm);
  margin-top: 12px;
}

.chapter-detail { margin-top: 32px; }
.chapter-detail-header {
  text-align: center; padding: 32px 0; border-bottom: 1px solid var(--border);
  margin-bottom: 32px;
}
.chapter-detail-header .ch-back {
  font-family: var(--sans); font-size: 14px; color: var(--accent-warm);
  cursor: pointer; background: none; border: none; margin-bottom: 16px;
  letter-spacing: 0.06em;
}
.chapter-detail-header .ch-back:hover { color: var(--accent); }
.chapter-detail-desc {
  max-width: 740px; margin: 0 auto 32px; font-size: 18px;
  line-height: 1.75; color: var(--text-secondary);
}
.chapter-detail-desc p { margin-bottom: 14px; }
.chapter-letters-title {
  font-family: var(--sans); font-size: 13px; font-weight: 500;
  text-transform: uppercase; letter-spacing: 0.15em; color: var(--accent-warm);
  margin-bottom: 16px;
}

/* === LETTER CARDS (used in chapter detail) === */
.letter-list { display: flex; flex-direction: column; gap: 12px; }
.letter-card {
  display: flex; gap: 16px; align-items: flex-start;
  background: #fff; border: 1px solid var(--border-light);
  padding: 16px 20px; cursor: pointer; transition: all var(--transition);
}
.letter-card:hover { box-shadow: var(--shadow); background: var(--bg-card-hover); }
.letter-card .lc-date {
  font-family: var(--sans); font-size: 13px; font-weight: 500;
  color: var(--accent-warm); white-space: nowrap; min-width: 100px;
  padding-top: 2px;
}
.letter-card .lc-body { flex: 1; }
.letter-card .lc-correspondents {
  font-size: 17px; font-weight: 500; color: var(--text); margin-bottom: 2px;
}
.letter-card .lc-summary {
  font-size: 15px; color: var(--text-secondary); line-height: 1.55;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  overflow: hidden;
}

/* === PHOTOS === */
.container-wide { max-width: 1200px; }
.photos-intro {
  font-size: 17px; font-style: italic; color: var(--text-secondary);
  max-width: 600px; margin: 16px auto 0; text-align: center; line-height: 1.6;
}
.photos-filters {
  display: flex; gap: 8px; justify-content: center; margin: 24px 0 32px;
  flex-wrap: wrap;
}
.photos-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 24px; margin-top: 8px;
}
.photo-card[data-hidden="true"] { display: none; }
.photo-card {
  background: #fff; border: 1px solid var(--border-light);
  overflow: hidden; cursor: pointer; transition: all var(--transition);
  break-inside: avoid;
}
.photo-card:hover { box-shadow: var(--shadow-lg); transform: translateY(-3px); }
.photo-card img {
  width: 100%; height: 260px; object-fit: cover; display: block;
  transition: transform 0.4s ease;
}
.photo-card:hover img { transform: scale(1.03); }
.photo-card .photo-caption {
  padding: 14px 16px; font-size: 14px; color: var(--text-secondary);
  line-height: 1.45; border-top: 1px solid var(--border-light);
}
.photo-card .photo-date {
  font-family: var(--sans); font-size: 11px; font-weight: 500;
  color: var(--accent-warm); text-transform: uppercase; letter-spacing: 0.04em;
  margin-bottom: 3px;
}
.photo-card .photo-people {
  font-size: 12px; color: var(--text-muted); margin-top: 4px;
}
.photo-card .photo-letter-link {
  display: inline-block; font-family: var(--sans); font-size: 12px;
  color: var(--accent-warm); cursor: pointer; margin-top: 6px;
  transition: color var(--transition);
}
.photo-card .photo-letter-link:hover { color: var(--accent); text-decoration: underline; }
.photo-card .photo-tags {
  display: flex; gap: 4px; flex-wrap: wrap; margin-top: 6px;
}
.photo-card .photo-tag {
  font-family: var(--sans); font-size: 10px; padding: 1px 7px;
  background: var(--bg-card); color: var(--text-muted);
}
.photo-card .photo-back-note {
  font-size: 12px; color: var(--text-muted); font-style: italic;
  margin-top: 4px;
}

/* Photo lightbox additions */
.photo-lightbox-caption {
  position: absolute; bottom: 20px; left: 50%; transform: translateX(-50%);
  background: rgba(26,21,16,0.8); color: #d4c5a9; padding: 8px 20px;
  font-family: var(--sans); font-size: 14px; max-width: 80%;
  text-align: center; pointer-events: none;
}
.photo-lightbox-nav {
  position: absolute; top: 50%; transform: translateY(-50%);
  background: rgba(26,21,16,0.6); color: #d4c5a9; border: none;
  font-size: 32px; padding: 8px 16px; cursor: pointer;
  transition: background var(--transition);
}
.photo-lightbox-nav:hover { background: rgba(26,21,16,0.9); }
.photo-lightbox-nav.prev { left: 12px; }
.photo-lightbox-nav.next { right: 12px; }
.photo-lightbox-close {
  position: absolute; top: 16px; right: 20px;
  background: none; border: none; color: #d4c5a9;
  font-size: 36px; cursor: pointer;
}
.photo-lightbox-flip {
  position: absolute; top: 16px; left: 20px;
  background: rgba(26,21,16,0.6); border: none; color: #d4c5a9;
  font-family: var(--sans); font-size: 13px; padding: 6px 14px;
  cursor: pointer; display: none;
}
.photo-lightbox-flip.visible { display: block; }

/* === HIGHLIGHTS === */
.highlights-intro {
  font-size: 17px; font-style: italic; color: var(--text-secondary);
  max-width: 600px; margin: 16px auto 0; text-align: center; line-height: 1.6;
}
.highlights-filters {
  display: flex; gap: 8px; justify-content: center; margin: 32px 0 40px;
  flex-wrap: wrap;
}
.highlights-list { max-width: 780px; margin: 0 auto; }

.highlight-card {
  position: relative; margin-bottom: 40px;
  padding: 32px 36px; background: #fff;
  border: 1px solid var(--border-light);
  transition: all var(--transition);
}
.highlight-card:hover { box-shadow: var(--shadow-lg); }
.highlight-card::before {
  content: '\201C'; position: absolute; top: -8px; left: 16px;
  font-family: var(--display); font-size: 72px; color: var(--accent-gold);
  opacity: 0.35; line-height: 1;
}
.highlight-category {
  display: inline-block; font-family: var(--sans); font-size: 11px; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.12em; padding: 3px 12px;
  margin-bottom: 12px;
}
.highlight-category[data-cat="humor"] { background: #fdf3e7; color: #b8860b; }
.highlight-category[data-cat="emotion"] { background: #f3e8f0; color: #8b4570; }
.highlight-category[data-cat="history"] { background: #e8eef3; color: #4a6b8a; }
.highlight-category[data-cat="military-life"] { background: #e8f0e8; color: #4a6b4a; }
.highlight-category[data-cat="family"] { background: #f5f0e8; color: #7a6b55; }
.highlight-category[data-cat="adventure"] { background: #f0ece3; color: #8b6914; }
.highlight-category[data-cat="home-front"] { background: #eae8e3; color: #6b5b4f; }

.highlight-excerpt {
  font-family: var(--serif); font-size: 20px; line-height: 1.75;
  color: var(--text); font-style: italic; margin-bottom: 16px;
  padding-left: 12px;
}
.highlight-context {
  font-family: var(--sans); font-size: 14px; line-height: 1.6;
  color: var(--text-secondary); margin-bottom: 12px;
  padding-left: 12px;
}
.highlight-link {
  font-family: var(--sans); font-size: 13px; font-weight: 500;
  color: var(--accent-warm); text-decoration: none; cursor: pointer;
  padding-left: 12px; transition: color var(--transition);
}
.highlight-link:hover { color: var(--accent); text-decoration: underline; }

.highlight-card[data-hidden="true"] { display: none; }

.highlight-divider {
  width: 40px; height: 1px; background: var(--accent-gold); margin: 0 auto 40px;
  opacity: 0.5;
}

/* === PEOPLE === */
.people-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 20px; }
.person-card {
  background: #fff; border: 1px solid var(--border-light);
  padding: 24px; transition: all var(--transition);
}
.person-card:hover { box-shadow: var(--shadow); }
.person-card .pc-name {
  font-family: var(--display); font-size: 24px; color: var(--text); margin-bottom: 2px;
}
.person-card .pc-aliases {
  font-size: 14px; font-style: italic; color: var(--text-muted); margin-bottom: 8px;
}
.person-card .pc-role {
  font-family: var(--sans); font-size: 13px; font-weight: 500;
  text-transform: uppercase; letter-spacing: 0.08em;
  color: var(--accent-warm); margin-bottom: 8px;
}
.person-card .pc-desc {
  font-size: 15px; color: var(--text-secondary); line-height: 1.6;
}
.person-card .pc-letters {
  font-family: var(--sans); font-size: 13px; color: var(--text-muted);
  margin-top: 10px;
}

/* === SEARCH === */
.search-box { max-width: 600px; margin: 0 auto 32px; text-align: center; }
#search-input {
  width: 100%; font-family: var(--serif); font-size: 20px;
  padding: 16px 24px; border: 1px solid var(--border);
  background: #fff; color: var(--text); outline: none;
  transition: border-color var(--transition);
}
#search-input:focus { border-color: var(--accent); }
#search-input::placeholder { color: var(--accent-gold); }
.search-hint {
  font-family: var(--sans); font-size: 13px; color: var(--text-muted);
  margin-top: 10px;
}
.search-results { max-width: 700px; margin: 0 auto; }
.search-result-count {
  font-family: var(--sans); font-size: 14px; color: var(--text-muted);
  margin-bottom: 16px; text-align: center;
}
.sr-card {
  background: #fff; border: 1px solid var(--border-light);
  padding: 16px 20px; margin-bottom: 10px; cursor: pointer;
  transition: all var(--transition);
}
.sr-card:hover { box-shadow: var(--shadow); background: var(--bg-card-hover); }
.sr-card .sr-header { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 4px; }
.sr-card .sr-title { font-size: 17px; font-weight: 500; color: var(--text); }
.sr-card .sr-date { font-family: var(--sans); font-size: 13px; color: var(--accent-warm); }
.sr-card .sr-snippet {
  font-size: 15px; color: var(--text-secondary); line-height: 1.55;
}
.sr-card .sr-snippet mark {
  background: rgba(181,166,138,0.3); color: var(--text); padding: 0 2px;
}

/* === MODAL === */
.modal {
  position: fixed; inset: 0; z-index: 2000;
  display: flex; align-items: stretch; justify-content: flex-end;
}
.modal-backdrop { position: absolute; inset: 0; background: rgba(26,21,16,0.6); }
.modal-content {
  position: relative; width: min(800px, 100vw); background: var(--bg);
  overflow-y: auto; padding: 32px 40px 60px;
  box-shadow: -4px 0 32px rgba(0,0,0,0.2);
  animation: slideIn 0.3s ease;
}
@keyframes slideIn { from { transform: translateX(100%); } to { transform: translateX(0); } }
.modal-close {
  position: sticky; top: 0; float: right; z-index: 10;
  font-size: 28px; background: var(--bg); border: none;
  color: var(--text-muted); cursor: pointer; width: 40px; height: 40px;
  display: flex; align-items: center; justify-content: center;
}
.modal-close:hover { color: var(--text); }
.modal-nav {
  display: flex; justify-content: space-between; margin-bottom: 24px;
  position: sticky; top: 0; background: var(--bg); padding: 8px 0; z-index: 5;
}
.modal-nav-btn {
  font-family: var(--sans); font-size: 14px; font-weight: 500;
  color: var(--accent-warm); background: none; border: 1px solid var(--border);
  padding: 6px 14px; cursor: pointer; transition: all var(--transition);
}
.modal-nav-btn:hover { background: var(--bg-card); }
.modal-nav-btn:disabled { opacity: 0.3; cursor: default; }

/* Letter detail inside modal */
.ld-header { text-align: center; margin-bottom: 32px; padding-bottom: 24px; border-bottom: 1px solid var(--border); }
.ld-date { font-family: var(--display); font-size: 32px; color: var(--text); margin-bottom: 6px; }
.ld-correspondents { font-size: 18px; font-style: italic; color: var(--accent); }
.ld-location { font-size: 15px; color: var(--text-muted); margin-top: 6px; }
.ld-approx {
  display: inline-block; font-family: var(--sans); font-size: 11px;
  background: rgba(160,135,107,0.15); color: var(--accent-warm);
  padding: 2px 8px; vertical-align: super;
}

.ld-meta {
  display: grid; grid-template-columns: 1fr 1fr; gap: 10px 24px;
  background: var(--bg-card); padding: 20px 24px; margin-bottom: 32px;
  font-size: 15px;
}
.ld-meta-item .ld-meta-label {
  font-family: var(--sans); font-size: 12px; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-muted);
}
.ld-meta-item .ld-meta-value { color: var(--text-secondary); margin-top: 2px; }
.ld-meta-full { grid-column: 1 / -1; }

.ld-scans { margin-bottom: 28px; }
.ld-scans-label {
  font-family: var(--sans); font-size: 13px; font-weight: 500;
  text-transform: uppercase; letter-spacing: 0.12em; color: var(--accent-warm);
  margin-bottom: 12px;
}
.ld-scan-thumbs { display: flex; gap: 8px; flex-wrap: wrap; }
.ld-scan-thumb {
  width: 120px; height: 160px; object-fit: cover; border: 1px solid var(--border);
  cursor: pointer; transition: all var(--transition);
}
.ld-scan-thumb:hover { box-shadow: var(--shadow); transform: scale(1.03); }
.ld-scan-full {
  max-width: 100%; border: 1px solid var(--border); margin-top: 12px;
  box-shadow: var(--shadow);
}

.ld-transcription { margin-bottom: 28px; }
.ld-trans-label {
  font-family: var(--display); font-size: 20px; color: var(--accent);
  text-transform: uppercase; letter-spacing: 0.12em; text-align: center;
  margin-bottom: 6px;
}
.ld-trans-rule { width: 40px; height: 1px; background: var(--accent-gold); margin: 0 auto 20px; }
.ld-trans-text { font-size: 19px; line-height: 1.8; color: var(--text); }
.ld-trans-text p { margin-bottom: 14px; }

.ld-summary {
  background: var(--bg-card); padding: 16px 20px;
  border-top: 1px solid var(--border); border-bottom: 1px solid var(--border);
  margin-bottom: 20px;
}
.ld-summary-label {
  font-family: var(--sans); font-size: 12px; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.08em; color: var(--text-muted);
  margin-bottom: 4px;
}
.ld-summary-text { font-size: 16px; font-style: italic; color: var(--text-secondary); line-height: 1.65; }

.ld-history {
  font-size: 15px; font-style: italic; color: var(--accent);
  padding: 12px 16px; border-left: 3px solid var(--accent-gold);
  background: rgba(181,166,138,0.06);
}
.ld-history strong { font-style: normal; }

/* Scan lightbox */
.lightbox {
  position: fixed; inset: 0; z-index: 3000;
  background: rgba(0,0,0,0.9); display: flex;
  align-items: center; justify-content: center; cursor: zoom-out;
}
.lightbox img { max-width: 95vw; max-height: 95vh; object-fit: contain; }


/* === SCROLLBAR === */
::-webkit-scrollbar { width: 8px; }
::-webkit-scrollbar-track { background: var(--bg); }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: var(--accent-gold); }
"""


# ---------------------------------------------------------------------------
# JavaScript
# ---------------------------------------------------------------------------
JS_CONTENT = r"""
// ---- State ----
let currentSection = 'hero';
let currentLetterIdx = -1;
let chronoLetterIds = [];
let currentFilter = 'all';

// ---- Init ----
document.addEventListener('DOMContentLoaded', () => {
  renderNarrative();
  renderTimeline();
  renderChapters();
  renderHighlights();
  renderPhotos();
  buildChronoIndex();
  setupSearch();
  setupKeyboard();
  setupScrollNav();

  // Set stat numbers
  document.getElementById('stat-letters').textContent = DATA.letters.length;
  const totalPages = DATA.letters.reduce((sum, l) => sum + l.pages.length, 0);
  document.getElementById('stat-pages').textContent = totalPages;
});

// ---- Navigation ----
function showSection(id) {
  document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
  const el = document.getElementById(id);
  if (el) {
    el.classList.add('active');
    currentSection = id;
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }
  // Close mobile menu
  document.querySelector('.nav-links')?.classList.remove('open');

  // If going to search, focus input
  if (id === 'search') {
    setTimeout(() => document.getElementById('search-input')?.focus(), 100);
  }
}

function toggleMobileMenu() {
  document.querySelector('.nav-links')?.classList.toggle('open');
}

// ---- Scroll-aware nav ----
function setupScrollNav() {
  let lastY = 0;
  window.addEventListener('scroll', () => {
    const nav = document.getElementById('topnav');
    const y = window.scrollY;
    if (y > 200 && y > lastY) nav.classList.add('hidden');
    else nav.classList.remove('hidden');
    lastY = y;
  });
}

// ---- Narrative ----
function renderNarrative() {
  const el = document.getElementById('narrative-text');
  const paragraphs = DATA.narrative.split('\n\n');
  el.innerHTML = paragraphs.map(p => `<p>${escHtml(p.trim())}</p>`).join('');
}

// ---- Timeline ----
function renderTimeline() {
  const container = document.getElementById('timeline-container');
  const yearNav = document.getElementById('year-nav');
  const chrono = DATA.chronological_order;

  // Group by year
  const years = {};
  chrono.forEach(entry => {
    const date = entry.date || '';
    const year = date.substring(0, 4) || 'Unknown';
    if (!years[year]) years[year] = [];
    years[year].push(entry);
  });

  // Year navigation
  yearNav.innerHTML = Object.keys(years)
    .filter(y => y !== 'Unknown')
    .sort()
    .map(y => `<button class="year-btn" onclick="scrollToYear('${y}')">${y}</button>`)
    .join('');

  // Build timeline
  let html = '';
  Object.keys(years).sort().forEach(year => {
    html += `<div class="timeline-year-marker" id="year-${year}"><span class="year-label">${year}</span></div>`;
    years[year].forEach(entry => {
      const letter = DATA.letters.find(l => l.id === String(entry.letter_id));
      if (!letter) return;
      const approx = entry.date_is_approximate;
      const fromLower = (letter.from || '').toLowerCase();
      const filterClass = fromLower.includes('bob') ? 'bob' :
                          fromLower.includes('james') || fromLower.includes('dad') ? 'dad' :
                          fromLower.includes('headquarters') || fromLower.includes('colonel') ? 'official' : 'other';

      html += `
        <div class="tl-card ${approx ? 'approximate' : ''}" data-letter-id="${letter.id}" data-filter="${filterClass}" onclick="openLetter('${letter.id}')">
          <div class="tl-card-date">
            ${entry.date || 'Undated'}
            ${approx ? '<span class="approx-badge">estimated</span>' : ''}
          </div>
          <div class="tl-card-title">${escHtml(letter.from)} &rarr; ${escHtml(letter.to)}</div>
          <div class="tl-card-summary">${escHtml(entry.one_line_summary || letter.summary || '')}</div>
          <div class="tl-card-tags">
            ${(letter.topics || []).slice(0, 3).map(t => `<span class="tl-tag">${escHtml(t)}</span>`).join('')}
          </div>
        </div>
      `;
    });
  });
  container.innerHTML = html;
}

function scrollToYear(year) {
  const el = document.getElementById(`year-${year}`);
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function filterTimeline(filter, btn) {
  currentFilter = filter;
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');

  document.querySelectorAll('.tl-card').forEach(card => {
    if (filter === 'all') {
      card.dataset.hidden = 'false';
    } else {
      card.dataset.hidden = card.dataset.filter !== filter ? 'true' : 'false';
    }
  });
}

// ---- Chapters ----
function renderChapters() {
  const grid = document.getElementById('chapters-grid');
  grid.innerHTML = DATA.chapters.map((ch, i) => {
    const desc = (ch.description || '').substring(0, 200) + '...';
    const count = (ch.key_letters || []).length;
    return `
      <div class="chapter-card" onclick="showChapterDetail(${i})">
        <div class="ch-num">Chapter ${i + 1}</div>
        <div class="ch-title">${escHtml(ch.chapter_title)}</div>
        <div class="ch-dates">${escHtml(ch.date_range || '')}</div>
        <div class="ch-desc">${escHtml(desc)}</div>
        <div class="ch-count">${count} letters in this chapter</div>
      </div>
    `;
  }).join('');
}

function showChapterDetail(idx) {
  const ch = DATA.chapters[idx];
  const grid = document.getElementById('chapters-grid');
  const detail = document.getElementById('chapter-detail');
  grid.style.display = 'none';
  detail.style.display = 'block';

  const desc = [ch.description, ch.description_continued].filter(Boolean).join('\n\n');
  const descHtml = desc.split('\n\n').map(p => `<p>${escHtml(p.trim())}</p>`).join('');

  // Get letters for this chapter in chronological order
  const keyIds = new Set((ch.key_letters || []).map(String));
  const chLetters = DATA.chronological_order
    .filter(c => keyIds.has(String(c.letter_id)))
    .map(c => {
      const letter = DATA.letters.find(l => l.id === String(c.letter_id));
      return letter ? { ...letter, chrono: c } : null;
    })
    .filter(Boolean);

  const lettersHtml = chLetters.map(l => `
    <div class="letter-card" onclick="openLetter('${l.id}')">
      <div class="lc-date">${escHtml(l.chrono.date || l.date || 'Undated')}</div>
      <div class="lc-body">
        <div class="lc-correspondents">${escHtml(l.from)} &rarr; ${escHtml(l.to)}</div>
        <div class="lc-summary">${escHtml(l.summary || '')}</div>
      </div>
    </div>
  `).join('');

  detail.innerHTML = `
    <div class="chapter-detail-header">
      <button class="ch-back" onclick="closeChapterDetail()">&larr; Back to Chapters</button>
      <div class="section-label">Chapter ${idx + 1}</div>
      <h2 class="section-title">${escHtml(ch.chapter_title)}</h2>
      <div class="section-rule"></div>
      <div style="font-style:italic; color:var(--text-muted); margin-top:8px;">${escHtml(ch.date_range || '')}</div>
    </div>
    <div class="chapter-detail-desc">${descHtml}</div>
    <div class="chapter-letters-title">Letters in this chapter (${chLetters.length})</div>
    <div class="letter-list">${lettersHtml}</div>
  `;

  window.scrollTo({ top: detail.offsetTop - 80, behavior: 'smooth' });
}

function closeChapterDetail() {
  document.getElementById('chapters-grid').style.display = 'grid';
  document.getElementById('chapter-detail').style.display = 'none';
}

// ---- People ----
function renderPeople() {
  const grid = document.getElementById('people-grid');
  if (!grid) return;
  grid.innerHTML = DATA.profiles.map(p => {
    const aliases = (p.aliases || []).slice(0, 4).join(', ');
    const letterCount = (p.letters_appeared_in || []).length;
    return `
      <div class="person-card">
        <div class="pc-name">${escHtml(p.name)}</div>
        ${aliases ? `<div class="pc-aliases">${escHtml(aliases)}</div>` : ''}
        <div class="pc-role">${escHtml(p.role || '')}</div>
        <div class="pc-desc">${escHtml((p.description || '').substring(0, 300))}${(p.description || '').length > 300 ? '...' : ''}</div>
        <div class="pc-letters">Appears in ${letterCount} letters</div>
      </div>
    `;
  }).join('');
}

// ---- Search ----
function setupSearch() {
  const input = document.getElementById('search-input');
  let debounce;
  input.addEventListener('input', () => {
    clearTimeout(debounce);
    debounce = setTimeout(() => doSearch(input.value), 200);
  });
}

function doSearch(query) {
  const results = document.getElementById('search-results');
  if (!query || query.length < 2) {
    results.innerHTML = '';
    return;
  }

  const q = query.toLowerCase();
  const matches = [];

  DATA.letters.forEach(letter => {
    let score = 0;
    let snippets = [];

    // Search transcription
    const trans = (letter.transcription || '').toLowerCase();
    if (trans.includes(q)) {
      score += 10;
      const idx = trans.indexOf(q);
      const start = Math.max(0, idx - 60);
      const end = Math.min(trans.length, idx + q.length + 60);
      let snippet = letter.transcription.substring(start, end);
      if (start > 0) snippet = '...' + snippet;
      if (end < trans.length) snippet += '...';
      snippets.push(snippet);
    }

    // Search summary
    if ((letter.summary || '').toLowerCase().includes(q)) {
      score += 5;
      if (!snippets.length) snippets.push(letter.summary);
    }

    // Search people
    (letter.people || []).forEach(p => {
      if (p.toLowerCase().includes(q)) { score += 3; }
    });

    // Search places
    (letter.places || []).forEach(p => {
      if (p.toLowerCase().includes(q)) { score += 3; }
    });

    // Search topics
    (letter.topics || []).forEach(t => {
      if (t.toLowerCase().includes(q)) { score += 3; }
    });

    // Search sender/recipient
    if ((letter.from || '').toLowerCase().includes(q)) score += 4;
    if ((letter.to || '').toLowerCase().includes(q)) score += 4;

    // Search historical context
    if ((letter.historical_context || '').toLowerCase().includes(q)) {
      score += 2;
      if (!snippets.length) snippets.push(letter.historical_context);
    }

    if (score > 0) {
      matches.push({ letter, score, snippet: snippets[0] || letter.summary || '' });
    }
  });

  matches.sort((a, b) => b.score - a.score);

  if (matches.length === 0) {
    results.innerHTML = `<div class="search-result-count">No results for "${escHtml(query)}"</div>`;
    return;
  }

  const highlight = (text) => {
    if (!text) return '';
    const regex = new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
    return escHtml(text).replace(regex, '<mark>$1</mark>');
  };

  results.innerHTML = `
    <div class="search-result-count">${matches.length} result${matches.length !== 1 ? 's' : ''} for "${escHtml(query)}"</div>
    ${matches.slice(0, 30).map(m => `
      <div class="sr-card" onclick="openLetter('${m.letter.id}')">
        <div class="sr-header">
          <span class="sr-title">${highlight(m.letter.from)} &rarr; ${highlight(m.letter.to)}</span>
          <span class="sr-date">${escHtml(m.letter.date || m.letter.date_normalized || 'Undated')}</span>
        </div>
        <div class="sr-snippet">${highlight(m.snippet.substring(0, 200))}</div>
      </div>
    `).join('')}
  `;
}

// ---- Letter Modal ----
function buildChronoIndex() {
  chronoLetterIds = DATA.chronological_order.map(c => String(c.letter_id));
}

function openLetter(id) {
  const letter = DATA.letters.find(l => l.id === String(id));
  if (!letter) return;

  currentLetterIdx = chronoLetterIds.indexOf(String(id));

  const modal = document.getElementById('letter-modal');
  const body = document.getElementById('modal-body');

  // Nav buttons
  document.getElementById('modal-prev').disabled = currentLetterIdx <= 0;
  document.getElementById('modal-next').disabled = currentLetterIdx >= chronoLetterIds.length - 1;

  // Date display
  const dateStr = letter.date || letter.date_normalized || 'Date unknown';
  const approxHtml = letter.date_is_approximate ? '<span class="ld-approx">estimated date</span>' : '';

  // Meta grid
  let metaItems = '';
  if (letter.location && letter.location !== 'null')
    metaItems += metaItem('Written From', letter.location);
  if (letter.postmark && letter.postmark !== 'null')
    metaItems += metaItem('Postmark', letter.postmark);
  if (letter.mood && letter.mood !== 'null')
    metaItems += metaItem('Tone', letter.mood);
  if (letter.legibility && letter.legibility !== 'null')
    metaItems += metaItem('Legibility', letter.legibility);
  if (letter.topics && letter.topics.length)
    metaItems += metaItem('Topics', letter.topics.join(', '), true);
  if (letter.people && letter.people.length)
    metaItems += metaItem('People Mentioned', letter.people.join('; '), true);
  if (letter.places && letter.places.length)
    metaItems += metaItem('Places', letter.places.join(', '), true);
  if (letter.envelope_notes && letter.envelope_notes !== 'null')
    metaItems += metaItem('Envelope', letter.envelope_notes.substring(0, 300), true);

  // Scan images
  const scans = DATA.scan_manifest[letter.id] || [];
  const scansHtml = scans.length ? `
    <div class="ld-scans">
      <div class="ld-scans-label">Original Scans (${scans.length})</div>
      <div class="ld-scan-thumbs">
        ${scans.map((s, i) => `<img class="ld-scan-thumb" src="scans_web/${s.filename}" alt="${escHtml(s.label)}" onclick="showScanFull(this, ${i}, '${letter.id}')" title="${escHtml(s.label)}">`).join('')}
      </div>
      <div id="scan-full-container"></div>
    </div>
  ` : '';

  // Transcription
  const transHtml = letter.transcription ? `
    <div class="ld-transcription">
      <div class="ld-trans-label">Transcription</div>
      <div class="ld-trans-rule"></div>
      <div class="ld-trans-text">
        ${letter.transcription.split(/\n\n+/).map(p => `<p>${escHtml(p.trim()).replace(/\n/g, '<br>')}</p>`).join('')}
      </div>
    </div>
  ` : '';

  // Summary
  const summaryHtml = letter.summary ? `
    <div class="ld-summary">
      <div class="ld-summary-label">Editor's Note</div>
      <div class="ld-summary-text">${escHtml(letter.summary)}</div>
    </div>
  ` : '';

  // Historical context
  const histHtml = letter.historical_context && letter.historical_context !== 'null' && letter.historical_context.length > 10 ? `
    <div class="ld-history">
      <strong>Historical Context:</strong> ${escHtml(letter.historical_context)}
    </div>
  ` : '';

  body.innerHTML = `
    <div class="ld-header">
      <div class="ld-date">${escHtml(dateStr)} ${approxHtml}</div>
      <div class="ld-correspondents">From ${escHtml(letter.from)} to ${escHtml(letter.to)}</div>
      ${letter.location && letter.location !== 'null' ? `<div class="ld-location">${escHtml(letter.location)}</div>` : ''}
    </div>
    <div class="ld-meta">${metaItems}</div>
    ${scansHtml}
    ${transHtml}
    ${summaryHtml}
    ${histHtml}
  `;

  modal.style.display = 'flex';
  document.body.style.overflow = 'hidden';
  modal.querySelector('.modal-content').scrollTop = 0;
}

function metaItem(label, value, full) {
  return `<div class="ld-meta-item ${full ? 'ld-meta-full' : ''}"><div class="ld-meta-label">${escHtml(label)}</div><div class="ld-meta-value">${escHtml(value)}</div></div>`;
}

function closeModal() {
  document.getElementById('letter-modal').style.display = 'none';
  document.body.style.overflow = '';
  // Close lightbox too if open
  document.querySelectorAll('.lightbox').forEach(lb => lb.remove());
}

function navigateLetter(delta) {
  const newIdx = currentLetterIdx + delta;
  if (newIdx >= 0 && newIdx < chronoLetterIds.length) {
    openLetter(chronoLetterIds[newIdx]);
  }
}

// Scan viewer
function showScanFull(thumb, idx, letterId) {
  const scans = DATA.scan_manifest[letterId] || [];
  const scan = scans[idx];
  if (!scan) return;

  const container = document.getElementById('scan-full-container');
  container.innerHTML = `<img class="ld-scan-full" src="scans_web/${scan.filename}" alt="${escHtml(scan.label)}" onclick="openLightbox('scans_web/${scan.filename}')">`;
}

function openLightbox(src) {
  const lb = document.createElement('div');
  lb.className = 'lightbox';
  lb.innerHTML = `<img src="${src}" alt="Full scan">`;
  lb.onclick = () => lb.remove();
  document.body.appendChild(lb);
}

// ---- Keyboard ----
function setupKeyboard() {
  document.addEventListener('keydown', (e) => {
    // Escape closes modal
    if (e.key === 'Escape') {
      // Close lightbox first, then modal
      const lb = document.querySelector('.lightbox');
      if (lb) { lb.remove(); return; }
      closeModal();
    }
    // Arrow keys navigate letters in modal
    if (document.getElementById('letter-modal').style.display === 'flex') {
      if (e.key === 'ArrowLeft') navigateLetter(-1);
      if (e.key === 'ArrowRight') navigateLetter(1);
    }
    // Global search shortcut
    if (e.key === '/' && !e.ctrlKey && !e.metaKey && document.activeElement.tagName !== 'INPUT') {
      e.preventDefault();
      showSection('search');
    }
  });
}

// ---- Photos ----
let currentPhotoIdx = -1;

const PHOTO_CAT_LABELS = {
  'brothers': 'Brothers', 'military': 'Military', 'family-gathering': 'Family Gathering',
  'portrait': 'Portrait', 'location': 'Location', 'vehicle': 'Vehicle',
  'childhood': 'Childhood', 'document': 'Document', 'couple': 'Couple',
  'extended-family': 'Extended Family', 'memorial': 'Memorial'
};

function renderPhotos() {
  const grid = document.getElementById('photos-grid');
  const filtersEl = document.getElementById('photo-filters');
  const photos = DATA.photos || [];

  // Build category filter buttons
  const allCats = new Set();
  photos.forEach(p => (p.categories || []).forEach(c => allCats.add(c)));
  const sortedCats = [...allCats].sort();
  filtersEl.innerHTML = `
    <button class="filter-btn active" onclick="filterPhotos('all',this)">All (${photos.length})</button>
    ${sortedCats.map(c => {
      const count = photos.filter(p => (p.categories || []).includes(c)).length;
      return `<button class="filter-btn" onclick="filterPhotos('${c}',this)">${PHOTO_CAT_LABELS[c] || c} (${count})</button>`;
    }).join('')}
  `;

  // Render photo cards
  grid.innerHTML = photos.map((p, i) => {
    const cats = (p.categories || []).join(' ');
    const dateStr = p.date_estimate || '';
    const people = (p.people || []).join(', ');
    const letterLink = p.letter_id
      ? `<a class="photo-letter-link" onclick="event.stopPropagation();openLetter('${p.letter_id}')">View related letter &rarr;</a>`
      : '';

    return `
      <div class="photo-card" data-categories="${escHtml(cats)}" onclick="openPhotoLightbox(${i})">
        <img src="photos_web/${p.filename}" alt="${escHtml(p.caption)}" loading="lazy">
        <div class="photo-caption">
          ${dateStr ? `<div class="photo-date">${escHtml(dateStr)}</div>` : ''}
          ${escHtml(p.caption)}
          ${people ? `<div class="photo-people">${escHtml(people)}</div>` : ''}
          <div class="photo-tags">
            ${(p.categories || []).map(c => `<span class="photo-tag">${PHOTO_CAT_LABELS[c] || c}</span>`).join('')}
          </div>
          ${letterLink}
          ${p.back ? '<div class="photo-back-note">Has writing on back &middot; click to view</div>' : ''}
        </div>
      </div>
    `;
  }).join('');
}

function filterPhotos(cat, btn) {
  document.querySelectorAll('.photos-filters .filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  document.querySelectorAll('.photo-card').forEach(card => {
    if (cat === 'all') {
      card.dataset.hidden = 'false';
    } else {
      const cats = (card.dataset.categories || '').split(' ');
      card.dataset.hidden = cats.includes(cat) ? 'false' : 'true';
    }
  });
}

function openPhotoLightbox(idx) {
  const photos = DATA.photos || [];
  if (idx < 0 || idx >= photos.length) return;
  currentPhotoIdx = idx;
  const photo = photos[idx];
  let showingBack = false;

  // Remove any existing lightbox
  document.querySelectorAll('.lightbox').forEach(lb => lb.remove());

  const captionParts = [photo.caption];
  if (photo.date_estimate) captionParts.unshift(photo.date_estimate + ' —');
  if (photo.people && photo.people.length) captionParts.push('(' + photo.people.join(', ') + ')');

  const lb = document.createElement('div');
  lb.className = 'lightbox';
  lb.style.cursor = 'default';
  lb.innerHTML = `
    <img src="photos_web/${photo.filename}" alt="${escHtml(photo.caption)}" style="max-width:90vw;max-height:85vh;object-fit:contain;">
    <div class="photo-lightbox-caption">${escHtml(captionParts.join(' '))}</div>
    <button class="photo-lightbox-close" onclick="this.parentElement.remove()">&times;</button>
    <button class="photo-lightbox-nav prev" onclick="event.stopPropagation();navigatePhoto(-1)">&lsaquo;</button>
    <button class="photo-lightbox-nav next" onclick="event.stopPropagation();navigatePhoto(1)">&rsaquo;</button>
    ${photo.back ? '<button class="photo-lightbox-flip visible" onclick="event.stopPropagation();flipPhoto(this)">Show Back</button>' : ''}
  `;

  // Click backdrop to close (but not on controls)
  lb.addEventListener('click', (e) => {
    if (e.target === lb) lb.remove();
  });

  document.body.appendChild(lb);
}

function navigatePhoto(delta) {
  const photos = DATA.photos || [];
  const newIdx = currentPhotoIdx + delta;
  if (newIdx >= 0 && newIdx < photos.length) {
    document.querySelectorAll('.lightbox').forEach(lb => lb.remove());
    openPhotoLightbox(newIdx);
  }
}

function flipPhoto(btn) {
  const photos = DATA.photos || [];
  const photo = photos[currentPhotoIdx];
  if (!photo) return;
  const lb = btn.closest('.lightbox');
  const img = lb.querySelector('img');
  const isBack = btn.textContent === 'Show Front';
  if (isBack) {
    img.src = `photos_web/${photo.filename}`;
    btn.textContent = 'Show Back';
  } else {
    img.src = `photos_web/${photo.back}`;
    btn.textContent = 'Show Front';
  }
}

// ---- Highlights ----
const HIGHLIGHTS = [
  {"letter_id":"1","excerpt":"These chicken shit draft board have deferred every body with a pimple on their butt. If I was you I would tell that draft board in Des Moines to kiss your ass.","context":"Bob writes to his brother John, a corporal serving in Korea, furious at the draft system that keeps civilians home while John remains overseas.","category":"military-life"},
  {"letter_id":"2","excerpt":"Got to write, I don\u2019t know quite why but I know I have really screwed the works up. It wouldn\u2019t be so bad, but I wanted to carry through a deal like this just to show you I could, but I didn\u2019t. I\u2019m a big kid now, but right now I feel like crying.","context":"Jim Jr. writes home to his father in February 1946 after botching a car errand \u2014 a raw, unguarded moment of shame from a young man just out of military service.","category":"emotion"},
  {"letter_id":"3","excerpt":"This Russian situation don\u2019t look to good to me, as we are in the hot spot right here. I was playing catch with the Lt. yesterday, boy he sure is a swell guy. I am learning Dego pretty good. At least I know what the score is.","context":"Bob writes from post-war Italy in March 1946, sandwiching his worry about the emerging Cold War between a game of catch and a language lesson.","category":"history"},
  {"letter_id":"4","excerpt":"Her name is Anna, she is really nice compared to this other woman mainly because she is clean, well clean anyway. All the boys think she is alright. I am not going to get married so don\u2019t worry. Just somebody to dance, remember the song.","context":"Bob reassures his father about a girl he met at the Red Cross in Caserta, Italy \u2014 in the most diplomatic terms he can muster.","category":"humor"},
  {"letter_id":"6","excerpt":"These god damn M.P.\u2019s are what. Causing us all the trouble overseas. Brig up last night for having a button no bottom. What a lot of shit.","context":"Bob vents about the indignities of military life in post-war Italy, where a missing uniform button lands him in the brig.","category":"humor"},
  {"letter_id":"7","excerpt":"I am going out to one of my girl friend house Sun. She lives about 20 miles out. She is going to have chicken for dinner. God help her if she don\u2019t. I have had chicken only 3 times since I left home.","context":"Bob writes from ASTP training at the University of Wyoming in 1944, fantasizing about the chicken dinner a girl has promised him twenty miles out of Laramie.","category":"humor"},
  {"letter_id":"8","excerpt":"I got a Hinie to sharpen it up sand the handle and polish it. They will do it for nothing but the next you will find them to busy but give him a smoke and he will be your man for anything. They salute us all the time, what a life.","context":"Bob describes the barter economy of post-war Italy, where a cigarette buys the labor of a German POW \u2014 and their perpetual salutes.","category":"military-life"},
  {"letter_id":"8","excerpt":"Met an Austrian woman at the Red Cross Club she couldnt speak a word of English this guy with me can understand a little Dego so we got along all right. She can speak five language but no English. Her brother was killed by the german and she and her sister made a run for it they used to live in Youslavia before the war.","context":"Bob recounts meeting a displaced Austrian refugee at a Red Cross dance in Caserta \u2014 a quiet reminder of the human wreckage World War II left across Europe.","category":"history"},
  {"letter_id":"9","excerpt":"Ive run into a little trouble the medicine to help my bones from degenerating has caused me to lose over \u00bd of my hair its very thin & have had to go to a couple new drs & each one wants this & that test.","context":"Aunt Pauline writes to Bob in 1976 with the unsentimental news that her bone medication is taking her hair \u2014 the collection\u2019s final letter, thirty-five years after the first.","category":"family"},
  {"letter_id":"11","excerpt":"Wed. afternoon a kid two bags from me about 36 feet was shot by another kid messing around with a 45. The slug entered his right side and came out the left side hitting his arm at the elbow and then glance off two walls. The bullet just missed his heart by 1/4 of inch.","context":"Bob buries a harrowing near-fatal accidental shooting \u2014 a peacetime casualty of military carelessness \u2014 inside a routine letter home from post-war Italy.","category":"military-life"},
  {"letter_id":"16","excerpt":"Bob starts off at 6 AM + goes right thru untill 10:30 PM. In about a 3 weeks, He will no he is in Hell too. Ill bet a Buck.","context":"Dad writes to Jim Jr. in July 1944, passing along Bob\u2019s address at the ASTP program in Wyoming with his own dry assessment of what awaits his youngest son.","category":"family"},
  {"letter_id":"16","excerpt":"Bob dont get a dam penny while in school, even how to Send him Towels, + I suppose I will have to send him Soap + Toilet paper.","context":"Dad reports on the hidden costs of Bob\u2019s Army college program \u2014 not just tuition, but toiletries \u2014 in his characteristically blunt shorthand.","category":"family"},
  {"letter_id":"24","excerpt":"I was coming back through Naples at about 7:00 with my float and the street was filled completely with people, about 2000 of them. I didn\u2019t know what to do exactly, so I asked the German. He handed me my 45 pistol. I said not yet, and put my tractor in 3rd and started plowing through. At 10:00 that same night they had a riot there \u2014 14 people were killed and 8 cops.","context":"Bob recounts driving a military float through a crowd of two thousand Neapolitans, hours before a deadly riot erupts in the same streets.","category":"adventure"},
  {"letter_id":"24","excerpt":"The German PW went on strike Wed. morning for more food, so we had to stand guard over them. I was in a tower about 60 feet high with a machine gun. None of them boys to go away. They went back to work that afternoon.","context":"Bob casually describes standing sixty-foot guard over striking German POWs in Naples \u2014 part of the strange, tense choreography of occupation Italy.","category":"history"},
  {"letter_id":"28","excerpt":"This new bomb might get me home a little quicker I hope. But I don\u2019t know.","context":"Bob writes from Chanute Field on August 9, 1945 \u2014 the day of the Nagasaki bombing \u2014 processing the atomic age in one unsure, homesick sentence.","category":"history"},
  {"letter_id":"28","excerpt":"Just heard about the Japs wanting to surrender. Hope they do. I don\u2019t know what I will do this weekin yet. I will try to get home the week after next. Hope I can do it. Say hello to every-body.","context":"The day after Nagasaki, Bob notes Japan\u2019s surrender bid with quiet relief and pivots immediately to his weekend plans and wishes for the family.","category":"history"},
  {"letter_id":"35","excerpt":"He numbed the gum got a knife, tooth pullers, chisels, everything you can think of. He really went in about 20 min of cutting, chiseling, pulling he had it out. You should see me all swelled up on one side. It didn\u2019t hurt too bad, but it sure scared Hell out of me.","context":"Bob describes his Army wisdom-tooth extraction at Chanute Field with the thoroughness of a battlefield report \u2014 and the same cheerful stoicism.","category":"humor"},
  {"letter_id":"45","excerpt":"I don\u2019t know what the war ending will affect me. Probably will get 2 years in the Islands as occupation army. Sure hope not.","context":"Written August 13, 1945 \u2014 just days after Japan\u2019s surrender \u2014 Bob tacks a two-sentence meditation on his uncertain future onto the end of a breezy letter about a weekend in Peoria.","category":"history"},
  {"letter_id":"46","excerpt":"No dance tonight on account of the president\u2019s death, sure hated to hear about it. Boy they drafted about half of Iowa it seems. Every town here it seems is from the farms.","context":"Bob writes from Fort Leavenworth on April 15, 1945 \u2014 three days after FDR died \u2014 noting the cancelled dance and the overwhelmingly rural Iowa faces around him.","category":"history"},
  {"letter_id":"51","excerpt":"I now work for Texaco gasoline making $206.50 a month, not bad for a nut like me. I hear you are a Cpl and keep up the good work and get a Sgt. stripe so the old man can\u2019t say he was the only Sgt. in the family.","context":"Bob writes to his brother John in Korea from Dallas, where civilian life has settled into Texaco sales \u2014 and the old family rivalries are very much alive.","category":"family"},
  {"letter_id":"52","excerpt":"I was rudely awakely at 6:30 the yelling of a Dozen guys, yelling gas attack, in a flash I was up. Took a quick breath and turn around to get my mask. In a flash I had it on, clear it and starting to breath again I could see the gas coming in through the windows. Somebody said it was Memorial Day. Hell I didn\u2019t even know it.","context":"The surreal experience of Memorial Day 1945 at Sheppard Field, which began with a surprise tear gas attack at 6:30 in the morning.","category":"military-life"},
  {"letter_id":"55","excerpt":"What are you doing in Korea, running the war all by yourself. You have been there long enough. I have good news for you, there is a guy here in Dallas who have been slipping by for a long time and they finally got him, he leaves the 16th of July.","context":"Bob teases John in Korea in July 1952 with the only good news he can find: at least one draft-dodger in Dallas has finally been caught.","category":"humor"},
  {"letter_id":"57","excerpt":"This is the Day, The Republicans & Eisenhower are Shouting. I don\u2019t No, but what, he might Make it. It is a little quiet here You No a Big Steel Strike is still on. If you got any Bitching to do, Put it in the Letter. Love Dad","context":"Dad writes to John in Korea on July 12, 1952 \u2014 the day of Eisenhower\u2019s nomination \u2014 covering the Republican convention, the steel strike, and brotherly complaints in one brief dispatch.","category":"home-front"},
  {"letter_id":"58","excerpt":"Duck, went thru here like a Bat out of Hell, Cold hit up North, they Moved out of Minsota, then a Cold Blast Sent them on thru Iowa, Just a little Snow flurries here, But So early in the fall. All the Places around Iowa Caught Hell.","context":"Dad\u2019s November 1951 letter to John in Korea captures the kinetic Iowa autumn in a single run-on sentence of ducks, cold fronts, and snowstorms.","category":"home-front"},
  {"letter_id":"58","excerpt":"They are Sure Chomping the guys as they come Back from Korea got a guy for $485 that He Spent in Korea & one of his good friends took him. They all Say the Same thing didn\u2019t No you had any Money at all.","context":"Dad warns John, still serving in Korea in 1951, about the financial predators waiting for returning soldiers \u2014 a quiet, furious paragraph tucked between hunting news and birthday wishes.","category":"home-front"},
  {"letter_id":"84","excerpt":"ARRIVAL, NAPLES, ITALY: 19 February, 1300 hours. DISTANCE FROM NEW YORK: 4331 MILES. TOTAL LENGTH OF VOYAGE, 11 days, 5 hours, 35 minutes. Keep this for me. Bobby","context":"Bob mails home the printed voyage log from the troopship SS NYU Victory \u2014 4,331 miles from New York to Naples \u2014 with just four handwritten words at the bottom.","category":"adventure"},
  {"letter_id":"1","excerpt":"P.S. Keep your eyes open for those sneaking red bastards.","context":"Bob closes his letter to John in Korea with a postscript that distills his whole anxious brotherly concern into one colorful line.","category":"humor"},
  {"letter_id":"1","excerpt":"Jimmy says he has a nice 51 Ford for you to drive when you get home. You two are lucky for that. This old 46 Chrysler I got isn\u2019t worth a good shit.","context":"Bob cheers up his brother John in Korea with the promise of a car waiting at home, and can\u2019t resist taking a swipe at his own wheels.","category":"family"},
  {"letter_id":"4","excerpt":"Naples is off limits the 18 of March, to much V.D. says the Army. This country is all closed up. Don\u2019t work at all in the afternoon, just sit around and talk all day. Not a bad life at all.","context":"Bob matter-of-factly reports on post-war occupation life in southern Italy, where the Army\u2019s public health orders have shut down the city.","category":"military-life"}
];

const CATEGORY_LABELS = {
  'humor': 'Humor',
  'emotion': 'Emotion',
  'history': 'History',
  'military-life': 'Military Life',
  'family': 'Family',
  'adventure': 'Adventure',
  'home-front': 'Home Front'
};

function renderHighlights() {
  const container = document.getElementById('highlights-list');
  let html = '';
  HIGHLIGHTS.forEach((h, i) => {
    const letter = DATA.letters.find(l => l.id === String(h.letter_id));
    const dateStr = letter ? (letter.date || letter.date_normalized || '') : '';
    const from = letter ? letter.from : '';

    html += `
      <div class="highlight-card" data-category="${h.category}">
        <div class="highlight-category" data-cat="${h.category}">${CATEGORY_LABELS[h.category] || h.category}</div>
        <div class="highlight-excerpt">${escHtml(h.excerpt)}</div>
        <div class="highlight-context">${escHtml(h.context)}</div>
        <a class="highlight-link" onclick="openLetter('${h.letter_id}')">
          Read full letter${from ? ' from ' + escHtml(from) : ''}${dateStr ? ', ' + escHtml(dateStr) : ''} &rarr;
        </a>
      </div>
    `;
    if (i < HIGHLIGHTS.length - 1) {
      html += '<div class="highlight-divider"></div>';
    }
  });
  container.innerHTML = html;
}

function filterHighlights(cat, btn) {
  document.querySelectorAll('.highlights-filters .filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  document.querySelectorAll('.highlight-card').forEach(card => {
    if (cat === 'all') {
      card.dataset.hidden = 'false';
      card.nextElementSibling && card.nextElementSibling.classList.contains('highlight-divider') && (card.nextElementSibling.style.display = '');
    } else {
      const match = card.dataset.category === cat;
      card.dataset.hidden = match ? 'false' : 'true';
    }
  });
  // Fix divider visibility
  const visible = [...document.querySelectorAll('.highlight-card[data-hidden="false"]')];
  document.querySelectorAll('.highlight-divider').forEach(d => d.style.display = 'none');
  visible.forEach((card, i) => {
    if (i < visible.length - 1 && card.nextElementSibling && card.nextElementSibling.classList.contains('highlight-divider')) {
      card.nextElementSibling.style.display = '';
    }
  });
}

// ---- Utils ----
function escHtml(str) {
  if (!str) return '';
  const div = document.createElement('div');
  div.textContent = String(str);
  return div.innerHTML;
}

// ---- Audio Player (Plyr) ----
const plyrPlayer = new Plyr('#audio-el', {
  controls: ['play', 'progress', 'current-time', 'duration', 'mute', 'volume'],
  seekTime: 30,
  tooltips: { seek: true },
  invertTime: false,
});
"""


if __name__ == "__main__":
    main()
