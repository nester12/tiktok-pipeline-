import os
import json

from upload import PENDING_QUEUE_FILE, load_pending_queue, log_queued_post, post_to_buffer_queue


def main():
    api_key = os.environ.get("BUFFER_API_KEY")
    channel_id = os.environ.get("BUFFER_TIKTOK_CHANNEL_ID")

    if not api_key or not channel_id:
        print("Missing Buffer API key/channel — skipping backlog retry.")
        return

    queue = load_pending_queue()
    if not queue:
        print("No pending videos in backlog.")
        return

    print(f"Found {len(queue)} video(s) in backlog — retrying with Buffer...")
    still_pending = []

    for index, item in enumerate(queue):
        try:
            success, result = post_to_buffer_queue(
                item["video_url"], item["caption"], api_key, channel_id
            )
        except Exception as exc:
            success, result = False, str(exc)

        if success:
            print(f"Backlog video queued in Buffer — post {result['post_id']} | scheduled for {result['scheduled_for']}")
            log_queued_post(item["video_url"], result["scheduled_for"], result["post_id"])
        else:
            result_text = str(result)
            print(f"Still couldn't queue ({result_text}) — keeping in backlog.")
            still_pending.append(item)
            if "limit" in result_text.lower() or "rate" in result_text.lower():
                still_pending.extend(queue[index + 1:])
                break

    with open(PENDING_QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(still_pending, f, indent=2)

    print(f"Backlog result: {len(queue) - len(still_pending)} queued, {len(still_pending)} still pending.")


if __name__ == "__main__":
    main()
