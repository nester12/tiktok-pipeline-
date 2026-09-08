# -------------------------------------------------------------------
# Post to TikTok via Zernio's unified posting API.
# Uses the configured profile queues in rotation:
# Morning -> Midday -> Afternoon -> Evening -> repeat.
# -------------------------------------------------------------------
import os
import sys
import json
import random
import requests

ZERNIO_BASE_URL = "https://zernio.com/api/v1"
ZERNIO_POSTS_URL = f"{ZERNIO_BASE_URL}/posts"
ZERNIO_NEXT_SLOT_URL = f"{ZERNIO_BASE_URL}/queue/next-slot"
STORY_FILE = "story.txt"
TRENDING_HASHTAGS_FILE = "trending_hashtags.json"

ATTRIBUTION = "Background footage by GameplaysForFree, licensed under CC BY 4.0"
DEFAULT_HASHTAGS = ["storytime", "redditstories", "fyp"]
NUM_HASHTAGS_TO_USE = 5
MAX_CAPTION_LENGTH = 2200
MAX_HOOK_WORDS = 18

PENDING_QUEUE_FILE = "pending_queue.json"
QUEUE_LOG_FILE = "queue_log.json"
QUEUE_STATE_FILE = "queue_rotation_state.json"

QUEUE_ENV_ORDER = [
    ("Morning", "ZERNIO_MORNING_QUEUE_ID"),
    ("Midday", "ZERNIO_MIDDAY_QUEUE_ID"),
    ("Afternoon", "ZERNIO_AFTERNOON_QUEUE_ID"),
    ("Evening", "ZERNIO_EVENING_QUEUE_ID"),
]


def headers(api_key):
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


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
            print(f"Could not load {TRENDING_HASHTAGS_FILE}: {exc}")
    return " ".join(f"#{t}" for t in tags)


def build_caption():
    hook = "You won't believe what happened to me..."
    if os.path.exists(STORY_FILE):
        with open(STORY_FILE, "r", encoding="utf-8") as f:
            text = f.read().strip()
        if text:
            hook = " ".join(text.split()[:MAX_HOOK_WORDS]).rstrip(",.;:") + "..."
    caption = f"{hook} {build_hashtags()}\n\n{ATTRIBUTION}"
    return caption if len(caption) <= MAX_CAPTION_LENGTH else caption[:MAX_CAPTION_LENGTH - 3] + "..."


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
    print(f"Saved unposted video to backlog ({PENDING_QUEUE_FILE}).")


def log_queued_post(video_url, due_at, queue_id=None, queue_name=None, post_id=None):
    log = []
    if os.path.exists(QUEUE_LOG_FILE):
        try:
            with open(QUEUE_LOG_FILE, "r", encoding="utf-8") as f:
                log = json.load(f)
        except Exception:
            pass
    log.append({"video_url": video_url, "due_at": due_at, "queue_id": queue_id,
                "queue_name": queue_name, "post_id": post_id})
    with open(QUEUE_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2)


def configured_queues():
    queues, missing = [], []
    for name, env_name in QUEUE_ENV_ORDER:
        queue_id = os.environ.get(env_name)
        if queue_id:
            queues.append((name, queue_id))
        else:
            missing.append(env_name)
    if missing:
        print(f"Missing queue secret(s): {', '.join(missing)}")
    return queues


def load_rotation_index():
    try:
        if os.path.exists(QUEUE_STATE_FILE):
            with open(QUEUE_STATE_FILE, "r", encoding="utf-8") as f:
                return max(int(json.load(f).get("next_index", 0)), 0)
    except Exception as exc:
        print(f"Could not read queue rotation state: {exc}")
    return 0


def choose_next_queue():
    queues = configured_queues()
    if not queues:
        return None, None
    return queues[load_rotation_index() % len(queues)]


def advance_queue_rotation():
    queues = configured_queues()
    if queues:
        with open(QUEUE_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"next_index": (load_rotation_index() + 1) % len(queues)}, f, indent=2)


def get_next_queue_slot(api_key, profile_id, queue_id):
    """Ask Zernio for the next available time in the selected queue."""
    params = {"profileId": profile_id, "queueId": queue_id}
    resp = requests.get(ZERNIO_NEXT_SLOT_URL, headers=headers(api_key), params=params, timeout=60)
    try:
        data = resp.json()
    except Exception:
        data = {"raw": resp.text}

    if resp.status_code != 200:
        raise RuntimeError(f"Could not get next Zernio queue slot (HTTP {resp.status_code}): {data}")

    # Zernio returns nextSlot directly as an ISO timestamp string.
    next_slot = data.get("nextSlot") if isinstance(data, dict) else None
    if next_slot and "T" in str(next_slot):
        return str(next_slot)

    # Also tolerate wrapped response formats.
    candidates = [data]
    for key in ("slot", "nextSlot", "data"):
        value = data.get(key) if isinstance(data, dict) else None
        if isinstance(value, dict):
            candidates.append(value)
    for item in candidates:
        for key in ("scheduledFor", "scheduled_for", "dateTime", "datetime", "time", "nextSlot"):
            value = item.get(key) if isinstance(item, dict) else None
            if value and "T" in str(value):
                return str(value)

    raise RuntimeError(f"Zernio returned no usable next queue time: {data}")


def post_to_zernio_queue(video_url, caption, api_key, account_id, profile_id, queue_id):
    scheduled_for = get_next_queue_slot(api_key, profile_id, queue_id)
    print(f"Next queue slot: {scheduled_for}")

    payload = {
        "platforms": [{"platform": "tiktok", "accountId": account_id}],
        "content": caption,
        "mediaItems": [{"type": "video", "url": video_url}],
        "scheduledFor": scheduled_for,
        "queuedFromProfile": profile_id,
        "queueId": queue_id,
    }
    print(f"Adding TikTok video to Zernio queue {queue_id} for {scheduled_for}.")
    resp = requests.post(ZERNIO_POSTS_URL, headers=headers(api_key), json=payload, timeout=60)
    try:
        data = resp.json()
    except Exception:
        data = {"raw": resp.text}
    print(data)

    if resp.status_code not in (200, 201):
        return False, data.get("error") or data.get("message") or f"HTTP {resp.status_code}: {data}"

    post = data.get("post") if isinstance(data.get("post"), dict) else data
    post_id = post.get("_id") or post.get("id") or post.get("postId")
    returned_time = post.get("scheduledFor") or data.get("scheduledFor")
    status = str(post.get("status") or data.get("status") or "").lower()

    if not post_id or not returned_time or status == "draft":
        return False, f"Zernio accepted the request but did not queue it: {data}"

    return True, {"post_id": post_id, "scheduled_for": returned_time,
                  "queue_id": queue_id, "status": status or "scheduled"}


def main():
    api_key = os.environ.get("ZERNIO_API_KEY")
    account_id = os.environ.get("ZERNIO_TIKTOK_ACCOUNT_ID")
    profile_id = os.environ.get("ZERNIO_PROFILE_ID")
    video_url = os.environ.get("VIDEO_URL")

    missing = [name for name, val in [
        ("ZERNIO_API_KEY", api_key),
        ("ZERNIO_TIKTOK_ACCOUNT_ID", account_id),
        ("ZERNIO_PROFILE_ID", profile_id),
        ("VIDEO_URL", video_url),
    ] if not val]
    if missing:
        raise ValueError(f"Missing required environment variable(s): {', '.join(missing)}")

    queue_name, queue_id = choose_next_queue()
    if not queue_id:
        raise ValueError("No Zernio queue IDs are configured. Add the four queue ID secrets.")
    print(f"Next Zernio queue: {queue_name}")

    caption = build_caption()
    try:
        success, result = post_to_zernio_queue(video_url, caption, api_key, account_id,
                                                profile_id, queue_id)
    except Exception as exc:
        success, result = False, str(exc)

    if success:
        print(f"SUCCESS — queued post {result['post_id']} | status {result['status']} | "
              f"scheduled for {result['scheduled_for']} | queue {queue_name}")
        log_queued_post(video_url, result["scheduled_for"], result["queue_id"],
                        queue_name, result["post_id"])
        advance_queue_rotation()
    else:
        print(f"Zernio did not queue the post: {result}")
        save_to_pending_queue(video_url, caption)
        sys.exit(1)


if __name__ == "__main__":
    main()
