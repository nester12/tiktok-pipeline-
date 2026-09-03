# -------------------------------------------------------------------
# Post to TikTok via Zernio's unified posting API
# -------------------------------------------------------------------
import os
import sys
import json
import random
import requests

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
        except Exception as exc:
            print(f"⚠️ Could not load {TRENDING_HASHTAGS_FILE}: {exc}")
    return " ".join(f"#{t}" for t in tags)


def build_caption():
    hook = "You won't believe what happened to me..."
    if os.path.exists(STORY_FILE):
        with open(STORY_FILE, "r", encoding="utf-8") as f:
            text = f.read().strip()
        if text:
            hook = " ".join(text.split()[:MAX_HOOK_WORDS]).rstrip(",.;:") + "..."

    caption = f"{hook} {build_hashtags()}\n\n{ATTRIBUTION}"
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
    print(f"💾 Saved unposted video to backlog ({PENDING_QUEUE_FILE}).")


def log_queued_post(video_url, due_at, queue_id=None):
    log = []
    if os.path.exists(QUEUE_LOG_FILE):
        try:
            with open(QUEUE_LOG_FILE, "r", encoding="utf-8") as f:
                log = json.load(f)
        except Exception:
            log = []
    log.append({"video_url": video_url, "due_at": due_at, "queue_id": queue_id})
    with open(QUEUE_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2)


def post_to_zernio(video_url, caption, api_key, account_id, profile_id=None, queue_id=None):
    """Create a TikTok post. Uses Zernio profile queue scheduling when profile_id is set."""
    payload = {
        "platforms": [{"platform": "tiktok", "accountId": account_id}],
        "content": caption,
        "mediaItems": [{"type": "video", "url": video_url}],
    }

    if profile_id:
        payload["queuedFromProfile"] = profile_id
        if queue_id:
            payload["queueId"] = queue_id
        print(f"🗓️ Sending post to Zernio profile queue: {profile_id}")
    else:
        print("⚠️ ZERNIO_PROFILE_ID not set — posting immediately instead of using a queue.")

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
        post = data.get("post") if isinstance(data.get("post"), dict) else data
        post_id = post.get("id") or post.get("postId") or "unknown-id"
        due = post.get("scheduledFor") or "immediately"
        assigned_queue = post.get("queueId") or data.get("queueId")
        status = post.get("status") or data.get("status") or "unknown"
        return True, {
            "post_id": post_id,
            "scheduled_for": due,
            "queue_id": assigned_queue,
            "status": status,
        }

    error_msg = data.get("error") or data.get("message") or f"HTTP {resp.status_code}: {data}"
    return False, str(error_msg)


def main():
    api_key = os.environ.get("ZERNIO_API_KEY")
    account_id = os.environ.get("ZERNIO_TIKTOK_ACCOUNT_ID")
    profile_id = os.environ.get("ZERNIO_PROFILE_ID")
    queue_id = os.environ.get("ZERNIO_QUEUE_ID")
    video_url = os.environ.get("VIDEO_URL")

    missing = [name for name, val in [
        ("ZERNIO_API_KEY", api_key),
        ("ZERNIO_TIKTOK_ACCOUNT_ID", account_id),
        ("VIDEO_URL", video_url),
    ] if not val]
    if missing:
        raise ValueError(f"❌ Missing required environment variable(s): {', '.join(missing)}")

    print("📤 Sending TikTok post to Zernio...")
    print(f"   Video URL: {video_url}")

    caption = build_caption()
    print(f"   Caption: {caption}")

    success, result = post_to_zernio(
        video_url,
        caption,
        api_key,
        account_id,
        profile_id=profile_id,
        queue_id=queue_id,
    )

    if success:
        print(
            f"🎉 SUCCESS — post {result['post_id']} | status {result['status']} | "
            f"scheduled for {result['scheduled_for']}"
        )
        log_queued_post(video_url, result["scheduled_for"], result["queue_id"])
    else:
        print(f"❌ Zernio rejected the post: {result}")
        save_to_pending_queue(video_url, caption)
        sys.exit(1)


if __name__ == "__main__":
    main()
