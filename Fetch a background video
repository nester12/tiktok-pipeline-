# -------------------------------------------------------------------
# Fetch a background video from Pexels (replaces the manual
# drag-and-drop upload cell, which won't work in headless Actions)
# -------------------------------------------------------------------
import os
import random
import requests

OUTPUT_FILE = "background.mp4"
SEARCH_TERMS = ["minecraft parkour", "satisfying", "subway surfers", "gta gameplay"]


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
        raise ValueError(f"❌ No Pexels results for '{query}'")

    video = random.choice(videos)
    # pick the highest-res vertical file available
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
