# -------------------------------------------------------------------
# Story Generator (Gemini primary, Groq fallback)
# -------------------------------------------------------------------
import json
import os
import random
import time

import requests

STORY_OUTPUT_FILE = "story.txt"
STYLE_EXAMPLES_FILE = "style_examples.json"
STYLE_NOTES_FILE = "style_notes.txt"
TREND_SUMMARY_FILE = "trend_summary.json"
RECENT_TOPICS_FILE = "recent_story_topics.json"

GEMINI_MODEL = os.environ.get("GEMINI_STORY_MODEL", "gemini-3.7-flash")
GROQ_MODEL = os.environ.get("GROQ_STORY_MODEL", "openai/gpt-oss-120b")
GROQ_FALLBACK_MODEL = os.environ.get("GROQ_STORY_FALLBACK_MODEL", "openai/gpt-oss-20b")

REQUEST_TIMEOUT = 90
GEMINI_RETRIES = 3
GROQ_RETRIES = 2
RETRYABLE_STATUS = {429, 500, 502, 503, 504}

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
    try:
        with open(RECENT_TOPICS_FILE, "w", encoding="utf-8") as f:
            json.dump(recent[-12:], f, indent=2, ensure_ascii=False)
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
        if topic.lower() == old.lower():
            return True
        old_words = set(old.lower().split())
        if topic_words and old_words:
            overlap = len(topic_words & old_words) / max(len(topic_words | old_words), 1)
            if overlap >= 0.65:
                return True
    return False


def weighted_trend_choice(trending, recent):
    available = [item for item in trending if not is_recently_used(item[0], recent)] or trending
    if not available:
        return None
    return random.choices(
        [item[0] for item in available],
        weights=[item[1] for item in available],
        k=1,
    )[0]


def create_topic_variation(base_topic):
    return random.choice([
        f"a completely different situation involving {base_topic}, with new people, motives, and consequences",
        f"an unexpected personal conflict connected to {base_topic}, told from a different point of view",
        f"a relatable everyday situation that starts around {base_topic} but escalates in an original direction",
        f"a new high-stakes misunderstanding involving {base_topic}, without copying any existing story details",
    ])


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
    data = load_json(STYLE_EXAMPLES_FILE, [])
    if isinstance(data, list) and data:
        ranked = sorted(
            data,
            key=lambda ex: ex.get("trend_score", ex.get("video_score", ex.get("views", 0))) or 0,
            reverse=True,
        )
        text = ""
        for index, example in enumerate(ranked[:5], start=1):
            transcript = (example.get("full_transcript") or example.get("transcript") or "").strip()
            if not transcript:
                continue
            topic = example.get("topic", "unknown topic")
            score = example.get("trend_score", "unknown")
            text += f"EXAMPLE {index} | topic={topic} | trend_score={score}:\n{transcript}\n\n"
        if text:
            return text
    return EXAMPLES


def load_style_notes():
    try:
        if os.path.exists(STYLE_NOTES_FILE):
            with open(STYLE_NOTES_FILE, "r", encoding="utf-8") as f:
                return f.read().strip()
    except Exception:
        pass
    return ""


def build_prompt(niche, word_target):
    style_notes = load_style_notes()
    notes_block = f"\nCurrent trend analysis notes:\n{style_notes}\n" if style_notes else ""
    return (
        f"Write a dramatic, first-person Reddit-style story for a TikTok narration about {niche}. "
        f"Target approximately {word_target} words and stay close to that target. "
        "Start immediately with a strong curiosity hook. Use natural conversational language that "
        "sounds good when spoken aloud. Keep clear conflict and escalation, but do not force a twist. "
        "Vary sentence length so narration sounds natural. Do not copy wording, people, events, or "
        "distinctive details from the references; learn only pacing and structure.\n\n"
        "High-performing reference examples:\n\n"
        f"{load_examples_text()}"
        f"{notes_block}\n"
        f"Write a completely original story of about {word_target} words about {niche}. "
        "No title, markdown, hashtags, stage directions, or commentary. Output only raw story text."
    )


def retry_delay(attempt):
    return min(3 * (2 ** (attempt - 1)) + random.uniform(0.2, 1.2), 15)


def extract_gemini_text(data):
    candidates = data.get("candidates") or []
    if not candidates:
        return ""
    parts = candidates[0].get("content", {}).get("parts", [])
    return "".join(str(part.get("text", "")) for part in parts).strip()


def generate_with_gemini(api_key, prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    last_error = None

    for attempt in range(1, GEMINI_RETRIES + 1):
        print(f"🟦 Gemini ({GEMINI_MODEL}) attempt {attempt}/{GEMINI_RETRIES}...")
        try:
            response = requests.post(
                url,
                params={"key": api_key},
                headers={"Content-Type": "application/json"},
                json={
                    "system_instruction": {
                        "parts": [{"text": "You write original, high-retention short-form spoken stories."}]
                    },
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": 0.9,
                        "topP": 0.95,
                        "maxOutputTokens": 1400,
                    },
                },
                timeout=REQUEST_TIMEOUT,
            )
        except requests.RequestException as exc:
            last_error = f"network error: {exc}"
            if attempt < GEMINI_RETRIES:
                delay = retry_delay(attempt)
                print(f"⚠️ Gemini network error; retrying in {delay:.1f}s.")
                time.sleep(delay)
                continue
            break

        if response.status_code == 200:
            try:
                text = extract_gemini_text(response.json())
            except ValueError as exc:
                last_error = f"invalid JSON: {exc}"
            else:
                if text:
                    return text
                last_error = f"empty response: {response.text[:400]}"
        else:
            last_error = f"HTTP {response.status_code}: {response.text[:500]}"

        if response.status_code in RETRYABLE_STATUS and attempt < GEMINI_RETRIES:
            delay = retry_delay(attempt)
            print(f"⚠️ Gemini temporary failure ({response.status_code}); retrying in {delay:.1f}s.")
            time.sleep(delay)
            continue
        break

    raise RuntimeError(f"Gemini failed after retries: {last_error}")


def extract_groq_text(data):
    choices = data.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        pieces = []
        for part in content:
            if isinstance(part, str):
                pieces.append(part)
            elif isinstance(part, dict):
                pieces.append(str(part.get("text") or part.get("content") or ""))
        return "".join(pieces).strip()
    return ""


def generate_with_groq_model(api_key, prompt, model):
    last_error = None
    for attempt in range(1, GROQ_RETRIES + 1):
        print(f"🟧 Groq ({model}) attempt {attempt}/{GROQ_RETRIES}...")
        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {
                            "role": "system",
                            "content": "You write original, high-retention short-form spoken stories. Return only the finished story.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.9,
                    "max_tokens": 2400,
                    "reasoning_effort": "low",
                    "include_reasoning": False,
                    "stream": False,
                },
                timeout=REQUEST_TIMEOUT,
            )
        except requests.RequestException as exc:
            last_error = f"network error: {exc}"
            if attempt < GROQ_RETRIES:
                delay = retry_delay(attempt)
                print(f"⚠️ Groq network error; retrying in {delay:.1f}s.")
                time.sleep(delay)
                continue
            break

        if response.status_code == 200:
            try:
                data = response.json()
            except ValueError as exc:
                last_error = f"invalid JSON: {exc}"
            else:
                text = extract_groq_text(data)
                if text:
                    return text
                finish_reason = (data.get("choices") or [{}])[0].get("finish_reason")
                last_error = f"empty final content (finish_reason={finish_reason}); response={str(data)[:600]}"
        else:
            last_error = f"HTTP {response.status_code}: {response.text[:500]}"

        if response.status_code in RETRYABLE_STATUS and attempt < GROQ_RETRIES:
            delay = retry_delay(attempt)
            print(f"⚠️ Groq temporary failure ({response.status_code}); retrying in {delay:.1f}s.")
            time.sleep(delay)
            continue

        if response.status_code == 200 and attempt < GROQ_RETRIES:
            delay = retry_delay(attempt)
            print(f"⚠️ Groq returned no final text; retrying in {delay:.1f}s.")
            time.sleep(delay)
            continue
        break

    raise RuntimeError(f"{model} failed: {last_error}")


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
        models = []
        for model in (GROQ_MODEL, GROQ_FALLBACK_MODEL):
            if model and model not in models:
                models.append(model)
        for model in models:
            try:
                story = generate_with_groq_model(groq_key, prompt, model)
                print(f"✅ Story generated with Groq ({model}).")
                return story
            except Exception as exc:
                failures.append(f"Groq {model}: {exc}")
                print(f"⚠️ Groq {model} failed: {exc}")
    else:
        failures.append("Groq: GROQ_API_KEY missing")

    details = "\n".join(f"  - {failure}" for failure in failures)
    raise RuntimeError(f"❌ All configured story-generation providers failed.\n{details}")


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
