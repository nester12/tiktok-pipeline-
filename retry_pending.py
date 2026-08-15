# -------------------------------------------------------------------
# Retries any videos left over in the backlog from a previous run
# (e.g. a post failed or hit a rate limit). Runs BEFORE generating
# anything new, so unposted videos get first priority once there's
# room.
# -------------------------------------------------------------------
import os
import json
from upload import load_pending_queue, post_to_zernio, log_queued_post, PENDING_QUEUE_FILE


def main():
    api_key = os.environ.get("ZERNIO_API_KEY")
    account_id = os.environ.get("ZERNIO_TIKTOK_ACCOUNT_ID")

    if not api_key or not account_id:
        print("⚠️ Missing Zernio credentials — skipping backlog retry.")
        return

    queue = load_pending_queue()
    if not queue:
        print("📭 No pending videos in backlog.")
        return

    print(f"📬 Found {len(queue)} video(s) in backlog — retrying...")
    still_pending = []

    for item in queue:
        success, message = post_to_zernio(item["video_url"], item["caption"], api_key, account_id)
        if success:
            print(f"✅ Backlog video posted — {message}")
            due_at = message.split("due ", 1)[1].strip() if "due " in message else None
            log_queued_post(item["video_url"], due_at)
        else:
            print(f"❌ Still couldn't post ({message}) — keeping in backlog.")
            still_pending.append(item)
            if "limit" in message.lower() or "rate" in message.lower():
                still_pending.extend(queue[queue.index(item) + 1:])
                break

    with open(PENDING_QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(still_pending, f, indent=2)

    print(f"\n📊 Backlog result: {len(queue) - len(still_pending)} posted, {len(still_pending)} still pending.")


if __name__ == "__main__":
    main()
