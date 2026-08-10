# -------------------------------------------------------------------
# Generate TTS Voiceover & Word Timestamps
# -------------------------------------------------------------------
import os
import json
import asyncio
import whisper
import edge_tts

STORY_FILE = "story.txt"
AUDIO_FILE = "narration.mp3"
JSON_FILE = "timestamps.json"
VOICE = "en-US-ChristopherNeural"


async def generate_audio(story_text):
    print(f"🎙️ Generating voiceover audio with voice '{VOICE}'...")
    communicate = edge_tts.Communicate(story_text, VOICE)
    await communicate.save(AUDIO_FILE)
    print(f"✅ Voiceover saved as '{AUDIO_FILE}'!")


def main():
    if not os.path.exists(STORY_FILE):
        raise FileNotFoundError(f"❌ '{STORY_FILE}' missing! Run generate_story.py first.")

    with open(STORY_FILE, "r", encoding="utf-8") as f:
        story_text = f.read().strip()

    # 1. Generate voiceover audio
    asyncio.run(generate_audio(story_text))

    # 2. Extract precise word timestamps with Whisper
    print("⏳ Analyzing speech audio with Whisper for word timestamps...")
    model = whisper.load_model("tiny")
    result = model.transcribe(AUDIO_FILE, word_timestamps=True)

    word_timestamps = []
    for segment in result["segments"]:
        for word_info in segment.get("words", []):
            word_timestamps.append({
                "word": word_info["word"].strip(),
                "start": round(word_info["start"], 2),
                "end": round(word_info["end"], 2)
            })

    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(word_timestamps, f, indent=2)

    print(f"\n✅ Created '{JSON_FILE}' with {len(word_timestamps)} word timing entries!")


if __name__ == "__main__":
    main()
