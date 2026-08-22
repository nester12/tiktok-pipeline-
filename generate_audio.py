# -------------------------------------------------------------------
# Generate TTS Voiceover (Chatterbox, MIT-licensed, commercial-safe)
# & Word Timestamps.
#
# Instead of relying purely on the AI to hit a target word count
# (unreliable — different models follow length instructions with
# very different accuracy), playback speed is calculated DYNAMICALLY
# based on how long the raw narration actually came out, so the
# final duration lands near the target on the first attempt
# regardless of word-count drift. A retry loop remains as a
# fallback only for extreme cases the speed adjustment can't fix
# without sounding unnatural.
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

VOICE_REFERENCE_PATH = os.environ.get("VOICE_REFERENCE_PATH")

EXAGGERATION = 0.6
CFG_WEIGHT = 0.4

TARGET_DURATION = 90    # fallback target if no real pacing data is available yet
MIN_DURATION = 60
MAX_DURATION = 120

# Keep playback speed within a range that always sounds natural, never
# rushed — lowered ceiling specifically so it never feels too fast
MIN_SPEED = 0.85
MAX_SPEED = 1.15

TARGET_PACE_FILE = "target_pace.json"
MAX_ATTEMPTS = 4


def get_target_wpm():
    """Uses the measured words-per-minute pace from real successful
    reference videos (via fetch_style_examples.py) if available,
    otherwise falls back to a reasonable default."""
    default_wpm = 140  # a natural, unhurried storytelling pace
    if os.path.exists(TARGET_PACE_FILE):
        try:
            with open(TARGET_PACE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            wpm = data.get("avg_wpm")
            if wpm and 60 <= wpm <= 220:
                print(f"🎯 Using measured pace from reference videos: {wpm} WPM "
                      f"(sample size: {data.get('sample_size', '?')})")
                return wpm
        except Exception as e:
            print(f"⚠️ Could not read {TARGET_PACE_FILE}: {e}")
    print(f"ℹ️ No reference pacing data yet — using default {default_wpm} WPM.")
    return default_wpm

_model = None


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
    """Time-stretches audio while preserving pitch, using ffmpeg's atempo filter."""
    subprocess.run(
        ["ffmpeg", "-y", "-i", input_path, "-filter:a", f"atempo={factor}", output_path],
        check=True, capture_output=True
    )


def get_duration(path):
    clip = AudioFileClip(path)
    duration = clip.duration
    clip.close()
    return duration


def synthesize_with_dynamic_speed(story_text, target_wpm):
    """Generates raw narration, then computes the speed needed so the
    narration matches the target words-per-minute pace (measured from
    real successful reference videos when available), clamped to a
    natural-sounding range."""
    model = get_model()
    kwargs = {"exaggeration": EXAGGERATION, "cfg_weight": CFG_WEIGHT}
    if VOICE_REFERENCE_PATH and os.path.exists(VOICE_REFERENCE_PATH):
        kwargs["audio_prompt_path"] = VOICE_REFERENCE_PATH

    wav = model.generate(story_text, **kwargs)
    ta.save(RAW_AUDIO_FILE, wav, model.sr)

    raw_duration = get_duration(RAW_AUDIO_FILE)
    word_count = len(story_text.split())
    raw_wpm = (word_count / raw_duration) * 60 if raw_duration > 0 else 0

    needed_speed = raw_wpm / target_wpm if raw_wpm > 0 else 1.0
    clamped_speed = max(MIN_SPEED, min(MAX_SPEED, needed_speed))

    print(f"📏 Raw narration: {raw_duration:.1f}s, {word_count} words ({raw_wpm:.0f} WPM) "
          f"→ target {target_wpm} WPM needs {needed_speed:.2f}x, "
          f"using {clamped_speed:.2f}x (clamped to {MIN_SPEED}-{MAX_SPEED})")

    speed_up_audio(RAW_AUDIO_FILE, AUDIO_FILE, clamped_speed)
    final_duration = get_duration(AUDIO_FILE)

    return final_duration, clamped_speed, raw_duration


def main():
    niche = random.choice(STORY_NICHES)
    word_target = 205
    target_wpm = get_target_wpm()
    story_text = None
    duration = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        print(f"\n🔁 Attempt {attempt}/{MAX_ATTEMPTS} — target {word_target} words")
        story_text = generate_story(word_target=word_target, niche=niche)

        with open(STORY_FILE, "w", encoding="utf-8") as f:
            f.write(story_text)

        print("🎙️ Generating voiceover with Chatterbox TTS...")
        duration, speed_used, raw_duration = synthesize_with_dynamic_speed(story_text, target_wpm)
        print(f"⏱️ Final audio duration: {duration:.1f}s (speed {speed_used:.2f}x)")

        if MIN_DURATION <= duration <= MAX_DURATION:
            print("✅ Duration within 60-120s target — proceeding.")
            break

        scale = TARGET_DURATION / max(raw_duration, 1)
        word_target = max(80, min(600, int(word_target * scale)))
        print(f"⚠️ Duration still out of range even after speed adjustment. "
              f"Adjusting target to {word_target} words and retrying...")
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
