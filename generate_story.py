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
PUBLIC_DOMAIN_PATTERNS_FILE = "public_domain_story_patterns.json"
RECENT_TOPICS_FILE = "recent_story_topics.json"

GEMINI_MODEL = os.environ.get("GEMINI_STORY_MODEL", "gemini-3.7-flash")
GROQ_MODEL = os.environ.get("GROQ_STORY_MODEL", "openai/gpt-oss-120b")
GROQ_FALLBACK_MODEL = os.environ.get("GROQ_STORY_FALLBACK_MODEL", "openai/gpt-oss-20b")

REQUEST_TIMEOUT = 90
GEMINI_RETRIES = 3
GROQ_RETRIES = 2
RETRYABLE_STATUS = {429, 500, 502, 503, 504}

STORY_NICHES = [
    "a shocking family secret discovered at a gathering",
    "a roommate who crossed a serious boundary",
    "catching a partner in a lie that changes everything",
    "a wedding or engagement that falls apart unexpectedly",
    "a neighbor feud that escalates too far",
    "a workplace betrayal by someone trusted",
    "a landlord or housing dispute with a hidden motive",
    "a friend group falling apart over one secret",
    "an inheritance or money dispute that exposes a family secret",
    "a stranger's small action that turns out to mean something much bigger",
]


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
        f"a completely different situation involving {base_topic}, with new people, motives and consequences",
        f"an unexpected personal conflict connected to {base_topic}, told from a different point of view",
        f"a relatable everyday situation that begins around {base_topic} but escalates in a new direction",
        f"a high-stakes misunderstanding involving {base_topic}, using entirely new story details",
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


def load_style_notes():
    try:
        if os.path.exists(STYLE_NOTES_FILE):
            with open(STYLE_NOTES_FILE, "r", encoding="utf-8") as f:
                return f.read().strip()
    except Exception:
        pass
    return ""


def load_tiktok_structure_signals(limit=6):
    """Return only abstract TikTok analysis. Never send transcripts to the writer."""
    data = load_json(STYLE_EXAMPLES_FILE, [])
    if not isinstance(data, list):
        return []
    ranked = sorted(
        [x for x in data if isinstance(x, dict)],
        key=lambda ex: ex.get("trend_score", ex.get("views", 0)) or 0,
        reverse=True,
    )
    signals = []
    for example in ranked[:limit]:
        beats = []
        for beat in example.get("beats", []) if isinstance(example.get("beats"), list) else []:
            if isinstance(beat, dict):
                beats.append({
                    "type": beat.get("type"),
                    "start": beat.get("start_position"),
                    "end": beat.get("end_position"),
                })
        signals.append({
            "topic": example.get("topic"),
            "hook_type": example.get("hook_type"),
            "summary": example.get("summary"),
            "beat_sequence": beats[:12],
            "trend_score": example.get("trend_score"),
        })
    return signals


def choose_public_domain_pattern():
    data = load_json(PUBLIC_DOMAIN_PATTERNS_FILE, [])
    if not isinstance(data, list) or not data:
        return None
    usable = [item for item in data if isinstance(item, dict) and isinstance(item.get("pattern"), dict)]
    if not usable:
        return None
    item = random.choice(usable)
    pattern = item["pattern"]
    # Deliberately return no title/author/source text. The writer sees only abstract mechanics.
    return {
        "premise_pattern": pattern.get("premise_pattern"),
        "hook_pattern": pattern.get("hook_pattern"),
        "conflict_pattern": pattern.get("conflict_pattern"),
        "escalation_pattern": pattern.get("escalation_pattern"),
        "misdirection": pattern.get("misdirection"),
        "twist_type": pattern.get("twist_type"),
        "twist_setup": pattern.get("twist_setup"),
        "reveal_mechanism": pattern.get("reveal_mechanism"),
        "payoff_pattern": pattern.get("payoff_pattern"),
        "emotional_arc": pattern.get("emotional_arc"),
        "beat_sequence": pattern.get("beat_sequence"),
        "adaptable_theme": pattern.get("adaptable_theme"),
        "retention_lessons": pattern.get("retention_lessons"),
    }


def build_prompt(niche, word_target):
    style_notes = load_style_notes()
    pattern = choose_public_domain_pattern()
    trend_signals = load_tiktok_structure_signals()
    min_words = max(120, int(word_target * 0.88))
    max_words = max(min_words + 20, int(word_target * 1.12))

    pattern_block = json.dumps(pattern, ensure_ascii=False, indent=2) if pattern else "No stored pattern available."
    trend_block = json.dumps(trend_signals, ensure_ascii=False, indent=2) if trend_signals else "No current TikTok structural signals available."

    return f"""
Write ONE completely original first-person spoken story for a TikTok/Reddit-style narration.

CURRENT AUDIENCE TOPIC:
{niche}

LENGTH:
- Aim for {word_target} words.
- Stay between about {min_words} and {max_words} words unless the story genuinely needs a little more room.
- Do not pad the ending just to hit the word count.

PUBLIC-DOMAIN NARRATIVE MECHANIC:
{pattern_block}

CURRENT TIKTOK STRUCTURAL SIGNALS:
{trend_block}

STYLE NOTES:
{style_notes[:5000]}

WRITING RULES:
- Use the public-domain information ONLY as abstract narrative architecture. Do not reproduce or modernise its original plot, characters, setting, objects, sequence of distinctive events, or wording.
- TikTok references are trend/structure signals only. Do not reconstruct any source transcript or identifiable creator story.
- Create brand-new characters, relationships, setting, motives, clues, conflict and outcome.
- Start with a specific curiosity hook in the first 1-2 sentences. Do not waste time introducing names or background first.
- Give the protagonist a clear goal or fear, then add concrete complications that make the situation progressively harder.
- Plant 2-4 subtle details before the reveal. They should seem ordinary at first but make sense differently after the reveal.
- If the chosen pattern contains a twist/reversal/recontextualisation, make the late reveal meaningful: it must change how the audience understands at least one earlier event. Do not use a random shock with no setup.
- Do not announce the twist with phrases like 'here is the twist' or 'you won't believe what happened next'. Let the event reveal it.
- The ending must resolve the main question or deliberately end on a strong natural cliffhanger; do not stop mid-thought.
- Keep the voice conversational and believable, as if a real person is telling something that happened to them.
- Use punctuation that helps natural TTS: commas for short pauses, full stops for clear beats, and occasional em dashes only when useful.
- Avoid excessive quotation dialogue, repeated filler, generic moral lessons, fake engagement bait, hashtags and calls to follow/like.
- No title, markdown, labels, commentary or source references.

Before writing, silently plan: hook -> context -> conflict -> escalation -> planted clues -> reveal/payoff -> resolution.
Output ONLY the finished story.
""".strip()


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
                    "system_instruction": {"parts": [{"text": "You are an original short-form storyteller. Build deep causal plots, plant fair clues, and deliver earned reveals without copying reference stories."}]},
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.95, "topP": 0.95, "maxOutputTokens": 2200},
                },
                timeout=REQUEST_TIMEOUT,
            )
        except requests.RequestException as exc:
            last_error = f"network error: {exc}"
            if attempt < GEMINI_RETRIES:
                time.sleep(retry_delay(attempt))
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
                last_error = "empty response"
        else:
            last_error = f"HTTP {response.status_code}: {response.text[:500]}"
        if response.status_code in RETRYABLE_STATUS and attempt < GEMINI_RETRIES:
            time.sleep(retry_delay(attempt))
            continue
        break
    raise RuntimeError(f"Gemini failed after retries: {last_error}")


def extract_groq_text(data):
    choices = data.get("choices") or []
    if not choices:
        return ""
    content = (choices[0].get("message") or {}).get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return "".join(str(p.get("text") or p.get("content") or "") if isinstance(p, dict) else str(p) for p in content).strip()
    return ""


def generate_with_groq_model(api_key, prompt, model):
    last_error = None
    for attempt in range(1, GROQ_RETRIES + 1):
        print(f"🟧 Groq ({model}) attempt {attempt}/{GROQ_RETRIES}...")
        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "Write original spoken stories with strong causality, fair clue planting and earned reveals. Return only the story."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.95,
                    "max_tokens": 3000,
                    "reasoning_effort": "low",
                    "include_reasoning": False,
                    "stream": False,
                },
                timeout=REQUEST_TIMEOUT,
            )
        except requests.RequestException as exc:
            last_error = f"network error: {exc}"
            if attempt < GROQ_RETRIES:
                time.sleep(retry_delay(attempt))
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
                last_error = "empty final content"
        else:
            last_error = f"HTTP {response.status_code}: {response.text[:500]}"
        if response.status_code in RETRYABLE_STATUS and attempt < GROQ_RETRIES:
            time.sleep(retry_delay(attempt))
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
            return story.strip()
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
                return story.strip()
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


if __name__ == "__main__":
    main()
