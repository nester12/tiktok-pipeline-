# -------------------------------------------------------------------
# Story Generator (Groq & Gemini support)
# -------------------------------------------------------------------
import os
import random
import requests

STORY_OUTPUT_FILE = "story.txt"

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
    "My sister asked me to babysit for 'an hour.' That was six hours ago. "
    "I called her twenty times. Nothing. Then I checked her location. "
    "She was at a hotel two towns over. Not working. Not stuck in traffic. "
    "A hotel. I packed the kids' bags right there. When she finally walked in laughing, "
    "I was already at the door. I didn't yell. I just said, 'Never again,' and left. "
    "She's called me eleven times since. I haven't answered once.\n\n"
    "EXAMPLE 2:\n"
    "My roommate ate my leftovers for the third time this week. So I stopped labeling them. "
    "Instead, I made a new dish. Looked identical to my usual dinner. Smelled amazing. "
    "She grabbed it the second I left for work. I got a text four hours later. "
    "All caps. 'WHAT DID YOU PUT IN THAT.' It was just extremely hot ghost pepper sauce. "
    "She moved out two weeks later. I still make that dish. Nobody touches my food anymore.\n\n"
    "EXAMPLE 3:\n"
    "My landlord raised my rent by four hundred dollars with zero notice. "
    "I asked why. He said 'market rates.' So I pulled up every violation in the building. "
    "Broken heater. Mold in the hallway. No fire extinguishers. I emailed the housing board "
    "that same night. Three weeks later, inspectors showed up unannounced. "
    "My rent increase mysteriously disappeared. Funny how that works.\n\n"
)


def build_prompt(niche, word_target):
    return (
        f"Write a viral, dramatic, first-person Reddit-style story for a TikTok video, "
        f"about {niche}. "
        f"The story MUST be approximately {word_target} words long — this is important, "
        f"do not go far under or over that word count. "
        "Start immediately with a shocking hook in the first sentence. "
        "Make it deeply relatable and emotional — the kind of story someone would send to a friend "
        "saying 'you won't believe this happened to me.' Use everyday, conversational language, "
        "short punchy sentences, and a clear emotional arc (setup, escalation, twist or resolution). "
        "Keep sentences short and fast-paced for text-to-speech narration.\n\n"
        "Here are three examples of the exact rhythm, pacing, and sentence length to match "
        "(do not reuse their topics or details, only match the style and length proportionally):\n\n"
        f"{EXAMPLES}"
        f"Now write a brand new story of about {word_target} words in that same style, about {niche}. "
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


def generate_with_nvidia(nvidia_key, prompt):
    print("🟩 Generating story using NVIDIA NIM (DeepSeek V4)...")
    url = "https://integrate.api.nvidia.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {nvidia_key}", "Content-Type": "application/json"}
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
            story_text = generate_with_nvidia(nvidia_key, prompt)
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
