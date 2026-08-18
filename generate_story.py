# -------------------------------------------------------------------
# Story Generator (Groq & Gemini support)
# -------------------------------------------------------------------
import os
import json
import random
import requests

STORY_OUTPUT_FILE = "story.txt"
STYLE_EXAMPLES_FILE = "style_examples.json"
STYLE_NOTES_FILE = "style_notes.txt"

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


def load_examples_text():
    """
    Uses real transcripts pulled from trending videos + reference accounts
    (via fetch_style_examples.py) if available, falling back to the
    hand-written examples otherwise.
    """
    if os.path.exists(STYLE_EXAMPLES_FILE):
        try:
            with open(STYLE_EXAMPLES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data:
                sample = random.sample(data, min(3, len(data)))
                text = ""
                for i, ex in enumerate(sample, 1):
                    text += f"EXAMPLE {i} (from {ex['source']}):\n{ex['transcript']}\n\n"
                return text
        except Exception as e:
            print(f"⚠️ Could not load {STYLE_EXAMPLES_FILE}, using default examples: {e}")

    return EXAMPLES


def load_style_notes():
    """AI-derived pattern notes from fetch_style_examples.py's analysis pass, if available."""
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
    notes_block = (
        f"\nCurrent trend analysis notes (patterns seen in recently trending similar videos):\n{style_notes}\n"
        if style_notes else ""
    )
    return (
        f"Write a viral, dramatic, first-person Reddit-style story for a TikTok video, "
        f"about {niche}. "
        f"The story MUST be approximately {word_target} words long — this is important, "
        f"do not go far under or over that word count. "
        "Start immediately with a shocking hook in the first sentence. "
        "Make it deeply relatable and emotional — the kind of story someone would send to a friend "
        "saying 'you won't believe this happened to me.' Use everyday, conversational language. "
        "Write it the way someone would actually SPEAK it out loud when telling a friend a story — "
        "flowing sentences connected with 'and,' 'but,' 'so,' and commas, not a rapid string of "
        "short blunt statements each ending in a period. Vary your rhythm: mix a few longer, "
        "flowing sentences with the occasional short one for punch at key emotional beats. "
        "Avoid excessive full stops — a story that's just one short clipped sentence after another "
        "sounds robotic when read aloud, not like natural narration. "
        "Keep a clear emotional arc (setup, escalation, twist or resolution) and fast pacing overall, "
        "but let it breathe like real spoken storytelling.\n\n"
        "Here are three examples of the exact rhythm, flow, and natural spoken pacing to match "
        "(do not reuse their topics or details, only match the style and length proportionally):\n\n"
        f"{examples_text}"
        f"{notes_block}"
        f"Now write a brand new story of about {word_target} words in that same flowing, "
        f"narrated-aloud style, about {niche}. "
        "Do NOT include titles, markdown headers (* or #), hashtags, stage directions, or quotes. "
        "Output ONLY the raw story text."
    )


def generate_with_groq(groq_key, prompt):
    print("⚡ Generating story using Groq API (Llama 3.3)...")
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"}
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": "You are a master storyteller writing viral, relatable TikTok Reddit scripts."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.9,
        "max_tokens": 700
    }
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code == 200:
        return response.json()["choices"][0]["message"]["content"].strip()
    raise Exception(f"Groq API Error ({response.status_code}): {response.text}")


def generate_with_gemini(gemini_key, prompt):
    print("🤖 Generating story using Gemini API...")
    import google.generativeai as genai
    genai.configure(api_key=gemini_key)
    model = genai.GenerativeModel('gemini-1.5-flash')
    return model.generate_content(prompt).text.strip()


def generate_with_nvidia(META1_API_KEY, prompt):
    print("🟩 Generating story using NVIDIA NIM (DeepSeek V4)...")
    url = "https://integrate.api.nvidia.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {META1_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "deepseek-ai/deepseek-v4",
        "messages": [
            {"role": "system", "content": "You are a master storyteller writing viral, relatable TikTok Reddit scripts."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.9,
        "max_tokens": 700
    }
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code == 200:
        return response.json()["choices"][0]["message"]["content"].strip()
    raise Exception(f"NVIDIA NIM API Error ({response.status_code}): {response.text}")


def generate_story(word_target=240, niche=None):
    """Generates a story of roughly word_target words. Returns the story text.
    Tries Groq first, then Gemini, then NVIDIA NIM (DeepSeek V4) as a fallback."""
    groq_key = os.environ.get("GROQ_API_KEY")
    gemini_key = os.environ.get("GEMINI_API_KEY")
    nvidia_key = os.environ.get("NVIDIA_API_KEY")

    if niche is None:
        niche = random.choice(STORY_NICHES)
    prompt = build_prompt(niche, word_target)
    print(f"🎯 Niche: {niche} | Target words: {word_target}")

    story_text = ""
    if groq_key:
        try:
            story_text = generate_with_groq(groq_key, prompt)
        except Exception as e:
            print(f"⚠️ Groq generation failed: {e}")

    if not story_text and gemini_key:
        try:
            story_text = generate_with_gemini(gemini_key, prompt)
        except Exception as e:
            print(f"⚠️ Gemini generation failed: {e}")

    if not story_text and nvidia_key:
        try:
            story_text = generate_with_nvidia(META1_API_KEY, prompt)
        except Exception as e:
            print(f"⚠️ NVIDIA NIM generation failed: {e}")

    if not story_text:
        raise ValueError("❌ None of GROQ_API_KEY, GEMINI_API_KEY, or NVIDIA_API_KEY produced a story!")

    return story_text


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
