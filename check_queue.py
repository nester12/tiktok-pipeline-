# -------------------------------------------------------------------
# Checks how many posts are currently queued on Buffer for this
# channel. Exits with code 1 (and prints a clear message) if the
# queue is already full, so the workflow can skip wasted generation
# work before it happens.
# -------------------------------------------------------------------
import os
import sys
import requests

BUFFER_GRAPHQL_URL = "https://api.buffer.com"
QUEUE_LIMIT = 10  # Buffer free plan cap per channel

QUERY = """
query GetQueuedPosts($channelId: ChannelId!) {
  posts(input: { channelId: $channelId, status: [PENDING] }) {
    edges {
      node {
        id
      }
    }
  }
}
"""


def main():
    token = os.environ.get("BUFFER_ACCESS_TOKEN")
    channel_id = os.environ.get("BUFFER_TIKTOK_CHANNEL_ID")

    if not token or not channel_id:
        print("⚠️ Missing Buffer credentials — skipping queue check, proceeding anyway.")
        return

    try:
        resp = requests.post(
            BUFFER_GRAPHQL_URL,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"query": QUERY, "variables": {"channelId": channel_id}},
            timeout=30,
        )
        data = resp.json()
        edges = data.get("data", {}).get("posts", {}).get("edges", [])
        count = len(edges)
        print(f"📊 Current queued posts: {count}/{QUEUE_LIMIT}")

        if count >= QUEUE_LIMIT:
            print("🛑 Queue is full — skipping generation for this video to avoid wasted work.")
            sys.exit(1)
    except Exception as e:
        print(f"⚠️ Could not check queue status ({e}) — proceeding anyway.")


if __name__ == "__main__":
    main()
