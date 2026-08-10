# -------------------------------------------------------------------
# Fetch a background video from Pexels, with an AI review step
# (Gemini vision) that checks a sample frame and rejects clips that
# are static, low-motion, or not a good fit before accepting one.
# -------------------------------------------------------------------
import os
import random
import requests
import subprocess

OUTPUT_FILE = "background.mp4"
SAMPLE_FRAME = "sample_frame.jpg"

SEARCH_TERMS = [
    "minecraft parkour gameplay",
    "subway surfers gameplay",
    "satisfying slime asmr",
    "gta 5 driving gameplay",
    "extreme sports action",
    "obstacle course fail",
    "oddly satisfying cutting",
    "car drifting close up",
]

MAX_CANDIDATES = 4


def search_pexels(api_key, query):
    headers = {"Authorization": api_key}
    resp = requests.get(
        "https://api.pexels.com/videos/search",
        headers=headers,
        params={"query": query, "orientation": "portrait", "per_page": 15}
    )
    resp.raise_for_status()
    return resp.json().get("videos", [])


def download(url, path):
    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        with open(path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)


def extract_sample_frame(video_path, out_path, at_seconds=1.5):
    """Grabs a single frame from the video using ffmpeg for AI review."""
    subprocess.run(
        ["ffmpeg", "-y", "-ss", str(at_seconds), "-i", video_path,
         "-frames:v", "1", "-q:v", "2", out_path],
        check=True, capture_output=True
    )


def ai_review_frame(gemini_key, frame_path):
    """
    Asks Gemini to review the sample frame for suitability as fast-moving,
    attention-grabbing TikTok background footage. Returns True/False.
    Fails open (returns True) if the API call errors, so a bad key never
    blocks the whole pipeline.
    """
    try:
        import google.generativeai as genai
        from PIL import Image

        genai.configure(api_key=gemini_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        img = Image.open(frame_path)

        prompt = (
            "You are reviewing a single frame from a video that will be used as "
            "high-energy TikTok background footage, played under text captions. "
            "Approve it only if it looks dynamic, visually interesting, and safe/appropriate "
            "for a general audience. Reject if it looks static, blank, low-quality, dark, "
            "or contains anything inappropriate or NSFW. "
            "Reply with exactly one word: APPROVE or REJECT."
        )
        response = model.generate_content([prompt, img])
        verdict = response.text.strip().upper()
        print(f"🤖 AI review verdict: {verdict}")
        return "APPROVE" in verdict
    except Exception as e:
        print(f"⚠️ AI review failed ({e}) — approving by default so pipeline isn't blocked.")
        return True


def main():
    api_key = os.environ.get("PEXELS_API_KEY")
    gemini_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        raise ValueError("❌ 'PEXELS_API_KEY' missing from environment (GitHub Actions secret)!")

    candidates_tried = 0
    last_downloaded = False

    while candidates_tried < MAX_CANDIDATES:
        query = random.choice(SEARCH_TERMS)
        print(f"\n🔍 Searching Pexels for: '{query}'...")
        videos = search_pexels(api_key, query)

        if not videos:
            print(f"   No results for '{query}', trying another term...")
            candidates_tried += 1
            continue

        video = random.choice(videos)
        file_url = sorted(video["video_files"], key=lambda f: f.get("height", 0), reverse=True)[0]["link"]

        print("⬇️ Downloading candidate background video...")
        download(file_url, OUTPUT_FILE)
        last_downloaded = True
        candidates_tried += 1

        if not gemini_key:
            print("ℹ️ No GEMINI_API_KEY set — skipping AI review, accepting this clip.")
            break

        try:
            extract_sample_frame(OUTPUT_FILE, SAMPLE_FRAME)
            approved = ai_review_frame(gemini_key, SAMPLE_FRAME)
        except Exception as e:
            print(f"⚠️ Could not extract/review frame ({e}) — accepting clip anyway.")
            approved = True

        if approved:
            print("✅ Background clip approved by AI review.")
            break
        else:
            print("🔁 Clip rejected — trying a different one...")

    if not last_downloaded:
        raise ValueError("❌ Could not find any usable background video after several attempts.")

    print(f"\n✅ Final background video saved to '{OUTPUT_FILE}'")


if __name__ == "__main__":
    main()
