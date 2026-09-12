# -------------------------------------------------------------------
# Generate TTS Voiceover (Inworld Adam primary, Kokoro legacy fallback)
# -------------------------------------------------------------------

import base64
import json
import os
import shutil
import subprocess

import numpy as np
import requests
import soundfile as sf

from generate_story import generate_story

STORY_FILE = "story.txt"
RAW_AUDIO_FILE = "narration_raw.wav"
AUDIO_FILE = "narration.wav"
JSON_FILE = "timestamps.json"
TARGET_PACE_FILE = "target_pace.json"
AUDIO_META_FILE = "audio_meta.json"

INWORLD_API_BASE = "https://api.inworld.ai"
INWORLD_VOICE_NAME = os.environ.get("INWORLD_VOICE_NAME", "Adam")
INWORLD_VOICE_ID = os.environ.get("INWORLD_VOICE_ID", "").strip()
INWORLD_MODEL = os.environ.get("INWORLD_MODEL", "inworld-tts-2")

KOKORO_VOICE = os.environ.get("KOKORO_VOICE", "am_michael")
KOKORO_LANG = os.environ.get("KOKORO_LANG", "a")
KOKORO_SPEED = float(os.environ.get("KOKORO_SPEED", "1.0"))

# Defaults keep the production pipeline unchanged. Preview/test workflows can
# override these with environment variables without affecting normal runs.
TARGET_DURATION = float(os.environ.get("TARGET_DURATION", "90"))
MIN_DURATION = float(os.environ.get("MIN_DURATION", "65"))
MAX_SINGLE_DURATION = float(os.environ.get("MAX_SINGLE_DURATION", "119"))
MAX_STORY_RETRIES = int(os.environ.get("MAX_STORY_RETRIES", "2"))
SAMPLE_RATE = 24000
JOIN_PAUSE_MS = 45

_pipeline = None
_active_voice_name = None
_active_voice_id = None
_active_tts_provider = None


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
            candidate = data.get("target_wpm") or data.get("avg_wpm")
            if candidate and 115 <= float(candidate) <= 175:
                print(f"🎯 Using learned narration pace: {float(candidate):.0f} WPM")
                return float(candidate)
        except Exception as exc:
            print(f"⚠️ Could not read pacing data: {exc}")
    print(f"ℹ️ Using natural narrator target: {default_wpm:.0f} WPM")
    return default_wpm


def prepare_for_tts(text):
    """Keep the generated spoken punctuation intact for the TTS engine."""
    return " ".join(text.replace("\n", " ").split()).strip()


def resolve_inworld_voice_id(api_key):
    """Find the user's Inworld voice named Adam unless an explicit ID is supplied."""
    if INWORLD_VOICE_ID:
        print(f"🎙️ Using configured Inworld voice ID for {INWORLD_VOICE_NAME}.")
        return INWORLD_VOICE_ID

    response = requests.get(
        f"{INWORLD_API_BASE}/voices/v1/voices",
        headers={"Authorization": f"Basic {api_key}"},
        timeout=30,
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"Could not list Inworld voices (HTTP {response.status_code}): {response.text[:500]}"
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError("Inworld voice list returned invalid JSON.") from exc

    voices = payload.get("voices", []) if isinstance(payload, dict) else []
    target = INWORLD_VOICE_NAME.casefold().strip()

    exact_display_matches = []
    exact_id_matches = []
    for voice in voices:
        if not isinstance(voice, dict):
            continue
        voice_id = str(voice.get("voiceId") or voice.get("voice_id") or "").strip()
        display_name = str(
            voice.get("displayName")
            or voice.get("display_name")
            or voice.get("name")
            or ""
        ).strip()

        if display_name.casefold() == target and voice_id:
            exact_display_matches.append((voice_id, display_name))
        if voice_id.casefold() == target and voice_id:
            exact_id_matches.append((voice_id, display_name or voice_id))

    matches = exact_display_matches or exact_id_matches
    if not matches:
        visible_names = []
        for voice in voices[:40]:
            if isinstance(voice, dict):
                name = voice.get("displayName") or voice.get("display_name") or voice.get("name")
                if name:
                    visible_names.append(str(name))
        hint = ", ".join(visible_names[:20]) or "no voice names returned"
        raise RuntimeError(
            f"Inworld voice '{INWORLD_VOICE_NAME}' was not found in this API key's voice library. "
            f"Voices returned included: {hint}"
        )

    voice_id, display_name = matches[0]
    print(f"✅ Found Inworld voice '{display_name}' (voiceId={voice_id}).")
    return voice_id


def generate_inworld_voiceover(story_text, api_key):
    global _active_voice_name, _active_voice_id, _active_tts_provider

    spoken_text = prepare_for_tts(story_text)
    if len(spoken_text) > 1950:
        raise RuntimeError(
            f"Story is {len(spoken_text)} characters; Inworld single-request narration is limited to about 2000 characters."
        )

    voice_id = resolve_inworld_voice_id(api_key)
    print(f"🎙️ Inworld '{INWORLD_VOICE_NAME}' using {INWORLD_MODEL}...")

    response = requests.post(
        f"{INWORLD_API_BASE}/tts/v1/voice",
        headers={
            "Authorization": f"Basic {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "text": spoken_text,
            "voiceId": voice_id,
            "modelId": INWORLD_MODEL,
            "audioConfig": {
                "audioEncoding": "WAV",
                "sampleRateHertz": SAMPLE_RATE,
            },
        },
        timeout=90,
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"Inworld TTS failed (HTTP {response.status_code}): {response.text[:800]}"
        )

    try:
        data = response.json()
        encoded_audio = data["audioContent"]
        audio_bytes = base64.b64decode(encoded_audio)
    except Exception as exc:
        raise RuntimeError(f"Inworld returned unusable audio data: {response.text[:500]}") from exc

    if not audio_bytes:
        raise RuntimeError("Inworld returned empty audio.")

    with open(RAW_AUDIO_FILE, "wb") as f:
        f.write(audio_bytes)

    _active_voice_name = INWORLD_VOICE_NAME
    _active_voice_id = voice_id
    _active_tts_provider = "inworld"
    return get_duration(RAW_AUDIO_FILE)


def get_kokoro_pipeline():
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


def generate_kokoro_voiceover(story_text):
    global _active_voice_name, _active_voice_id, _active_tts_provider

    pipeline = get_kokoro_pipeline()
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
    _active_voice_name = KOKORO_VOICE
    _active_voice_id = KOKORO_VOICE
    _active_tts_provider = "kokoro"
    return get_duration(RAW_AUDIO_FILE)


def generate_raw_voiceover(story_text):
    """Use Inworld Adam whenever INWORLD_API_KEY is configured.

    If the user configured Inworld, do not silently switch to another voice on
    failure. A wrong narrator is worse than a visible workflow failure.
    """
    inworld_key = os.environ.get("INWORLD_API_KEY", "").strip()
    if inworld_key:
        return generate_inworld_voiceover(story_text, inworld_key)

    print("⚠️ INWORLD_API_KEY is not configured — using legacy Kokoro narration.")
    return generate_kokoro_voiceover(story_text)


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
    generate_raw_voiceover(story_text)
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
            "tts_provider": _active_tts_provider,
            "voice": _active_voice_name,
            "voice_id": _active_voice_id,
            "model": INWORLD_MODEL if _active_tts_provider == "inworld" else None,
            "target_duration": TARGET_DURATION,
            "complete_single_video": duration < 120,
        }, f, indent=2)


def main():
    ensure_ffmpeg()
    target_wpm = get_target_wpm()
    base_word_target = max(45, int(round(target_wpm * TARGET_DURATION / 60)))

    story_text = None
    duration = None
    measured_wpm = None

    for attempt in range(1, MAX_STORY_RETRIES + 1):
        word_target = base_word_target
        if attempt > 1 and duration:
            scale = TARGET_DURATION / max(duration, 1)
            word_target = int(round(len(story_text.split()) * scale))
            lower_bound = max(40, int(base_word_target * 0.65))
            upper_bound = max(lower_bound + 20, int(base_word_target * 1.45))
            word_target = max(lower_bound, min(upper_bound, word_target))

        print(f"\n🔁 Story/audio attempt {attempt}/{MAX_STORY_RETRIES} — target {word_target} words")
        story_text = generate_story(word_target=word_target, niche=None)
        with open(STORY_FILE, "w", encoding="utf-8") as f:
            f.write(story_text)

        duration, measured_wpm = synthesize_naturally(story_text)
        print(f"⏱️ Final audio duration: {duration:.1f}s")

        if MIN_DURATION <= duration <= MAX_SINGLE_DURATION:
            print("✅ Complete story fits the requested video length; keeping it unchanged.")
            break
        if duration < MIN_DURATION:
            print("⚠️ Story is too short for the requested format; requesting one longer version.")
        else:
            print("⚠️ Story is too long for the requested format; requesting one tighter version.")
    else:
        print("⚠️ Using the final natural narration after retry limit.")

    generate_word_timestamps(AUDIO_FILE)
    save_audio_meta(story_text, duration, measured_wpm)
    print(
        f"✅ Finished: {len(story_text.split())} words | {duration:.1f}s | "
        f"provider={_active_tts_provider} | voice={_active_voice_name}"
    )


if __name__ == "__main__":
    main()
