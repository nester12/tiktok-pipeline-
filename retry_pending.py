# -------------------------------------------------------------------
# Retry videos left in the backlog from previous runs.
# Uses the same four-queue rotation as new posts.
# -------------------------------------------------------------------
import os
import json

from upload import (
    PENDING_QUEUE_FILE,
    advance_queue_rotation,
    choose_next_queue,
    load_pending_queue,
    log_queued_post,
    post_to_zernio,
)


def main():
    api_key = os.environ.get("ZERNIO_API_KEY")
    account_id = os.environ.get("ZERNIO_TIKTOK_ACCOUNT_ID")
    profile_id = os.environ.get("ZERNIO_PROFILE_ID")

    if not api_key or not account_id:
        print("⚠️ Missing Zernio credentials — skipping backlog retry.")
        return

    queue = load_pending_queue()
    if not queue:
        print("📭 No pending videos in backlog.")
        return

    print(f"📬 Found {len(queue)} video(s) in backlog — retrying...")
    still_pending = []

    for index, item in enumerate(queue):
        queue_name, queue_id = choose_next_queue()
        if queue_name:
            print(f"🔄 Backlog post using queue: {queue_name}")

        success, result = post_to_zernio(
            item["video_url"],
            item["caption"],
            api_key,
            account_id,
            profile_id=profile_id,
            queue_id=queue_id,
        )

        if success:
            print(
                f"✅ Backlog video accepted — post {result['post_id']} | "
                f"scheduled for {result['scheduled_for']} | queue {queue_name or 'default'}"
            )
            log_queued_post(
                item["video_url"],
                result["scheduled_for"],
                result["queue_id"],
                queue_name,
            )
            if queue_id:
                advance_queue_rotation()
        else:
            print(f"❌ Still couldn't post ({result}) — keeping in backlog.")
            still_pending.append(item)
            if "limit" in result.lower() or "rate" in result.lower():
                still_pending.extend(queue[index + 1:])
                break

    with open(PENDING_QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(still_pending, f, indent=2)

    print(
        f"📊 Backlog result: {len(queue) - len(still_pending)} accepted, "
        f"{len(still_pending)} still pending."
    )


if __name__ == "__main__":
    main()
