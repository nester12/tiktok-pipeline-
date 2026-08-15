# -------------------------------------------------------------------
# Safety-net check using a LOCAL ledger (queue_log.json) of posts
# we've sent to Zernio recently. Zernio's free tier has no fixed
# queue cap (unlike Buffer's old 10-post limit), but TikTok itself
# enforces its own strict, undocumented daily posting limit for
# third-party API posts — so this stays as a conservative safety
# net to avoid hammering that limit and wasting generation work.
# -------------------------------------------------------------------
import os
import sys
import json
from datetime import datetime, timezone

QUEUE_LOG_FILE = "queue_log.json"
SAFETY_LIMIT = 10  # conservative cap — adjust if you learn TikTok's real daily limit for your account


def parse_due_at(due_at_str):
    if not due_at_str:
        return None
    try:
        cleaned = due_at_str.replace("Z", "+00:00")
        return datetime.fromisoformat(cleaned)
    except Exception:
        return None


def main():
    if not os.path.exists(QUEUE_LOG_FILE):
        print("📊 No queue log yet — assuming room to post.")
        return

    try:
        with open(QUEUE_LOG_FILE, "r", encoding="utf-8") as f:
            log = json.load(f)
    except Exception:
        print("⚠️ Could not read queue log — assuming room to post.")
        return

    now = datetime.now(timezone.utc)
    still_pending = []

    for entry in log:
        due_at = parse_due_at(entry.get("due_at"))
        if due_at is None or due_at > now:
            still_pending.append(entry)

    with open(QUEUE_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(still_pending, f, indent=2)

    count = len(still_pending)
    print(f"📊 Recently posted/pending count: {count}/{SAFETY_LIMIT}")

    if count >= SAFETY_LIMIT:
        print("🛑 Safety limit reached — skipping generation for this run.")
        sys.exit(1)


if __name__ == "__main__":
    main()
