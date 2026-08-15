# -------------------------------------------------------------------
# Generate TTS Voiceover (Chatterbox, MIT-licensed, commercial-safe)
# & Word Timestamps. Includes an automatic retry loop that
# regenerates the story with an adjusted length until the final
# audio lands between 60-120s.
# -------------------------------------------------------------------
import os
import json
import subprocess
import whisper
import torchaudio as ta
from chatterbox.tts import ChatterboxTTS
from moviepy.editor import AudioFileClip

from generate_story import generate_story, STORY_NICHES
import random

STORY_FILE = "story.txt"
RAW_AUDIO_FILE = "narration_raw.wav"
AUDIO_FILE = "narration.wav"
JSON_FILE = "timestamps.json"

# Optional: path to a reference voice clip for cloning (6-10s of clean audio).
# Leave unset to use Chatterbox's default voice.
VOICE_REFERENCE_PATH = os.environ.get("VOICE_REFERENCE_PATH")

# Emotion intensity — Chatterbox's expressive-narration dial (0.0-1.0+)
EXAGGERATION = 0.6
CFG_WEIGHT = 0.4

# Playback speed multiplier, applied after generation via ffmpeg's
# pitch-preserving time-stretch (Chatterbox has no native rate control)
SPEED_FACTOR = 1.15

MIN_DURATION = 60
MAX_DURATION = 120
MAX_ATTEMPTS = 4

_model = None  # loaded once, reused across retry attempts in the same run


def get_model():
    global _model
    if _model is None:
        hf_token = os.environ.get("HF_TOKEN")
        if hf_token:
            from huggingface_hub import login
            login(token=hf_token)

        print("📦 Loading Chatterbox TTS model (CPU)...")
        _model = ChatterboxTTS.from_pretrained(device="cpu")
    return _model


def speed_up_audio(input_path, output_path, factor):
    """Speeds up audio while preserving pitch, using ffmpeg's atempo filter.
    atempo only accepts 0.5-2.0 per instance, which covers our use case fine."""
    subprocess.run(
        ["ffmpeg", "-y", "-i", input_path, "-filter:a", f"atempo={factor}", output_path],
        check=True, capture_output=True
    )


def synthesize(story_text):
    model = get_model()
    kwargs = {"exaggeration": EXAGGERATION, "cfg_weight": CFG_WEIGHT}
    if VOICE_REFERENCE_PATH and os.path.exists(VOICE_REFERENCE_PATH):
        kwargs["audio_prompt_path"] = VOICE_REFERENCE_PATH

    wav = model.generate(story_text, **kwargs)
    ta.save(RAW_AUDIO_FILE, wav, model.sr)

    print(f"⏩ Speeding up audio {SPEED_FACTOR}x (pitch-preserving)...")
    speed_up_audio(RAW_AUDIO_FILE, AUDIO_FILE, SPEED_FACTOR)


def get_audio_duration():
    clip = AudioFileClip(AUDIO_FILE)
    duration = clip.duration
    clip.close()
    return duration


def main():
    niche = random.choice(STORY_NICHES)
    word_target = 205  # initial guess for ~85s at 1.15x playback speed
    story_text = None
    duration = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        print(f"\n🔁 Attempt {attempt}/{MAX_ATTEMPTS} — target {word_target} words")
        story_text = generate_story(word_target=word_target, niche=niche)

        with open(STORY_FILE, "w", encoding="utf-8") as f:
            f.write(story_text)

        print("🎙️ Generating voiceover with Chatterbox TTS...")
        synthesize(story_text)

        duration = get_audio_duration()
        print(f"⏱️ Resulting audio duration: {duration:.1f}s")

        if MIN_DURATION <= duration <= MAX_DURATION:
            print("✅ Duration within 60-120s target — proceeding.")
            break

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
