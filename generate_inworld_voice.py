"""Optional Inworld voice generation for story.txt; requires explicit opt-in."""
import os
import json
import base64
import subprocess
from pathlib import Path
import requests

def main():
    story = Path("story.txt").read_text(encoding="utf-8").strip()
    if not story:
        raise ValueError("Empty story")
    if len(story.encode("utf-16-le")) // 2 > 1900:
        raise ValueError("Story exceeds TTS request size")
    if os.getenv("ENABLE_PAID_TTS") != "YES":
        print("Voice preview mode; no provider request")
        return
    from datetime import datetime, timezone
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    price = float(os.environ["ESTIMATED_TTS_GBP_PER_MILLION_CHARS"])
    cap = float(os.getenv("MONTHLY_TTS_BUDGET_GBP", "3"))
    if price <= 0 or cap <= 0:
        raise ValueError("Set positive TTS price and budget")
    ledger_file = Path("tts_spend_ledger.json")
    ledger = json.loads(ledger_file.read_text()) if ledger_file.exists() else {}
    projected = len(story) * price / 1_000_000
    if float(ledger.get(month, 0)) + projected > cap:
        raise RuntimeError("Estimated monthly TTS budget exceeded")
    ledger[month] = round(float(ledger.get(month, 0)) + projected, 6)
    ledger_file.write_text(json.dumps(ledger, indent=2))
    key = os.environ["INWORLD_API_KEY"]
    result = requests.post(
        "https://api.inworld.ai/tts/v1/voice",
        headers={"Authorization": "Basic " + key},
        json={"text": story, "voiceId": os.getenv("INWORLD_VOICE_NAME", "Dennis"),
              "modelId": "inworld-tts-2", "audioConfig": {"audioEncoding": "MP3"}},
        timeout=120,
    )
    result.raise_for_status()
    Path("narration_inworld.mp3").write_bytes(base64.b64decode(result.json()["audioContent"]))
    subprocess.run(["ffmpeg", "-y", "-i", "narration_inworld.mp3", "narration.wav"], check=True)
    print("Narration generated. Re-run timestamps alignment.")

if __name__ == "__main__":
    main()
