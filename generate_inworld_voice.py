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
