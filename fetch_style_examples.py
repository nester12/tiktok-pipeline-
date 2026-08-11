# -------------------------------------------------------------------
# Pulls real transcripts from example TikTok accounts via SocialCrawl,
# to use as few-shot style examples for story generation.
# Run this OCCASIONALLY (not every pipeline run) — it costs API
# credits. Saves results to style_examples.json in the repo.
# -------------------------------------------------------------------
import os
import json
import requests

TARGET_HANDLES = ["aethryn", "textplan", "best_texting"]
VIDEOS_PER_HANDLE = 3
OUTPUT_FILE = "style_examples.json"

BASE_URL = "https://www.socialcrawl.dev/v1"


def get_headers(api_key):
    return {"x-api-key": api_key}


def get_recent_videos(api_key, handle, limit):
    print(f"🔍 Fetching recent videos for @{handle}...")
    resp = requests.get(
        f"{BASE_URL}/tiktok/profile-videos",
        headers=get_headers(api_key),
        params={"handle": handle, "limit": limit},
    )
    if resp.status_code != 200:
        print(f"⚠️ Could not fetch videos for @{handle}: {resp.status_code} {resp.text}")
        return []
    data = resp.json().get("data", {})
    return data.get("items", [])


def get_transcript(api_key, video_url):
    resp = requests.get(
        f"{BASE_URL}/tiktok/video/transcript",
        headers=get_headers(api_key),
        params={"url": video_url},
    )
    if resp.status_code != 200:
        print(f"   ⚠️ No transcript for {video_url}: {resp.status_code}")
        return None
    data = resp.json().get("data", {})
    return data.get("transcript") or data.get("text")


def main():
    api_key = os.environ.get("SOCIALCRAWL_API_KEY")
    if not api_key:
        raise ValueError("❌ 'SOCIALCRAWL_API_KEY' missing from environment!")

    examples = []

    for handle in TARGET_HANDLES:
        videos = get_recent_videos(api_key, handle, VIDEOS_PER_HANDLE)
        for video in videos:
            video_url = video.get("url") or video.get("video_url")
            if not video_url:
                continue
            print(f"   📝 Getting transcript for {video_url}...")
            transcript = get_transcript(api_key, video_url)
            if transcript and len(transcript.split()) > 20:
                examples.append({
                    "handle": handle,
                    "caption": video.get("caption", ""),
                    "transcript": transcript.strip(),
                })

    if not examples:
        print("⚠️ No usable transcripts were collected. Keeping existing style_examples.json (if any) unchanged.")
        return

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(examples, f, indent=2)

    print(f"\n✅ Saved {len(examples)} style examples to '{OUTPUT_FILE}'")
    for ex in examples:
        print(f"   - @{ex['handle']}: {ex['transcript'][:80]}...")


if __name__ == "__main__":
    main()
