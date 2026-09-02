# -------------------------------------------------------------------
# Story Generator (Gemini primary, Groq fallback)
# -------------------------------------------------------------------
import os
import json
import random
import requests

STORY_OUTPUT_FILE = "story.txt"
STYLE_EXAMPLES_FILE = "style_examples.json"
STYLE_NOTES_FILE = "style_notes.txt"
TREND_SUMMARY_FILE = "trend_summary.json"
RECENT_TOPICS_FILE = "recent_story_topics.json"

GEMINI_MODEL = os.environ.get("GEMINI_STORY_MODEL", "gemini-3.7-flash")
GROQ_MODEL = os.environ.get("GROQ_STORY_MODEL", "openai/gpt-oss-120b")

STORY_NICHES = [
    "a shocking family secret discovered at a holiday dinner",
    "a roommate who crossed every boundary imaginable",
    "catching a partner in a lie that changed everything",
    "a wedding that fell apart in the most dramatic way",
    "a neighbor feud that escalated way too far",
    "a workplace betrayal by someone you trusted",
    "a landlord doing something completely unhinged",
    "a friend group falling apart over one secret",
    "an inheritance that tore a family apart",
    "a stranger's act of kindness that changed a bad day",
]

EXAMPLES = (
    "EXAMPLE 1:\n"
    "My sister asked me to babysit for 'an hour,' but that was six hours ago, and she wasn't "
    "answering any of my calls. So I checked her location, and she was at a hotel two towns "
    "over — not working, not stuck in traffic, just at a hotel. I packed the kids' bags right "
    "there, and when she finally walked in laughing, I was already at the door. I didn't yell, "
    "I just said 'never again' and left. She's called me eleven times since, and I still haven't "
    "answered once.\n\n"
    "EXAMPLE 2:\n"
    "My roommate kept eating my leftovers, so instead of labeling them again, I made a new dish "
    "that looked identical to my usual dinner but smelled amazing. She grabbed it the second I "
    "left for work, and four hours later I got a text in all caps asking what I put in it. It was "
    "just extremely hot ghost pepper sauce. She moved out two weeks later, and I still make that "
    "dish — nobody touches my food anymore.\n\n"
    "EXAMPLE 3:\n"
    "My landlord raised my rent by four hundred dollars with zero notice, and when I asked why, "
    "he just said 'market rates.' So I pulled up every violation in the building — the broken "
    "heater, the mold in the hallway, the missing fire extinguishers — and emailed the housing "
    "board that same night. Three weeks later, inspectors showed up unannounced, and my rent "
    "increase mysteriously disappeared. Funny how that works.\n\n"
)


def load_json(path, default):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as exc:
        print(f"⚠️ Could not read {path}: {exc}")
    return default


def load_recent_topics():
    data = load_json(RECENT_TOPICS_FILE, [])
    if not isinstance(data, list):
        return []
    return [str(item).strip() for item in data if str(item).strip()][-12:]


def remember_topic(topic):
    recent = load_recent_topics()
    recent.append(topic)
    recent = recent[-12:]
    try:
        with open(RECENT_TOPICS_FILE, "w", encoding="utf-8") as f:
            json.dump(recent, f, indent=2, ensure_ascii=False)
    except Exception as exc:
        print(f"⚠️ Could not save recent topic history: {exc}")


def normalize_topic_entry(entry):
    if isinstance(entry, str):
        return entry.strip(), 1.0
    if isinstance(entry, (list, tuple)) and entry:
        topic = str(entry[0]).strip()
        try:
            weight = max(float(entry[1]), 1.0) if len(entry) > 1 else 1.0
        except (TypeError, ValueError):
            weight = 1.0
        return topic, weight
    if isinstance(entry, dict):
        topic = str(entry.get("topic") or entry.get("name") or "").strip()
        try:
            weight = max(float(entry.get("score") or entry.get("count") or 1), 1.0)
        except (TypeError, ValueError):
            weight = 1.0
        return topic, weight
    return "", 0.0


def load_trending_topics():
    summary = load_json(TREND_SUMMARY_FILE, {})
    raw_topics = summary.get("top_topics", []) if isinstance(summary, dict) else []
    topics = []
    for entry in raw_topics:
        topic, weight = normalize_topic_entry(entry)
        if topic:
            topics.append((topic, weight))
    return topics


def is_recently_used(topic, recent):
    topic_words = set(topic.lower().split())
    for old in recent:
        old_words = set(old.lower().split())
        if topic.lower() == old.lower():
            return True
        if topic_words and old_words:
            overlap = len(topic_words & old_words) / max(len(topic_words | old_words), 1)
            if overlap >= 0.65:
                return True
    return False


def weighted_trend_choice(trending, recent):
    available = [(topic, weight) for topic, weight in trending if not is_recently_used(topic, recent)]
    if not available:
        available = trending
    if not available:
        return None
    return random.choices(
        [item[0] for item in available],
        weights=[item[1] for item in available],
        k=1,
    )[0]


def create_topic_variation(base_topic):
    variations = [
        f"a completely different situation involving {base_topic}, with new people, motives, and consequences",
        f"an unexpected personal conflict connected to {base_topic}, told from a different point of view",
        f"a relatable everyday situation that starts around {base_topic} but escalates in an original direction",
        f"a new high-stakes misunderstanding involving {base_topic}, without copying any existing story details",
    ]
    return random.choice(variations)


def select_story_niche():
    recent = load_recent_topics()
    trending = load_trending_topics()
    roll = random.random()

    if trending and roll < 0.70:
        niche = weighted_trend_choice(trending, recent)
        mode = "proven trend"
    elif trending and roll < 0.90:
        base = weighted_trend_choice(trending, recent)
        niche = create_topic_variation(base) if base else None
        mode = "trend variation"
    else:
        choices = [topic for topic in STORY_NICHES if not is_recently_used(topic, recent)]
        niche = random.choice(choices or STORY_NICHES)
        mode = "experiment"

    if not niche:
        choices = [topic for topic in STORY_NICHES if not is_recently_used(topic, recent)]
        niche = random.choice(choices or STORY_NICHES)
        mode = "fallback experiment"

    print(f"🧭 Topic selection: {mode}")
    remember_topic(niche)
    return niche


def load_examples_text():
    if os.path.exists(STYLE_EXAMPLES_FILE):
        try:
            with open(STYLE_EXAMPLES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data:
                ranked = sorted(
                    data,
                    key=lambda ex: ex.get("trend_score", ex.get("video_score", ex.get("views", 0))) or 0,
                    reverse=True,
                )
                sample = ranked[: min(5, len(ranked))]
                text = ""
                for i, ex in enumerate(sample, 1):
                    transcript = (ex.get("full_transcript") or ex.get("transcript") or "").strip()
                    if not transcript:
                        continue
                    topic = ex.get("topic", "unknown topic")
                    score = ex.get("trend_score", "unknown")
                    text += f"EXAMPLE {i} | topic={topic} | trend_score={score}:\n{transcript}\n\n"
                if text:
                    return text
        except Exception as exc:
            print(f"⚠️ Could not load {STYLE_EXAMPLES_FILE}, using defaults: {exc}")
    return EXAMPLES


def load_style_notes():
    if os.path.exists(STYLE_NOTES_FILE):
        try:
            with open(STYLE_NOTES_FILE, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            pass
    return ""


def build_prompt(niche, word_target):
    examples_text = load_examples_text()
    style_notes = load_style_notes()
    notes_block = f"\nCurrent trend analysis notes:\n{style_notes}\n" if style_notes else ""
    return (
        f"Write a dramatic, first-person Reddit-style story for a TikTok narration about {niche}. "
        f"Target approximately {word_target} words and stay close to that target. "
        "Start immediately with a strong curiosity hook. Use natural conversational language that "
        "sounds good when spoken aloud. Keep the story moving, with clear conflict and escalation, "
        "but do not force a twist if the story works better with a reveal, resolution, or cliffhanger. "
        "Vary sentence length so the narration does not sound robotic. Do not copy wording, people, "
        "events, or distinctive details from the examples. Learn only from their pacing and structure.\n\n"
        "High-performing reference examples:\n\n"
        f"{examples_text}"
        f"{notes_block}\n"
        f"Now write a completely original story of about {word_target} words about {niche}. "
        "Do not include a title, markdown, hashtags, stage directions, or commentary. "
        "Output only the raw story text."
    )


def generate_with_gemini(api_key, prompt):
    print(f"🟦 Generating story with Gemini ({GEMINI_MODEL})...")
    url = "https://generativelanguage.googleapis.com/v1beta/models/" f"{GEMINI_MODEL}:generateContent"
    response = requests.post(
        url,
        params={"key": api_key},
        headers={"Content-Type": "application/json"},
        json={
            "system_instruction": {"parts": [{"text": "You write original, high-retention short-form spoken stories."}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.9, "topP": 0.95, "maxOutputTokens": 1200},
        },
        timeout=90,
    )
    if response.status_code != 200:
        raise RuntimeError(f"Gemini API error {response.status_code}: {response.text[:500]}")
    data = response.json()
    candidates = data.get("candidates") or []
    if not candidates:
        raise RuntimeError(f"Gemini returned no candidates: {data}")
    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(part.get("text", "") for part in parts).strip()
    if not text:
        raise RuntimeError("Gemini returned an empty story.")
    return text


def generate_with_groq(api_key, prompt):
    print(f"🟧 Gemini unavailable; using Groq ({GROQ_MODEL})...")
    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": GROQ_MODEL,
            "messages": [
                {"role": "system", "content": "You write original, high-retention short-form spoken stories."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.9,
            "max_tokens": 1200,
        },
        timeout=90,
    )
    if response.status_code != 200:
        raise RuntimeError(f"Groq API error {response.status_code}: {response.text[:500]}")
    text = response.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()
    if not text:
        raise RuntimeError("Groq returned an empty story.")
    return text


def generate_story(word_target=240, niche=None):
    gemini_key = os.environ.get("GEMINI_API_KEY")
    groq_key = os.environ.get("GROQ_API_KEY")
    if niche is None:
        niche = select_story_niche()
    prompt = build_prompt(niche, word_target)
    print(f"🎯 Niche: {niche} | Target words: {word_target}")
    failures = []
    if gemini_key:
        try:
            story = generate_with_gemini(gemini_key, prompt)
            print(f"✅ Story generated with Gemini ({GEMINI_MODEL}).")
            return story
        except Exception as exc:
            failures.append(f"Gemini: {exc}")
            print(f"⚠️ Gemini generation failed: {exc}")
    else:
        failures.append("Gemini: GEMINI_API_KEY missing")
    if groq_key:
        try:
            story = generate_with_groq(groq_key, prompt)
            print(f"✅ Story generated with Groq ({GROQ_MODEL}).")
            return story
        except Exception as exc:
            failures.append(f"Groq: {exc}")
            print(f"⚠️ Groq generation failed: {exc}")
    else:
        failures.append("Groq: GROQ_API_KEY missing")
    details = "\n".join(f"  - {failure}" for failure in failures)
    raise RuntimeError("❌ All configured story-generation providers failed.\n" f"{details}")


def main():
    story_text = generate_story()
    with open(STORY_OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(story_text)
    print(f"\n✅ Story saved to '{STORY_OUTPUT_FILE}' ({len(story_text.split())} words)\n")
    print("=" * 60)
    print(story_text)
    print("=" * 60)


if __name__ == "__main__":
    main()
