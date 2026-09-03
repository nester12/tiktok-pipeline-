# Public-domain story structure learner.
#
# Purpose:
# - Give the generator deeper, proven story architecture and twist mechanics.
# - Use curated short stories by authors whose original works are public domain.
# - Never export the source prose to the generator. Only abstract plot/beat analysis
#   is saved, so the generator learns structure rather than copying wording.

import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional

import requests

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GEMINI_MODEL = os.getenv("GEMINI_STYLE_MODEL", "gemini-3.7-flash")
GROQ_MODEL = os.getenv("GROQ_STYLE_MODEL", "openai/gpt-oss-120b")

OUTPUT_FILE = "public_domain_story_patterns.json"
STYLE_NOTES_FILE = "style_notes.txt"
REQUEST_TIMEOUT = 45
MAX_STORIES_PER_RUN = 8
MIN_STORY_WORDS = 250
MAX_STORY_WORDS = 9000

# Curated collections chosen for compact plots, misdirection and strong endings.
# O. Henry died in 1910 and Saki in 1916, so their original works are also
# out of copyright in the UK under the normal life+70 literary term.
PUBLIC_DOMAIN_COLLECTIONS = [
    {
        "author": "O. Henry",
        "ebook_id": 2776,
        "book": "The Four Million",
        "source_page": "https://www.gutenberg.org/ebooks/2776",
        "titles": [
            "After Twenty Years",
            "The Green Door",
            "The Furnished Room",
            "The Cop and the Anthem",
            "Mammon and the Archer",
            "The Gift of the Magi",
        ],
    },
    {
        "author": "Saki",
        "ebook_id": 269,
        "book": "Beasts and Super-Beasts",
        "source_page": "https://www.gutenberg.org/ebooks/269",
        "titles": [
            "The Open Window",
            "Dusk",
            "The Story-Teller",
            "The Lumber Room",
            "The Blind Spot",
            "A Touch of Realism",
        ],
    },
]

session = requests.Session()
session.headers.update({"User-Agent": "tiktok-pipeline-public-domain-learner/1.0"})


def normalize_heading(value: str) -> str:
    value = value.strip().lower()
    value = value.replace("’", "'").replace("“", '"').replace("”", '"')
    value = re.sub(r"[^a-z0-9']+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def strip_gutenberg_boilerplate(text: str) -> str:
    start = re.search(r"\*\*\*\s*START OF (?:THE|THIS) PROJECT GUTENBERG EBOOK.*?\*\*\*", text, re.I | re.S)
    end = re.search(r"\*\*\*\s*END OF (?:THE|THIS) PROJECT GUTENBERG EBOOK.*?\*\*\*", text, re.I | re.S)
    if start:
        text = text[start.end():]
    if end:
        text = text[:end.start()]
    return text.strip()


def download_collection(ebook_id: int) -> Optional[str]:
    urls = [
        f"https://www.gutenberg.org/cache/epub/{ebook_id}/pg{ebook_id}.txt",
        f"https://www.gutenberg.org/files/{ebook_id}/{ebook_id}-8.txt",
        f"https://www.gutenberg.org/files/{ebook_id}/{ebook_id}.txt",
    ]
    for url in urls:
        try:
            response = session.get(url, timeout=REQUEST_TIMEOUT)
            if response.status_code == 200 and len(response.text) > 5000:
                print(f"📚 Downloaded Project Gutenberg #{ebook_id}")
                return strip_gutenberg_boilerplate(response.text)
        except requests.RequestException as exc:
            print(f"⚠️ Could not download {url}: {exc}")
    return None


def find_title_indices(lines: List[str], titles: List[str]) -> Dict[str, int]:
    wanted = {normalize_heading(title): title for title in titles}
    found: Dict[str, int] = {}
    for index, line in enumerate(lines):
        normalized = normalize_heading(line)
        title = wanted.get(normalized)
        if title and title not in found:
            found[title] = index
    return found


def extract_story(text: str, title: str, all_titles: List[str]) -> Optional[str]:
    lines = text.splitlines()
    indices = find_title_indices(lines, all_titles)
    start = indices.get(title)
    if start is None:
        return None

    later = [position for name, position in indices.items() if position > start]
    end = min(later) if later else len(lines)
    body = "\n".join(lines[start + 1:end]).strip()
    body = re.sub(r"\n{3,}", "\n\n", body)
    words = body.split()
    if len(words) < MIN_STORY_WORDS:
        return None
    if len(words) > MAX_STORY_WORDS:
        body = " ".join(words[:MAX_STORY_WORDS])
    return body


def parse_json(text: str) -> Optional[dict]:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        value = json.loads(cleaned)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            try:
                value = json.loads(cleaned[start:end + 1])
                return value if isinstance(value, dict) else None
            except json.JSONDecodeError:
                return None
    return None


def analysis_prompt(title: str, author: str, story: str) -> str:
    return f"""
Analyse this PUBLIC-DOMAIN short story only for reusable narrative STRUCTURE.
Do not quote the prose and do not preserve distinctive names, locations, objects,
or exact events in your analysis. We want abstract storytelling mechanics that can
inspire a completely new TikTok/Reddit-style story.

Return ONLY valid JSON with this schema:
{{
  "premise_pattern": "abstract one-sentence premise pattern",
  "hook_pattern": "how curiosity is created near the beginning",
  "conflict_pattern": "central conflict in abstract terms",
  "escalation_pattern": "how stakes rise",
  "misdirection": "what assumption the audience is encouraged to make",
  "twist_type": "identity|irony|hidden_motive|false_assumption|reversal|coincidence|recontextualisation|other",
  "twist_setup": "what information quietly prepares the twist",
  "reveal_mechanism": "how the reveal lands",
  "payoff_pattern": "why the ending feels satisfying or memorable",
  "emotional_arc": ["emotion1", "emotion2", "emotion3"],
  "beat_sequence": ["hook", "context", "conflict", "escalation", "..."],
  "adaptable_theme": "broad modern theme this structure could support",
  "retention_lessons": ["short lesson 1", "short lesson 2", "short lesson 3"]
}}

Rules:
- Be structural, not literary.
- Do not include direct quotations.
- Do not reproduce character names or distinctive source details.
- Focus especially on setup, misdirection, twist and payoff.
- A future writer must be able to use this pattern while creating entirely new
  characters, setting, events and ending details.

Source title: {title}
Source author: {author}

Story text for analysis:
{story}
""".strip()


def call_gemini(api_key: str, prompt: str) -> Optional[dict]:
    if not api_key:
        return None
    try:
        response = session.post(
            f"{GEMINI_BASE}/models/{GEMINI_MODEL}:generateContent",
            params={"key": api_key},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "temperature": 0.2,
                    "maxOutputTokens": 1800,
                },
            },
            timeout=75,
        )
        if response.status_code != 200:
            print(f"⚠️ Gemini pattern analysis failed: {response.status_code} {response.text[:180]}")
            return None
        text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
        return parse_json(text)
    except (requests.RequestException, KeyError, IndexError, ValueError) as exc:
        print(f"⚠️ Gemini pattern analysis error: {exc}")
        return None


def call_groq(api_key: str, prompt: str) -> Optional[dict]:
    if not api_key:
        return None
    try:
        response = session.post(
            GROQ_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": GROQ_MODEL,
                "messages": [
                    {"role": "system", "content": "Analyse story structure. Return JSON only."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
                "max_tokens": 1800,
                "response_format": {"type": "json_object"},
            },
            timeout=75,
        )
        if response.status_code != 200:
            print(f"⚠️ Groq pattern analysis failed: {response.status_code} {response.text[:180]}")
            return None
        return parse_json(response.json()["choices"][0]["message"]["content"])
    except (requests.RequestException, KeyError, IndexError, ValueError) as exc:
        print(f"⚠️ Groq pattern analysis error: {exc}")
        return None


def load_existing() -> List[dict]:
    try:
        if Path(OUTPUT_FILE).exists():
            data = json.loads(Path(OUTPUT_FILE).read_text(encoding="utf-8"))
            if isinstance(data, list):
                return [item for item in data if isinstance(item, dict)]
    except Exception as exc:
        print(f"⚠️ Could not load {OUTPUT_FILE}: {exc}")
    return []


def clean_pattern(value: dict) -> dict:
    allowed = {
        "premise_pattern", "hook_pattern", "conflict_pattern", "escalation_pattern",
        "misdirection", "twist_type", "twist_setup", "reveal_mechanism",
        "payoff_pattern", "emotional_arc", "beat_sequence", "adaptable_theme",
        "retention_lessons",
    }
    return {key: value.get(key) for key in allowed if key in value}


def update_style_notes(patterns: List[dict]) -> None:
    existing = ""
    if Path(STYLE_NOTES_FILE).exists():
        existing = Path(STYLE_NOTES_FILE).read_text(encoding="utf-8").strip()
    marker = "\n\nPUBLIC-DOMAIN TWIST PATTERNS\n"
    if marker.strip() in existing:
        existing = existing.split(marker.strip(), 1)[0].rstrip()

    strongest = patterns[-8:]
    lines = [
        "PUBLIC-DOMAIN TWIST PATTERNS",
        "Use these as structural inspiration only. Create new people, settings, events, objects and wording.",
        "Do not copy or lightly modernise a source story.",
    ]
    for item in strongest:
        pattern = item.get("pattern", {})
        lines.append(
            "- "
            + str(pattern.get("twist_type", "twist"))
            + ": hook=" + str(pattern.get("hook_pattern", ""))[:180]
            + "; misdirection=" + str(pattern.get("misdirection", ""))[:180]
            + "; payoff=" + str(pattern.get("payoff_pattern", ""))[:180]
        )

    combined = (existing + "\n\n" + "\n".join(lines)).strip() + "\n"
    Path(STYLE_NOTES_FILE).write_text(combined, encoding="utf-8")


def main() -> None:
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    groq_key = os.getenv("GROQ_API_KEY", "")
    if not gemini_key and not groq_key:
        raise ValueError("Set GEMINI_API_KEY or GROQ_API_KEY for public-domain story analysis.")

    existing = load_existing()
    by_id = {str(item.get("source_id")): item for item in existing if item.get("source_id")}
    analysed_this_run = 0

    for collection in PUBLIC_DOMAIN_COLLECTIONS:
        text = download_collection(collection["ebook_id"])
        if not text:
            continue
        for title in collection["titles"]:
            source_id = f"gutenberg-{collection['ebook_id']}-{normalize_heading(title).replace(' ', '-')}"
            if source_id in by_id:
                continue
            if analysed_this_run >= MAX_STORIES_PER_RUN:
                break

            story = extract_story(text, title, collection["titles"])
            if not story:
                print(f"⚠️ Could not isolate '{title}' in Gutenberg #{collection['ebook_id']}")
                continue

            print(f"🧠 Analysing public-domain structure: {collection['author']} — {title}")
            prompt = analysis_prompt(title, collection["author"], story)
            analysis = call_gemini(gemini_key, prompt)
            if not analysis:
                analysis = call_groq(groq_key, prompt)
            if not analysis:
                continue

            entry = {
                "source_id": source_id,
                "source_title": title,
                "author": collection["author"],
                "collection": collection["book"],
                "source_url": collection["source_page"],
                "rights_note": "Original literary work is public domain; generator receives structural analysis only.",
                "pattern": clean_pattern(analysis),
            }
            by_id[source_id] = entry
            analysed_this_run += 1

        if analysed_this_run >= MAX_STORIES_PER_RUN:
            break

    patterns = list(by_id.values())
    Path(OUTPUT_FILE).write_text(json.dumps(patterns, indent=2, ensure_ascii=False), encoding="utf-8")
    update_style_notes(patterns)
    print(f"✅ Saved {len(patterns)} public-domain story patterns ({analysed_this_run} newly analysed).")


if __name__ == "__main__":
    main()
