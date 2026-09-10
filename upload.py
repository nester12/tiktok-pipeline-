import os
import sys
import json
import random
import requests

BUFFER_API_URL = "https://api.buffer.com"
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
            print(f"Could not load {TRENDING_HASHTAGS_FILE}: {exc}")
    return " ".join(f"#{t}" for t in tags[:5])


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


def log_queued_post(video_url, due_at, post_id=None):
    log = []
    if os.path.exists(QUEUE_LOG_FILE):
        try:
            with open(QUEUE_LOG_FILE, "r", encoding="utf-8") as f:
                log = json.load(f)
        except Exception:
            pass
    log.append({"video_url": video_url, "due_at": due_at, "provider": "buffer", "post_id": post_id})
    with open(QUEUE_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2)


def graphql_string(value):
    return json.dumps(str(value))


def post_to_buffer_queue(video_url, caption, api_key, channel_id):
    query = f'''mutation CreateVideoPost {{
      createPost(input: {{
        text: {graphql_string(caption)}
        channelId: {graphql_string(channel_id)}
        schedulingType: automatic
        mode: addToQueue
        assets: [{{ video: {{ url: {graphql_string(video_url)} }} }}]
      }}) {{
        ... on PostActionSuccess {{
          post {{ id dueAt status }}
        }}
        ... on MutationError {{
          message
        }}
      }}
    }}'''

    resp = requests.post(
        BUFFER_API_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"query": query},
        timeout=60,
    )
    try:
        data = resp.json()
    except Exception:
        data = {"raw": resp.text}

    if resp.status_code != 200:
        return False, f"Buffer HTTP {resp.status_code}: {data}"
    if data.get("errors"):
        return False, f"Buffer GraphQL error: {data['errors']}"

    result = data.get("data", {}).get("createPost")
    if not isinstance(result, dict):
        return False, f"Buffer returned no createPost result: {data}"
    if result.get("message") and not result.get("post"):
        return False, result["message"]

    post = result.get("post")
    if not isinstance(post, dict) or not post.get("id"):
        return False, f"Buffer did not create a queued post: {data}"

    return True, {
        "post_id": post["id"],
        "scheduled_for": post.get("dueAt"),
        "status": post.get("status") or "scheduled",
    }


def main():
    api_key = os.environ.get("BUFFER_API_KEY")
    channel_id = os.environ.get("BUFFER_TIKTOK_CHANNEL_ID")
    video_url = os.environ.get("VIDEO_URL")

    missing = [name for name, val in [
        ("BUFFER_API_KEY", api_key),
        ("BUFFER_TIKTOK_CHANNEL_ID", channel_id),
        ("VIDEO_URL", video_url),
    ] if not val]
    if missing:
        raise ValueError(f"Missing required environment variable(s): {', '.join(missing)}")

    caption = build_caption()
    try:
        success, result = post_to_buffer_queue(video_url, caption, api_key, channel_id)
    except Exception as exc:
        success, result = False, str(exc)

    if success:
        print(f"SUCCESS — Buffer queued post {result['post_id']} | status {result['status']} | scheduled for {result['scheduled_for']}")
        log_queued_post(video_url, result["scheduled_for"], result["post_id"])
    else:
        print(f"Buffer did not queue the post: {result}")
        save_to_pending_queue(video_url, caption)
        sys.exit(1)


if __name__ == "__main__":
    main()
