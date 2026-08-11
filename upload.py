# -------------------------------------------------------------------
# Post to TikTok via Buffer's GraphQL API
# -------------------------------------------------------------------
import os
import sys
import requests

BUFFER_GRAPHQL_URL = "https://api.buffer.com"
STORY_FILE = "story.txt"

ATTRIBUTION = "Background footage by GameplaysForFree, licensed under CC BY 4.0"
HASHTAGS = "#storytime #redditstories #fyp"


MAX_CAPTION_LENGTH = 2200
MAX_HOOK_WORDS = 18


def build_caption():
    """Uses a short hook pulled from the start of the generated story, plus
    required CC BY 4.0 attribution for the background footage. Hard-capped
    at TikTok's 2200 character limit no matter what."""
    hook = "You won't believe what happened to me..."
    if os.path.exists(STORY_FILE):
        with open(STORY_FILE, "r", encoding="utf-8") as f:
            text = f.read().strip()
        if text:
            words = text.split()
            hook = " ".join(words[:MAX_HOOK_WORDS]).rstrip(",.;:") + "..."

    caption = f"{hook} {HASHTAGS}\n\n{ATTRIBUTION}"

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
