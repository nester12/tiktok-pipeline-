import json
import os
import random
import time

import requests

STORY_OUTPUT_FILE = "story.txt"
TREND_SUMMARY_FILE = "trend_summary.json"
RECENT_TOPICS_FILE = "recent_story_topics.json"
STYLE_NOTES_FILE = "style_notes.txt"

GEMINI_MODEL = os.environ.get("GEMINI_STORY_MODEL", "gemini-3.7-flash")
GROQ_MODEL = os.environ.get("GROQ_STORY_MODEL", "openai/gpt-oss-120b")
GROQ_FALLBACK_MODEL = os.environ.get("GROQ_STORY_FALLBACK_MODEL", "openai/gpt-oss-20b")
REQUEST_TIMEOUT = 90
GEMINI_RETRIES = 3
GROQ_RETRIES = 2
RETRYABLE_STATUS = {429, 500, 502, 503, 504}

STORY_NICHES = [
    "a family secret discovered at a gathering",
    "a roommate who crossed an important boundary",
    "discovering that someone close has been dishonest",
    "an event or celebration that changes unexpectedly",
    "a neighbor disagreement that keeps escalating",
    "a workplace betrayal by someone trusted",
    "a housing dispute with a hidden motive",
    "a friend group falling apart over one secret",
    "a money dispute that exposes a family secret",
    "a stranger's small action that turns out to matter much more",
]


def load_json(path, default):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as exc:
        print(f"Could not read {path}: {exc}")
    return default


def load_style_notes():
    try:
        if os.path.exists(STYLE_NOTES_FILE):
            with open(STYLE_NOTES_FILE, "r", encoding="utf-8") as f:
                return f.read().strip()
    except Exception:
        pass
    return ""


def load_recent_topics():
    data = load_json(RECENT_TOPICS_FILE, [])
    return [str(x).strip() for x in data if str(x).strip()][-12:] if isinstance(data, list) else []


def remember_topic(topic):
    recent = load_recent_topics()
    recent.append(topic)
    try:
        with open(RECENT_TOPICS_FILE, "w", encoding="utf-8") as f:
            json.dump(recent[-12:], f, indent=2, ensure_ascii=False)
    except Exception as exc:
        print(f"Could not save recent topic history: {exc}")


def topic_is_recent(topic, recent):
    words = set(topic.lower().split())
    for old in recent:
        old_words = set(old.lower().split())
        if topic.lower() == old.lower():
            return True
        if words and old_words:
            overlap = len(words & old_words) / max(len(words | old_words), 1)
            if overlap >= 0.65:
                return True
    return False


def load_trending_topics():
    data = load_json(TREND_SUMMARY_FILE, {})
    raw = data.get("top_topics", []) if isinstance(data, dict) else []
    topics = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            topics.append(item.strip())
        elif isinstance(item, dict):
            value = str(item.get("topic") or item.get("name") or "").strip()
            if value:
                topics.append(value)
        elif isinstance(item, (list, tuple)) and item:
            value = str(item[0]).strip()
            if value:
                topics.append(value)
    return topics


def select_story_niche():
    recent = load_recent_topics()
    trending = [x for x in load_trending_topics() if not topic_is_recent(x, recent)]
    regular = [x for x in STORY_NICHES if not topic_is_recent(x, recent)]

    if trending and random.random() < 0.75:
        niche = random.choice(trending)
        mode = "trend"
    else:
        niche = random.choice(regular or STORY_NICHES)
        mode = "original"

    print(f"Topic selection: {mode}")
    remember_topic(niche)
    return niche


def build_prompt(niche, word_target):
    min_words = max(45, int(word_target * 0.90))
    max_words = max(min_words + 12, int(word_target * 1.10))
    notes = load_style_notes()

    return f"""
Write ONE completely original first-person story for short-form text-to-speech narration.

TOPIC:
{niche}

LENGTH:
- Aim for about {word_target} words.
- Stay between about {min_words} and {max_words} words.
- Do not pad the ending just to reach the word count.

NARRATION FORMAT:
- Output the entire finished story as ONE continuous paragraph.
- Write for speech, not like an essay or formal prose.
- It should sound like a real person naturally telling a friend what happened from memory.
- Use commas often so connected thoughts flow naturally.
- Use ... only for genuine hesitation, suspense, remembering something, or a pause before important information.
- Use an em dash — for an interruption, sudden change of thought, or sharp reveal.
- Use full stops sparingly; prefer connected spoken rhythm when it sounds natural.
- Keep dialogue inside the same paragraph.
- Natural spoken connectors are encouraged where they fit, including phrases such as "and then", "so I'm like", "but here's the thing", "that's when", "he goes", "and at this point", and "which obviously".
- Do not mechanically add ... or — everywhere. Punctuation must follow the emotion and meaning.
- Occasional CAPITAL words are allowed for strong emphasis, but use them rarely.
- Avoid audiobook language, essay transitions, formal narration, and overly polished written sentences.

STORY QUALITY:
- Open immediately with a specific curiosity hook.
- Establish the central problem quickly.
- Escalate through concrete actions and consequences.
- Plant 2-4 ordinary-looking details that matter later.
- Major reveals must connect to something established earlier.
- A twist should reframe an earlier detail instead of appearing randomly.
- Keep the narrator believable, casual and immediate.
- Avoid repeated information, generic moral lessons, hashtags, calls to follow, and fake engagement bait.
- End with either a satisfying payoff or a deliberate natural cliffhanger.

ORIGINALITY:
- Create new characters, setting, motives, clues, conflict, dialogue and outcome.
- Do not copy, paraphrase, modernise, or reconstruct any reference story or creator wording.

OPTIONAL STYLE NOTES:
{notes[:3000]}

Return ONLY the finished one-paragraph narration. No title, labels, markdown, notes or explanation.
""".strip()


def retry_delay(attempt):
    return min(3 * (2 ** (attempt - 1)) + random.uniform(0.2, 1.0), 15)


def extract_gemini_text(data):
    candidates = data.get("candidates") or []
    if not candidates:
        return ""
    parts = candidates[0].get("content", {}).get("parts", [])
    return "".join(str(part.get("text", "")) for part in parts).strip()


def generate_with_gemini(api_key, prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    last_error = "unknown error"
    for attempt in range(1, GEMINI_RETRIES + 1):
        try:
            response = requests.post(
                url,
                params={"key": api_key},
                headers={"Content-Type": "application/json"},
                json={
                    "system_instruction": {"parts": [{"text": "Write original, conversational short-form stories with clear causality and earned reveals. Return only the story."}]},
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.95, "topP": 0.95, "maxOutputTokens": 2200},
                },
                timeout=REQUEST_TIMEOUT,
            )
        except requests.RequestException as exc:
            last_error = str(exc)
            if attempt < GEMINI_RETRIES:
                time.sleep(retry_delay(attempt))
                continue
            break

        if response.status_code == 200:
            text = extract_gemini_text(response.json())
            if text:
                return text
            last_error = "empty response"
        else:
            last_error = f"HTTP {response.status_code}: {response.text[:400]}"

        if response.status_code in RETRYABLE_STATUS and attempt < GEMINI_RETRIES:
            time.sleep(retry_delay(attempt))
            continue
        break

    raise RuntimeError(f"Gemini failed: {last_error}")


def extract_groq_text(data):
    choices = data.get("choices") or []
    if not choices:
        return ""
    content = (choices[0].get("message") or {}).get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return "".join(str(x.get("text") or x.get("content") or "") if isinstance(x, dict) else str(x) for x in content).strip()
    return ""


def generate_with_groq_model(api_key, prompt, model):
    last_error = "unknown error"
    for attempt in range(1, GROQ_RETRIES + 1):
        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "Write original, conversational short-form stories. Return only the story."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.95,
                    "max_tokens": 3000,
                    "reasoning_effort": "medium",
                    "include_reasoning": False,
                    "stream": False,
                },
                timeout=REQUEST_TIMEOUT,
            )
        except requests.RequestException as exc:
            last_error = str(exc)
            if attempt < GROQ_RETRIES:
                time.sleep(retry_delay(attempt))
                continue
            break

        if response.status_code == 200:
            text = extract_groq_text(response.json())
            if text:
                return text
            last_error = "empty response"
        else:
            last_error = f"HTTP {response.status_code}: {response.text[:400]}"

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
    print(f"Niche: {niche} | target words: {word_target}")
    failures = []

    if gemini_key:
        try:
            story = generate_with_gemini(gemini_key, prompt)
            print(f"Story generated with Gemini ({GEMINI_MODEL}).")
            return " ".join(story.strip().splitlines())
        except Exception as exc:
            failures.append(f"Gemini: {exc}")
            print(f"Gemini generation failed: {exc}")
    else:
        failures.append("Gemini: GEMINI_API_KEY missing")

    if groq_key:
        for model in dict.fromkeys([GROQ_MODEL, GROQ_FALLBACK_MODEL]):
            if not model:
                continue
            try:
                story = generate_with_groq_model(groq_key, prompt, model)
                print(f"Story generated with Groq ({model}).")
                return " ".join(story.strip().splitlines())
            except Exception as exc:
                failures.append(f"Groq {model}: {exc}")
                print(f"Groq {model} failed: {exc}")
    else:
        failures.append("Groq: GROQ_API_KEY missing")

    details = "\n".join(f"- {x}" for x in failures)
    raise RuntimeError(f"All configured story-generation providers failed.\n{details}")


def main():
    story_text = generate_story()
    with open(STORY_OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(story_text)
    print(f"Story saved to {STORY_OUTPUT_FILE} ({len(story_text.split())} words)")


if __name__ == "__main__":
    main()
