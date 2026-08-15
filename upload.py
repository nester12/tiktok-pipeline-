# -------------------------------------------------------------------
# Post to TikTok via Zernio's unified posting API
# -------------------------------------------------------------------
import os
import sys
import json
import random
import requests
from datetime import datetime, timezone, timedelta

ZERNIO_URL = "https://zernio.com/api/v1/posts"
STORY_FILE = "story.txt"
TRENDING_HASHTAGS_FILE = "trending_hashtags.json"

ATTRIBUTION = "Background footage by GameplaysForFree, licensed under CC BY 4.0"
DEFAULT_HASHTAGS = ["storytime", "redditstories", "fyp"]
NUM_HASHTAGS_TO_USE = 5

MAX_CAPTION_LENGTH = 2200
MAX_HOOK_WORDS = 18

PENDING_QUEUE_FILE = "pending_queue.json"
QUEUE_LOG_FILE = "queue_log.json"


def build_hashtags():
    """Uses currently trending hashtags (from fetch_style_examples.py) if
    available, mixed with a couple of reliable defaults, otherwise falls
    back to the default set entirely."""
    tags = list(DEFAULT_HASHTAGS)

    if os.path.exists(TRENDING_HASHTAGS_FILE):
        try:
            with open(TRENDING_HASHTAGS_FILE, "r", encoding="utf-8") as f:
                trending = json.load(f)
            if trending:
                extra = random.sample(trending, min(NUM_HASHTAGS_TO_USE, len(trending)))
                for tag in extra:
                    if tag not in tags:
                        tags.append(tag)
        except Exception as e:
            print(f"⚠️ Could not load {TRENDING_HASHTAGS_FILE}, using default hashtags: {e}")

    return " ".join(f"#{t}" for t in tags)


def build_caption():
    """Uses a short hook pulled from the start of the generated story, plus
    trending hashtags and required CC BY 4.0 attribution for the background
    footage. Hard-capped at TikTok's 2200 character limit no matter what."""
    hook = "You won't believe what happened to me..."
    if os.path.exists(STORY_FILE):
        with open(STORY_FILE, "r", encoding="utf-8") as f:
            text = f.read().strip()
        if text:
            words = text.split()
            hook = " ".join(words[:MAX_HOOK_WORDS]).rstrip(",.;:") + "..."

    hashtags = build_hashtags()
    caption = f"{hook} {hashtags}\n\n{ATTRIBUTION}"

    if len(caption) > MAX_CAPTION_LENGTH:
        caption = caption[:MAX_CAPTION_LENGTH - 3] + "..."

    return caption


def load_pending_queue():
    if os.path.exists(PENDING_QUEUE_FILE):
        try:
            with open(PENDING_QUEUE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_to_pending_queue(video_url, caption):
    queue = load_pending_queue()
    queue.append({"video_url": video_url, "caption": caption})
    with open(PENDING_QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(queue, f, indent=2)
    print(f"💾 Saved unposted video to backlog ({PENDING_QUEUE_FILE}) — will retry next run.")


def log_queued_post(video_url, due_at):
    log = []
    if os.path.exists(QUEUE_LOG_FILE):
        try:
            with open(QUEUE_LOG_FILE, "r", encoding="utf-8") as f:
                log = json.load(f)
        except Exception:
            log = []
    log.append({"video_url": video_url, "due_at": due_at})
    with open(QUEUE_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2)


def post_to_zernio(video_url, caption, api_key, account_id, scheduled_for=None):
    """Returns (success: bool, message: str)."""
    payload = {
        "platforms": [{"platform": "tiktok", "accountId": account_id}],
        "content": caption,
        "mediaItems": [{"type": "video", "url": video_url}],
    }
    if scheduled_for:
        payload["scheduledFor"] = scheduled_for

    resp = requests.post(
        ZERNIO_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )

    try:
        data = resp.json()
    except Exception:
        data = {"raw": resp.text}

    print(data)

    if resp.status_code in (200, 201):
        post_id = data.get("id") or data.get("postId") or "unknown-id"
        due = data.get("scheduledFor") or scheduled_for or "immediately"
        return True, f"post id {post_id}, due {due}"

    error_msg = data.get("error") or data.get("message") or f"HTTP {resp.status_code}: {data}"
    return False, str(error_msg)


def main():
    api_key = os.environ.get("ZERNIO_API_KEY")
    account_id = os.environ.get("ZERNIO_TIKTOK_ACCOUNT_ID")
    video_url = os.environ.get("VIDEO_URL")

    missing = [name for name, val in [
        ("ZERNIO_API_KEY", api_key),
        ("ZERNIO_TIKTOK_ACCOUNT_ID", account_id),
        ("VIDEO_URL", video_url),
    ] if not val]

    if missing:
        raise ValueError(f"❌ Missing required environment variable(s): {', '.join(missing)}")

    print(f"📤 Posting to TikTok via Zernio...")
    print(f"   Video URL: {video_url}")

    caption = build_caption()
    print(f"   Caption: {caption}")

    # Post immediately (no scheduling needed — we control timing via our own 4x/day trigger)
    success, message = post_to_zernio(video_url, caption, api_key, account_id)

    if success:
        print(f"\n🎉 SUCCESS! Posted via Zernio — {message}")
        due_at = message.split("due ", 1)[1].strip() if "due " in message else None
        log_queued_post(video_url, due_at)
    else:
        print(f"❌ Zernio rejected the post: {message}")
        save_to_pending_queue(video_url, caption)
        sys.exit(1)


if __name__ == "__main__":
    main()
