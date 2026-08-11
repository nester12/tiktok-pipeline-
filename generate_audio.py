# -------------------------------------------------------------------
# Generate TTS Voiceover & Word Timestamps
# Includes an automatic retry loop that regenerates the story with
# an adjusted length until the final audio lands between 60-120s.
# -------------------------------------------------------------------
import os
import json
import asyncio
import whisper
import edge_tts
from moviepy.editor import AudioFileClip

from generate_story import generate_story, STORY_NICHES
import random

STORY_FILE = "story.txt"
AUDIO_FILE = "narration.mp3"
JSON_FILE = "timestamps.json"
VOICE = "en-US-AndrewNeural"  # warmer, more expressive narrator-style voice
RATE = "+15%"

MIN_DURATION = 60
MAX_DURATION = 120
MAX_ATTEMPTS = 4


async def synthesize(story_text):
    communicate = edge_tts.Communicate(story_text, VOICE, rate=RATE)
    await communicate.save(AUDIO_FILE)


def get_audio_duration():
    clip = AudioFileClip(AUDIO_FILE)
    duration = clip.duration
    clip.close()
    return duration


def main():
    niche = random.choice(STORY_NICHES)
    word_target = 240  # initial guess, ~85s at +15% rate
    story_text = None
    duration = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        print(f"\n🔁 Attempt {attempt}/{MAX_ATTEMPTS} — target {word_target} words")
        story_text = generate_story(word_target=word_target, niche=niche)

        with open(STORY_FILE, "w", encoding="utf-8") as f:
            f.write(story_text)

        print(f"🎙️ Generating voiceover audio with voice '{VOICE}' at rate {RATE}...")
        asyncio.run(synthesize(story_text))

        duration = get_audio_duration()
        print(f"⏱️ Resulting audio duration: {duration:.1f}s")

        if MIN_DURATION <= duration <= MAX_DURATION:
            print("✅ Duration within 60-120s target — proceeding.")
            break

        # Adjust word target proportionally toward the 90s midpoint and retry
        scale = 90 / max(duration, 1)
        word_target = max(80, min(500, int(word_target * scale)))
        print(f"⚠️ Duration out of range. Adjusting target to {word_target} words and retrying...")
    else:
        print(f"⚠️ Reached max attempts — proceeding with last result ({duration:.1f}s), outside ideal range.")

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
    print(f"📏 Final story: {len(story_text.split())} words, {duration:.1f}s audio")


if __name__ == "__main__":
    main()
