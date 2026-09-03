# -------------------------------------------------------------------
# Generate TTS Voiceover (Kokoro)
# -------------------------------------------------------------------

import json
import os
import shutil
import subprocess

import numpy as np
import soundfile as sf

from generate_story import generate_story

STORY_FILE = "story.txt"
RAW_AUDIO_FILE = "narration_raw.wav"
AUDIO_FILE = "narration.wav"
JSON_FILE = "timestamps.json"
TARGET_PACE_FILE = "target_pace.json"
AUDIO_META_FILE = "audio_meta.json"

KOKORO_VOICE = os.environ.get("KOKORO_VOICE", "am_michael")
KOKORO_LANG = os.environ.get("KOKORO_LANG", "a")
KOKORO_SPEED = float(os.environ.get("KOKORO_SPEED", "1.0"))

# Aim around 90 seconds, but preserve a complete story when it naturally lands
# anywhere in this range. A 90-second story should not be regenerated merely
# to hit an exact duration.
TARGET_DURATION = 90
MIN_DURATION = 65
MAX_SINGLE_DURATION = 119
MAX_STORY_RETRIES = 2
SAMPLE_RATE = 24000
JOIN_PAUSE_MS = 45

_pipeline = None


def ensure_ffmpeg():
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg was not found.")
    if not shutil.which("ffprobe"):
        raise RuntimeError("ffprobe was not found.")


def get_duration(path):
    ensure_ffmpeg()
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", path,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip())


def get_target_wpm():
    default_wpm = 145.0
    if os.path.exists(TARGET_PACE_FILE):
        try:
            with open(TARGET_PACE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            # median is more resistant to unusually fast viral clips than avg.
            candidate = data.get("target_wpm") or data.get("avg_wpm")
            if candidate and 115 <= float(candidate) <= 175:
                print(f"🎯 Using learned narration pace: {float(candidate):.0f} WPM")
                return float(candidate)
        except Exception as exc:
            print(f"⚠️ Could not read pacing data: {exc}")
    print(f"ℹ️ Using natural narrator target: {default_wpm:.0f} WPM")
    return default_wpm


def get_pipeline():
    global _pipeline
    if _pipeline is not None:
        return _pipeline
    try:
        from kokoro import KPipeline
    except ImportError as exc:
        raise RuntimeError("Kokoro TTS is not installed. Run pip install -r requirements.txt.") from exc
    print(f"📦 Loading Kokoro TTS ({KOKORO_VOICE})...")
    _pipeline = KPipeline(lang_code=KOKORO_LANG)
    return _pipeline


def _to_numpy(audio):
    if audio is None:
        return None
    if hasattr(audio, "detach"):
        audio = audio.detach().cpu().numpy()
    audio = np.asarray(audio, dtype=np.float32).squeeze()
    if audio.ndim != 1:
        audio = audio.reshape(-1)
    return audio


def prepare_for_tts(text):
    """Light cleanup only; keep the author's punctuation/prosody intact."""
    text = " ".join(text.replace("\n", " ").split())
    text = text.replace("...", "…")
    return text.strip()


def generate_raw_voiceover(story_text):
    pipeline = get_pipeline()
    spoken_text = prepare_for_tts(story_text)
    print(f"🎙️ Kokoro '{KOKORO_VOICE}' at {KOKORO_SPEED:.2f}x...")

    audio_parts = []
    pause = np.zeros(int(SAMPLE_RATE * JOIN_PAUSE_MS / 1000), dtype=np.float32)

    try:
        generator = pipeline(spoken_text, voice=KOKORO_VOICE, speed=KOKORO_SPEED)
        for index, result in enumerate(generator, start=1):
            audio = getattr(result, "audio", None)
            if audio is None:
                try:
                    audio = result[2]
                except Exception:
                    audio = None
            audio = _to_numpy(audio)
            if audio is None or audio.size == 0:
                continue
            if audio_parts:
                audio_parts.append(pause)
            audio_parts.append(audio)
            print(f"  ✓ voice segment {index}")
    except Exception as exc:
        raise RuntimeError(f"Kokoro failed while generating voice '{KOKORO_VOICE}': {exc}") from exc

    if not audio_parts:
        raise RuntimeError("Kokoro returned no usable voice audio.")

    full_audio = np.concatenate(audio_parts)
    sf.write(RAW_AUDIO_FILE, full_audio, SAMPLE_RATE)
    return get_duration(RAW_AUDIO_FILE)


def master_audio(input_path, output_path):
    """Normalize loudness without changing pitch, speed or story timing."""
    ensure_ffmpeg()
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-loglevel", "error", "-i", input_path,
                "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", output_path,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"FFmpeg failed while mastering narration: {exc.stderr}") from exc


def synthesize_naturally(story_text):
    raw_duration = generate_raw_voiceover(story_text)
    master_audio(RAW_AUDIO_FILE, AUDIO_FILE)
    final_duration = get_duration(AUDIO_FILE)
    word_count = len(story_text.split())
    natural_wpm = word_count / max(final_duration, 0.1) * 60
    print(f"📏 Natural voice: {final_duration:.1f}s | {natural_wpm:.0f} WPM")
    return final_duration, natural_wpm


def generate_word_timestamps(audio_path):
    try:
        import whisper
    except ImportError as exc:
        raise RuntimeError("Whisper is not installed.") from exc

    print("⏳ Creating word timestamps...")
    model = whisper.load_model("tiny")
    result = model.transcribe(audio_path, word_timestamps=True)

    timestamps = []
    for segment in result.get("segments", []):
        for word_info in segment.get("words", []):
            word = word_info.get("word", "").strip()
            if not word:
                continue
            timestamps.append({
                "word": word,
                "start": round(float(word_info["start"]), 2),
                "end": round(float(word_info["end"]), 2),
            })

    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(timestamps, f, indent=2)
    print(f"✅ Created {len(timestamps)} word timestamps.")


def save_audio_meta(story_text, duration, measured_wpm):
    with open(AUDIO_META_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "duration_seconds": round(duration, 2),
            "word_count": len(story_text.split()),
            "measured_wpm": round(measured_wpm, 1),
            "voice": KOKORO_VOICE,
            "speed": KOKORO_SPEED,
            "complete_single_video": duration < 120,
        }, f, indent=2)


def main():
    ensure_ffmpeg()
    target_wpm = get_target_wpm()
    base_word_target = int(round(target_wpm * TARGET_DURATION / 60))

    story_text = None
    duration = None
    measured_wpm = None

    # Generate a story once and preserve it whenever it is a complete 65-119s
    # narration. Only retry generation if it is actually too short/long.
    for attempt in range(1, MAX_STORY_RETRIES + 1):
        word_target = base_word_target
        if attempt > 1 and duration:
            scale = TARGET_DURATION / max(duration, 1)
            word_target = int(round(len(story_text.split()) * scale))
            word_target = max(170, min(330, word_target))

        print(f"\n🔁 Story/audio attempt {attempt}/{MAX_STORY_RETRIES} — target {word_target} words")
        story_text = generate_story(word_target=word_target, niche=None)
        with open(STORY_FILE, "w", encoding="utf-8") as f:
            f.write(story_text)

        duration, measured_wpm = synthesize_naturally(story_text)
        print(f"⏱️ Final audio duration: {duration:.1f}s")

        if MIN_DURATION <= duration <= MAX_SINGLE_DURATION:
            print("✅ Complete story fits a single video; keeping it unchanged.")
            break
        if duration < MIN_DURATION:
            print("⚠️ Story is too short for the target format; requesting one longer version.")
        else:
            print("⚠️ Story exceeds two minutes; requesting one tighter version rather than speeding the voice.")
    else:
        print("⚠️ Using the final natural narration after retry limit.")

    generate_word_timestamps(AUDIO_FILE)
    save_audio_meta(story_text, duration, measured_wpm)
    print(f"✅ Finished: {len(story_text.split())} words | {duration:.1f}s | voice={KOKORO_VOICE}")


if __name__ == "__main__":
    main()
