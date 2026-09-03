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

# Natural male narrator. Change this through a GitHub Actions env var if
# another Kokoro voice is preferred (for example: am_adam or am_onyx).
KOKORO_VOICE = os.environ.get("KOKORO_VOICE", "am_michael")
KOKORO_LANG = os.environ.get("KOKORO_LANG", "a")
KOKORO_SPEED = float(os.environ.get("KOKORO_SPEED", "1.0"))

TARGET_DURATION = 90
MIN_DURATION = 65
MAX_DURATION = 120
MAX_ATTEMPTS = 4
SAMPLE_RATE = 24000

# A very short join gap prevents clipped joins without creating the obvious
# stop/start sound the old Chatterbox chunking produced.
JOIN_PAUSE_MS = 55

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
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            path,
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

            wpm = data.get("avg_wpm")
            if wpm and 100 <= float(wpm) <= 190:
                print(f"🎯 Using measured story pace: {float(wpm):.0f} WPM")
                return float(wpm)
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
        raise RuntimeError(
            "Kokoro TTS is not installed. Run pip install -r requirements.txt."
        ) from exc

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


def generate_raw_voiceover(story_text):
    pipeline = get_pipeline()

    print(
        f"🎙️ Generating natural narration with Kokoro voice "
        f"'{KOKORO_VOICE}' at {KOKORO_SPEED:.2f}x..."
    )

    audio_parts = []
    pause = np.zeros(
        int(SAMPLE_RATE * JOIN_PAUSE_MS / 1000),
        dtype=np.float32,
    )

    try:
        generator = pipeline(
            story_text,
            voice=KOKORO_VOICE,
            speed=KOKORO_SPEED,
        )

        for index, result in enumerate(generator, start=1):
            # Kokoro Result objects expose .audio; tuple-style output is kept
            # for compatibility with versions that still implement it.
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
        raise RuntimeError(
            f"Kokoro failed while generating voice '{KOKORO_VOICE}': {exc}"
        ) from exc

    if not audio_parts:
        raise RuntimeError("Kokoro returned no usable voice audio.")

    full_audio = np.concatenate(audio_parts)
    sf.write(RAW_AUDIO_FILE, full_audio, SAMPLE_RATE)
    return get_duration(RAW_AUDIO_FILE)


def master_audio(input_path, output_path):
    """Normalize loudness without changing the voice's pitch or timing."""
    ensure_ffmpeg()

    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-i",
                input_path,
                "-af",
                "loudnorm=I=-16:TP=-1.5:LRA=11",
                output_path,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"FFmpeg failed while mastering narration: {exc.stderr}"
        ) from exc


def synthesize_naturally(story_text):
    raw_duration = generate_raw_voiceover(story_text)

    # Important: unlike the old system, do NOT stretch/compress the finished
    # voice with atempo. That processing was one of the reasons narration
    # sounded artificial. Kokoro generates at the desired speaking speed.
    master_audio(RAW_AUDIO_FILE, AUDIO_FILE)
    final_duration = get_duration(AUDIO_FILE)

    word_count = len(story_text.split())
    natural_wpm = word_count / max(final_duration, 0.1) * 60

    print(
        f"📏 Natural voice: {final_duration:.1f}s | "
        f"{natural_wpm:.0f} WPM"
    )

    return final_duration, raw_duration


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
            timestamps.append(
                {
                    "word": word_info["word"].strip(),
                    "start": round(float(word_info["start"]), 2),
                    "end": round(float(word_info["end"]), 2),
                }
            )

    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(timestamps, f, indent=2)

    print(f"✅ Created {len(timestamps)} word timestamps.")


def main():
    ensure_ffmpeg()

    target_wpm = get_target_wpm()
    word_target = int(round(target_wpm * TARGET_DURATION / 60))

    story_text = None
    duration = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        print(
            f"\n🔁 Attempt {attempt}/{MAX_ATTEMPTS} "
            f"— target {word_target} words"
        )

        # Passing niche=None allows generate_story.py to use its own current
        # trend-selection logic instead of this audio module choosing randomly.
        story_text = generate_story(
            word_target=word_target,
            niche=None,
        )

        with open(STORY_FILE, "w", encoding="utf-8") as f:
            f.write(story_text)

        duration, _ = synthesize_naturally(story_text)
        print(f"⏱️ Final audio duration: {duration:.1f}s")

        if MIN_DURATION <= duration <= MAX_DURATION:
            print("✅ Audio duration accepted.")
            break

        scale = TARGET_DURATION / max(duration, 1)
        word_target = int(round(word_target * scale))
        word_target = max(100, min(500, word_target))

        print(f"⚠️ Adjusting story target to {word_target} words.")
    else:
        print("⚠️ Maximum attempts reached. Using last result.")

    generate_word_timestamps(AUDIO_FILE)

    print(
        f"✅ Finished with Kokoro '{KOKORO_VOICE}': "
        f"{len(story_text.split())} words | {duration:.1f}s"
    )


if __name__ == "__main__":
    main()
