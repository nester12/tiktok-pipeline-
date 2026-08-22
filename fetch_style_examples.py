# -------------------------------------------------------------------
# Pulls trending videos from SocialCrawl — both by hashtag search
# (broad discovery, not limited to fixed accounts) and from a seed
# list of reference accounts — extracts transcripts + engagement
# metadata, then runs an AI analysis pass to surface patterns
# (common hashtags, hook styles, what's actually performing well).
#
# Run this OCCASIONALLY (weekly via schedule, or manually) — it
# costs SocialCrawl API credits. Not meant to run on every post.
# -------------------------------------------------------------------
import os
import json
import requests

BASE_URL = "https://www.socialcrawl.dev/v1"

# Broad discovery via hashtags, not limited to 3 fixed accounts
HASHTAGS_TO_SEARCH = [
    "storytime", "redditstories", "storytelling",
    "confession", "aitastories", "fyp",
]
VIDEOS_PER_HASHTAG = 12

# Still keep a seed list of known-good accounts as a secondary source
SEED_HANDLES = ["aethryn", "textplan", "best_texting"]
VIDEOS_PER_HANDLE = 8

# Your own account — tracked separately so we can see what's actually
# working on your channel specifically, not just external inspiration
OWN_HANDLE = "only1_short_story"
VIDEOS_FROM_OWN_ACCOUNT = 20  # pull as many as exist; harmless if fewer are available

STYLE_EXAMPLES_FILE = "style_examples.json"
TRENDING_HASHTAGS_FILE = "trending_hashtags.json"
STYLE_NOTES_FILE = "style_notes.txt"
TARGET_PACE_FILE = "target_pace.json"


def get_headers(api_key):
    return {"x-api-key": api_key}


def get_hashtag_videos(api_key, hashtag, limit):
    print(f"🔍 Searching hashtag #{hashtag}...")
    resp = requests.get(
        f"{BASE_URL}/tiktok/hashtag/videos",
        headers=get_headers(api_key),
        params={"hashtag": hashtag, "limit": limit},
    )
    if resp.status_code != 200:
        print(f"⚠️ Hashtag search failed for #{hashtag}: {resp.status_code} {resp.text[:200]}")
        return []
    data = resp.json().get("data", {})
    return data.get("items", [])


def get_profile_videos(api_key, handle, limit):
    print(f"🔍 Fetching recent videos for @{handle}...")
    resp = requests.get(
        f"{BASE_URL}/tiktok/profile-videos",
        headers=get_headers(api_key),
        params={"handle": handle, "limit": limit},
    )
    if resp.status_code != 200:
        print(f"⚠️ Could not fetch videos for @{handle}: {resp.status_code} {resp.text[:200]}")
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
        return None
    data = resp.json().get("data", {})
    return data.get("transcript") or data.get("text")


def extract_hashtags(caption):
    if not caption:
        return []
    return [w.strip("#").lower() for w in caption.split() if w.startswith("#")]


def collect_videos(api_key):
    """Gathers video candidates from both hashtag search and seed accounts, deduped by URL."""
    seen_urls = set()
    candidates = []

    for tag in HASHTAGS_TO_SEARCH:
        for video in get_hashtag_videos(api_key, tag, VIDEOS_PER_HASHTAG):
            url = video.get("url") or video.get("video_url")
            if url and url not in seen_urls:
                seen_urls.add(url)
                video["_source"] = f"#{tag}"
                candidates.append(video)

    for handle in SEED_HANDLES:
        for video in get_profile_videos(api_key, handle, VIDEOS_PER_HANDLE):
            url = video.get("url") or video.get("video_url")
            if url and url not in seen_urls:
                seen_urls.add(url)
                video["_source"] = f"@{handle}"
                candidates.append(video)

    # Own account — tagged distinctly so it's clear this is real
    # performance data from your own posted videos, not inspiration
    for video in get_profile_videos(api_key, OWN_HANDLE, VIDEOS_FROM_OWN_ACCOUNT):
        url = video.get("url") or video.get("video_url")
        if url and url not in seen_urls:
            seen_urls.add(url)
            video["_source"] = f"@{OWN_HANDLE} (own account)"
            candidates.append(video)

    return candidates


def analyze_patterns(examples, nvidia_key):
    """Asks GLM-5.2 (via NVIDIA NIM) to summarize what's working across the
    collected examples, with special attention to how the account's own
    videos compare to external trending examples. GLM-5.2 is well suited
    to this — it's a structured reasoning/extraction task, not creative
    writing, which is where GLM-5.2 is actually strong."""
    if not nvidia_key or not examples:
        return ""

    own_examples = [ex for ex in examples if "own account" in ex["source"]]
    other_examples = [ex for ex in examples if "own account" not in ex["source"]]

    sample_text = "\n\n---\n\n".join(
        f"Source: {ex['source']}\nViews: {ex.get('views', 'unknown')}\n"
        f"Transcript: {ex['transcript'][:500]}"
        for ex in other_examples[:12]
    )

    own_text = "\n\n---\n\n".join(
        f"Views: {ex.get('views', 'unknown')}\nTranscript: {ex['transcript'][:500]}"
        for ex in own_examples[:8]
    ) or "(no videos from your own account collected this run)"

    prompt = (
        "Here are transcripts from currently trending 'reddit story' style TikTok videos "
        "from OTHER accounts, with view counts where available:\n\n"
        f"{sample_text}\n\n"
        "Here are transcripts from MY OWN TikTok account's videos, with their actual "
        "view counts:\n\n"
        f"{own_text}\n\n"
        "Analyze both sets and write a short set of concrete notes (bullet points, under "
        "180 words) covering: (1) patterns in what's performing well externally — hook "
        "styles, structure, pacing; (2) how my own videos compare — are they matching "
        "those patterns or missing something; (3) one or two specific things to try "
        "differently next. Be specific and actionable, not generic."
    )

    try:
        resp = requests.post(
            "https://integrate.api.nvidia.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {nvidia_key}", "Content-Type": "application/json"},
            json={
                "model": "z-ai/glm-5.2",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.5,
                "max_tokens": 400,
            },
        )
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"⚠️ Pattern analysis failed: {e}")

    return ""


def main():
    api_key = os.environ.get("SOCIALCRAWL_API_KEY")
    nvidia_key = os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        raise ValueError("❌ 'SOCIALCRAWL_API_KEY' missing from environment!")

    candidates = collect_videos(api_key)
    print(f"\n📦 Collected {len(candidates)} unique candidate videos, fetching transcripts...")

    examples = []
    hashtag_counter = {}
    wpm_samples = []

    for video in candidates:
        url = video.get("url") or video.get("video_url")
        caption = video.get("caption", "")
        views = video.get("views") or video.get("view_count")
        video_duration = video.get("duration") or video.get("video_duration")

        for tag in extract_hashtags(caption):
            hashtag_counter[tag] = hashtag_counter.get(tag, 0) + 1

        transcript = get_transcript(api_key, url)
        if transcript and len(transcript.split()) > 20:
            word_count = len(transcript.split())
            examples.append({
                "source": video["_source"],
                "caption": caption,
                "views": views,
                "duration": video_duration,
                "transcript": transcript.strip(),
            })

            # Only trust WPM from videos with real duration data and a
            # sane word count (filters out obviously bad/partial data)
            if video_duration and video_duration > 5 and word_count > 20:
                wpm = (word_count / video_duration) * 60
                if 60 <= wpm <= 220:  # sanity range — excludes clearly broken data
                    wpm_samples.append(wpm)

    if not examples:
        print("⚠️ No usable transcripts collected this run. Leaving existing files unchanged.")
        return

    # Sort by views (highest first) where we have that data, unknowns last
    examples.sort(key=lambda e: (e["views"] is None, -(e["views"] or 0)))

    with open(STYLE_EXAMPLES_FILE, "w", encoding="utf-8") as f:
        json.dump(examples, f, indent=2)
    print(f"✅ Saved {len(examples)} style examples to '{STYLE_EXAMPLES_FILE}'")

    top_hashtags = sorted(hashtag_counter.items(), key=lambda x: -x[1])[:15]
    with open(TRENDING_HASHTAGS_FILE, "w", encoding="utf-8") as f:
        json.dump([tag for tag, _ in top_hashtags], f, indent=2)
    print(f"✅ Saved top hashtags to '{TRENDING_HASHTAGS_FILE}': {[t for t,_ in top_hashtags]}")

    if wpm_samples:
        avg_wpm = sum(wpm_samples) / len(wpm_samples)
        with open(TARGET_PACE_FILE, "w", encoding="utf-8") as f:
            json.dump({"avg_wpm": round(avg_wpm, 1), "sample_size": len(wpm_samples)}, f, indent=2)
        print(f"✅ Saved target pacing to '{TARGET_PACE_FILE}': {avg_wpm:.1f} WPM (from {len(wpm_samples)} videos)")
    else:
        print("ℹ️ No duration data available this run — target_pace.json left unchanged.")

    notes = analyze_patterns(examples, nvidia_key)
    if notes:
        with open(STYLE_NOTES_FILE, "w", encoding="utf-8") as f:
            f.write(notes)
        print(f"✅ Saved AI pattern analysis to '{STYLE_NOTES_FILE}':\n{notes}")


if __name__ == "__main__":
    main()
