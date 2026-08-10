# -------------------------------------------------------------------
# Story Generator (Groq & Gemini support)
# -------------------------------------------------------------------
import os
import requests

STORY_OUTPUT_FILE = "story.txt"

STORY_PROMPT = (
    "Write a viral, dramatic, first-person Reddit-style story for a 60-second TikTok video. "
    "Start immediately with a shocking hook (e.g. workplace revenge, crazy landlord, family drama, or fraud). "
    "Keep sentences short, fast-paced, and natural for text-to-speech audio narration. "
    "Do NOT include titles, markdown headers (* or #), hashtags, stage directions, or quotes. "
    "Output ONLY the raw story text."
)


def generate_with_groq(groq_key):
    """Generates story via Groq API (Llama 3.3 70B)."""
    print("⚡ Generating story using Groq API (Llama 3.3)...")
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {groq_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": "You are a master storyteller writing viral TikTok Reddit scripts."},
            {"role": "user", "content": STORY_PROMPT}
        ],
        "temperature": 0.85,
        "max_tokens": 400
    }
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code == 200:
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()
    else:
        raise Exception(f"Groq API Error ({response.status_code}): {response.text}")


def generate_with_gemini(gemini_key):
    """Generates story via Gemini API."""
    print("🤖 Generating story using Gemini API...")
    import google.generativeai as genai
    genai.configure(api_key=gemini_key)
    model = genai.GenerativeModel('gemini-1.5-flash')
    response = model.generate_content(STORY_PROMPT)
    return response.text.strip()


def main():
    # Keys come from environment variables (set as GitHub Actions secrets)
    groq_key = os.environ.get("GROQ_API_KEY")
    gemini_key = os.environ.get("GEMINI_API_KEY")

    story_text = ""

    if groq_key:
        try:
            story_text = generate_with_groq(groq_key)
        except Exception as e:
            print(f"⚠️ Groq generation failed: {e}")

    if not story_text and gemini_key:
        try:
            story_text = generate_with_gemini(gemini_key)
        except Exception as e:
            print(f"⚠️ Gemini generation failed: {e}")

    if not story_text:
        raise ValueError(
            "❌ Neither GROQ_API_KEY nor GEMINI_API_KEY was found or valid in environment variables!\n"
            "Add at least one as a GitHub Actions repository secret."
        )

    with open(STORY_OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(story_text)

    print(f"\n✅ Story generated successfully and saved to '{STORY_OUTPUT_FILE}'!\n")
    print("=" * 60)
    print(story_text)
    print("=" * 60)


if __name__ == "__main__":
    main()
