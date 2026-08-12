# -------------------------------------------------------------------
# Post to TikTok via Buffer's GraphQL API
# -------------------------------------------------------------------
import os
import sys
import json
import random
import requests

BUFFER_GRAPHQL_URL = "https://api.buffer.com"
STORY_FILE = "story.txt"
TRENDING_HASHTAGS_FILE = "trending_hashtags.json"

ATTRIBUTION = "Background footage by GameplaysForFree, licensed under CC BY 4.0"
DEFAULT_HASHTAGS = ["storytime", "redditstories", "fyp"]
NUM_HASHTAGS_TO_USE = 5


MAX_CAPTION_LENGTH = 2200
MAX_HOOK_WORDS = 18


def build_hashtags():
    """Uses currently trending hashtags (from fetch_style_examples.py) if
    available, mixed with a couple of reliable defaults, otherwise falls
    back to the default set entirely."""
    tags = list(DEFAULT_HASHTAGS)  # always include these as a safe baseline

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

CREATE_POST_MUTATION = """
mutation CreatePost($channelId: ChannelId!, $text: String!, $videoUrl: String!) {
  createPost(
    input: {
      text: $text
      channelId: $channelId
      schedulingType: automatic
      mode: addToQueue
      assets: [
        { video: { url: $videoUrl } }
      ]
    }
  ) {
    ... on PostActionSuccess {
      post {
        id
        dueAt
      }
    }
    ... on MutationError {
      message
    }
  }
}
"""


def main():
    token = os.environ.get("BUFFER_ACCESS_TOKEN")
    channel_id = os.environ.get("BUFFER_TIKTOK_CHANNEL_ID")
    video_url = os.environ.get("VIDEO_URL")

    missing = [name for name, val in [
        ("BUFFER_ACCESS_TOKEN", token),
        ("BUFFER_TIKTOK_CHANNEL_ID", channel_id),
        ("VIDEO_URL", video_url),
    ] if not val]

    if missing:
        raise ValueError(f"❌ Missing required environment variable(s): {', '.join(missing)}")

    print(f"📤 Posting to TikTok via Buffer...")
    print(f"   Video URL: {video_url}")

    caption = build_caption()
    print(f"   Caption: {caption}")

    resp = requests.post(
        BUFFER_GRAPHQL_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={
            "query": CREATE_POST_MUTATION,
            "variables": {
                "channelId": channel_id,
                "text": caption,
                "videoUrl": video_url,
            },
        },
        timeout=60,
    )

    data = resp.json()
    print(data)

    result = data.get("data", {}).get("createPost", {})

    if result.get("message"):
        raise RuntimeError(f"❌ Buffer rejected the post: {result['message']}")

    post = result.get("post")
    if post:
        print(f"\n🎉 SUCCESS! Queued on Buffer — post id {post['id']}, due {post.get('dueAt')}")
    else:
        raise RuntimeError(f"❌ Unexpected response from Buffer: {data}")


if __name__ == "__main__":
    main()
