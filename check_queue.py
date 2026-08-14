# -------------------------------------------------------------------
# Checks how many of our own recently-queued posts are still likely
# pending on Buffer, using a LOCAL ledger (queue_log.json) rather
# than querying Buffer directly — we don't have a confirmed API for
# listing pending posts, but we do reliably get a dueAt timestamp
# back every time we successfully queue one, so we track that
# ourselves instead.
#
# A post counts as "still in the queue" if its due_at time hasn't
# passed yet. Once due_at is in the past, we assume Buffer has
# posted it and it's no longer taking up a queue slot.
# -------------------------------------------------------------------
import os
import sys
import json
from datetime import datetime, timezone

QUEUE_LOG_FILE = "queue_log.json"
QUEUE_LIMIT = 10  # Buffer free plan cap per channel


def parse_due_at(due_at_str):
    if not due_at_str:
        return None
    try:
        # Handle common ISO formats, with or without 'Z'
        cleaned = due_at_str.replace("Z", "+00:00")
        return datetime.fromisoformat(cleaned)
    except Exception:
        return None


def main():
    if not os.path.exists(QUEUE_LOG_FILE):
        print("📊 No queue log yet — assuming queue has room.")
        return

    try:
        with open(QUEUE_LOG_FILE, "r", encoding="utf-8") as f:
            log = json.load(f)
    except Exception:
        print("⚠️ Could not read queue log — assuming queue has room.")
        return

    now = datetime.now(timezone.utc)
    still_pending = []

    for entry in log:
        due_at = parse_due_at(entry.get("due_at"))
        if due_at is None or due_at > now:
            # Unknown due date, or still in the future — count as pending
            still_pending.append(entry)

    # Prune the log file to just what's still relevant, so it doesn't grow forever
    with open(QUEUE_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(still_pending, f, indent=2)

    count = len(still_pending)
    print(f"📊 Estimated queued posts still pending: {count}/{QUEUE_LIMIT}")

    if count >= QUEUE_LIMIT:
        print("🛑 Queue is likely full — skipping generation for this run to avoid wasted work.")
        sys.exit(1)


if __name__ == "__main__":
    main()
