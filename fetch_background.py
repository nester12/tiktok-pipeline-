# -------------------------------------------------------------------
# Fetch a background video from Pexels — chosen for high motion /
# attention-grabbing footage that works well under text captions
# -------------------------------------------------------------------
import os
import random
import requests

OUTPUT_FILE = "background.mp4"
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


def main():
    api_key = os.environ.get("PEXELS_API_KEY")
    if not api_key:
        raise ValueError("❌ 'PEXELS_API_KEY' missing from environment (GitHub Actions secret)!")

    query = random.choice(SEARCH_TERMS)
    print(f"🔍 Searching Pexels for background footage: '{query}'...")

    headers = {"Authorization": api_key}
    resp = requests.get(
        "https://api.pexels.com/videos/search",
        headers=headers,
        params={"query": query, "orientation": "portrait", "per_page": 15}
    )
    resp.raise_for_status()
    videos = resp.json().get("videos", [])

    if not videos:
        # fallback to a safe, always-available search term
        query = "satisfying"
        resp = requests.get(
            "https://api.pexels.com/videos/search",
            headers=headers,
            params={"query": query, "orientation": "portrait", "per_page": 15}
        )
        resp.raise_for_status()
        videos = resp.json().get("videos", [])

    if not videos:
        raise ValueError(f"❌ No Pexels results for '{query}'")

    video = random.choice(videos)
    file_url = sorted(video["video_files"], key=lambda f: f.get("height", 0), reverse=True)[0]["link"]

    print(f"⬇️ Downloading background video...")
    with requests.get(file_url, stream=True) as r:
        r.raise_for_status()
        with open(OUTPUT_FILE, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

    print(f"✅ Saved background video to '{OUTPUT_FILE}'")


if __name__ == "__main__":
    main()
