# -------------------------------------------------------------------
# Retries any videos left over in the backlog from a previous run
# (e.g. Buffer's queue was full). Runs BEFORE generating anything
# new, so unposted videos get first priority once there's room.
# -------------------------------------------------------------------
import os
import sys
from upload import load_pending_queue, save_to_pending_queue, post_to_buffer, PENDING_QUEUE_FILE
import json


def main():
    token = os.environ.get("BUFFER_ACCESS_TOKEN")
    channel_id = os.environ.get("BUFFER_TIKTOK_CHANNEL_ID")

    if not token or not channel_id:
        print("⚠️ Missing Buffer credentials — skipping backlog retry.")
        return

    queue = load_pending_queue()
    if not queue:
        print("📭 No pending videos in backlog.")
        return

    print(f"📬 Found {len(queue)} video(s) in backlog — retrying...")
    still_pending = []

    for item in queue:
        success, message = post_to_buffer(item["video_url"], item["caption"], token, channel_id)
        if success:
            print(f"✅ Backlog video posted — {message}")
        else:
            print(f"❌ Still couldn't post ({message}) — keeping in backlog.")
            still_pending.append(item)
            if "limit reached" in message.lower() or "queue" in message.lower():
                # Queue's still full — no point trying the rest right now
                still_pending.extend(queue[queue.index(item) + 1:])
                break

    with open(PENDING_QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(still_pending, f, indent=2)

    print(f"\n📊 Backlog result: {len(queue) - len(still_pending)} posted, {len(still_pending)} still pending.")


if __name__ == "__main__":
    main()
