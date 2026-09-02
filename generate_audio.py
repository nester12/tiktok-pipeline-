# -------------------------------------------------------------------
# Generate TTS Voiceover (Chatterbox)
# -------------------------------------------------------------------

import json
import os
import random
import re
import shutil
import subprocess

import torch
import torchaudio as ta

from generate_story import STORY_NICHES, generate_story


STORY_FILE = "story.txt"
RAW_AUDIO_FILE = "narration_raw.wav"
AUDIO_FILE = "narration.wav"
JSON_FILE = "timestamps.json"

VOICE_REFERENCE_PATH = os.environ.get("VOICE_REFERENCE_PATH")

EXAGGERATION = 0.6
CFG_WEIGHT = 0.4

TARGET_DURATION = 90
MIN_DURATION = 60
MAX_DURATION = 120

MIN_SPEED = 0.85
MAX_SPEED = 1.15

TARGET_PACE_FILE = "target_pace.json"
MAX_ATTEMPTS = 4

# IMPORTANT:
# Long stories must NOT be sent to Chatterbox in one request.
MAX_CHUNK_CHARS = 300
MAX_CHUNK_WORDS = 45

# Pause between generated pieces
CHUNK_PAUSE_MS = 180

_model = None


def get_target_wpm():

    default_wpm = 140

    if os.path.exists(TARGET_PACE_FILE):

        try:

            with open(
                TARGET_PACE_FILE,
                "r",
                encoding="utf-8"
            ) as f:

                data = json.load(f)

            wpm = data.get("avg_wpm")

            if wpm and 60 <= wpm <= 220:

                print(
                    f"🎯 Using measured pace: "
                    f"{wpm} WPM"
                )

                return float(wpm)

        except Exception as exc:

            print(
                f"⚠️ Could not read pacing data: "
                f"{exc}"
            )

    print(
        f"ℹ️ No reference pacing data yet — "
        f"using default {default_wpm} WPM."
    )

    return float(default_wpm)


def get_device():

    if torch.cuda.is_available():
        return "cuda"

    if (
        hasattr(torch.backends, "mps")
        and torch.backends.mps.is_available()
    ):
        return "mps"

    return "cpu"


def get_model():

    global _model

    if _model is not None:
        return _model

    try:

        from chatterbox.tts import ChatterboxTTS

    except ImportError as exc:

        raise RuntimeError(
            "Chatterbox TTS is not installed."
        ) from exc

    hf_token = os.environ.get("HF_TOKEN")

    if hf_token:

        try:

            from huggingface_hub import login

            login(
                token=hf_token,
                add_to_git_credential=False
            )

        except Exception as exc:

            print(
                f"⚠️ Hugging Face login warning: "
                f"{exc}"
            )

    device = get_device()

    print(
        f"📦 Loading Chatterbox TTS model "
        f"({device.upper()})..."
    )

    _model = ChatterboxTTS.from_pretrained(
        device=device
    )

    return _model


def ensure_ffmpeg():

    if not shutil.which("ffmpeg"):

        raise RuntimeError(
            "ffmpeg was not found."
        )

    if not shutil.which("ffprobe"):

        raise RuntimeError(
            "ffprobe was not found."
        )


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
            path
        ],
        check=True,
        capture_output=True,
        text=True
    )

    return float(
        result.stdout.strip()
    )


def speed_up_audio(
    input_path,
    output_path,
    factor
):

    ensure_ffmpeg()

    factor = float(factor)

    factor = max(
        0.5,
        min(2.0, factor)
    )

    try:

        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-i",
                input_path,
                "-filter:a",
                f"atempo={factor:.6f}",
                output_path
            ],
            check=True,
            capture_output=True,
            text=True
        )

    except subprocess.CalledProcessError as exc:

        raise RuntimeError(
            "FFmpeg failed to adjust "
            f"voice speed: {exc.stderr}"
        ) from exc


def split_long_piece(text):

    """
    Handles a sentence that is itself too large.
    """

    pieces = re.split(
        r"(?<=[,;:])\s+",
        text
    )

    chunks = []
    current = ""

    for piece in pieces:

        piece = piece.strip()

        if not piece:
            continue

        candidate = (
            f"{current} {piece}".strip()
            if current
            else piece
        )

        if (
            len(candidate) > MAX_CHUNK_CHARS
            or
            len(candidate.split()) > MAX_CHUNK_WORDS
        ):

            if current:
                chunks.append(current)

            current = piece

        else:

            current = candidate

        # Emergency fallback for extremely
        # long text with no punctuation.
        if (
            len(current) > MAX_CHUNK_CHARS
            or
            len(current.split()) > MAX_CHUNK_WORDS
        ):

            words = current.split()

            while len(words) > MAX_CHUNK_WORDS:

                chunk = " ".join(
                    words[:MAX_CHUNK_WORDS]
                )

                chunks.append(chunk)

                words = words[
                    MAX_CHUNK_WORDS:
                ]

            current = " ".join(words)

    if current:
        chunks.append(current)

    return chunks


def split_story_for_tts(text):

    """
    Break the complete story into safe
    Chatterbox requests.

    Sentence boundaries are preferred so
    narration still sounds natural.
    """

    text = re.sub(
        r"\s+",
        " ",
        text
    ).strip()

    if not text:

        raise ValueError(
            "Story text is empty."
        )

    sentences = re.split(
        r"(?<=[.!?])\s+",
        text
    )

    chunks = []
    current = ""

    for sentence in sentences:

        sentence = sentence.strip()

        if not sentence:
            continue

        # Sentence itself is too large.
        if (
            len(sentence) > MAX_CHUNK_CHARS
            or
            len(sentence.split()) > MAX_CHUNK_WORDS
        ):

            if current:

                chunks.append(current)
                current = ""

            chunks.extend(
                split_long_piece(sentence)
            )

            continue

        candidate = (
            f"{current} {sentence}".strip()
            if current
            else sentence
        )

        if (
            len(candidate) <= MAX_CHUNK_CHARS
            and
            len(candidate.split()) <= MAX_CHUNK_WORDS
        ):

            current = candidate

        else:

            if current:
                chunks.append(current)

            current = sentence

    if current:
        chunks.append(current)

    return chunks


def normalise_waveform(wav):

    if not isinstance(
        wav,
        torch.Tensor
    ):

        wav = torch.as_tensor(wav)

    wav = (
        wav
        .detach()
        .float()
        .cpu()
    )

    if wav.ndim == 1:

        wav = wav.unsqueeze(0)

    elif wav.ndim > 2:

        wav = wav.squeeze()

        if wav.ndim == 1:
            wav = wav.unsqueeze(0)

    if wav.ndim != 2:

        raise RuntimeError(
            "Unexpected Chatterbox "
            f"audio shape: {wav.shape}"
        )

    return wav


def generate_raw_voiceover(
    story_text
):

    model = get_model()

    chunks = split_story_for_tts(
        story_text
    )

    print(
        f"🧩 Story split into "
        f"{len(chunks)} voice chunks."
    )

    kwargs = {
        "exaggeration": EXAGGERATION,
        "cfg_weight": CFG_WEIGHT
    }

    if VOICE_REFERENCE_PATH:

        if os.path.exists(
            VOICE_REFERENCE_PATH
        ):

            kwargs[
                "audio_prompt_path"
            ] = VOICE_REFERENCE_PATH

            print(
                "🗣️ Using reference voice."
            )

        else:

            print(
                "⚠️ Voice reference file "
                "not found. Using default voice."
            )

    audio_parts = []

    pause_samples = int(
        model.sr
        *
        CHUNK_PAUSE_MS
        /
        1000
    )

    for index, chunk in enumerate(
        chunks,
        start=1
    ):

        print(
            f"🎙️ Generating chunk "
            f"{index}/{len(chunks)} "
            f"({len(chunk.split())} words)"
        )

        try:

            wav = model.generate(
                chunk,
                **kwargs
            )

        except IndexError as exc:

            raise RuntimeError(
                "\n❌ Chatterbox text limit "
                f"was reached on chunk {index}.\n"
                f"Chunk words: "
                f"{len(chunk.split())}\n"
                f"Chunk characters: "
                f"{len(chunk)}\n"
                f"Text: {chunk[:150]}..."
            ) from exc

        except Exception as exc:

            raise RuntimeError(
                "❌ Chatterbox failed on "
                f"chunk {index}/{len(chunks)}: "
                f"{exc}"
            ) from exc

        wav = normalise_waveform(wav)

        audio_parts.append(wav)

        if index < len(chunks):

            pause = torch.zeros(
                (
                    wav.shape[0],
                    pause_samples
                ),
                dtype=wav.dtype
            )

            audio_parts.append(pause)

    if not audio_parts:

        raise RuntimeError(
            "No voice audio was generated."
        )

    full_wav = torch.cat(
        audio_parts,
        dim=1
    )

    ta.save(
        RAW_AUDIO_FILE,
        full_wav,
        model.sr
    )

    return get_duration(
        RAW_AUDIO_FILE
    )


def synthesize_with_dynamic_speed(
    story_text,
    target_wpm
):

    raw_duration = (
        generate_raw_voiceover(
            story_text
        )
    )

    word_count = len(
        story_text.split()
    )

    if raw_duration <= 0:

        raise RuntimeError(
            "Generated audio has "
            "invalid duration."
        )

    raw_wpm = (
        word_count
        /
        raw_duration
        *
        60
    )

    # Example:
    # raw = 120 WPM
    # target = 140 WPM
    # speed needed = 140 / 120
    needed_speed = (
        target_wpm
        /
        raw_wpm
    )

    speed_used = max(
        MIN_SPEED,
        min(
            MAX_SPEED,
            needed_speed
        )
    )

    print(
        f"📏 Raw voice: "
        f"{raw_duration:.1f}s | "
        f"{raw_wpm:.0f} WPM"
    )

    print(
        f"🎚️ Speed adjustment: "
        f"{speed_used:.2f}x"
    )

    speed_up_audio(
        RAW_AUDIO_FILE,
        AUDIO_FILE,
        speed_used
    )

    final_duration = get_duration(
        AUDIO_FILE
    )

    return (
        final_duration,
        speed_used,
        raw_duration
    )


def generate_word_timestamps(
    audio_path
):

    try:

        import whisper

    except ImportError as exc:

        raise RuntimeError(
            "Whisper is not installed."
        ) from exc

    print(
        "⏳ Creating word timestamps..."
    )

    model = whisper.load_model(
        "tiny"
    )

    result = model.transcribe(
        audio_path,
        word_timestamps=True
    )

    timestamps = []

    for segment in result.get(
        "segments",
        []
    ):

        for word_info in segment.get(
            "words",
            []
        ):

            timestamps.append(
                {
                    "word":
                    word_info[
                        "word"
                    ].strip(),

                    "start":
                    round(
                        float(
                            word_info[
                                "start"
                            ]
                        ),
                        2
                    ),

                    "end":
                    round(
                        float(
                            word_info[
                                "end"
                            ]
                        ),
                        2
                    )
                }
            )

    with open(
        JSON_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            timestamps,
            f,
            indent=2
        )

    print(
        f"✅ Created "
        f"{len(timestamps)} "
        f"word timestamps."
    )


def main():

    ensure_ffmpeg()

    niche = random.choice(
        STORY_NICHES
    )

    word_target = 205

    target_wpm = (
        get_target_wpm()
    )

    story_text = None
    duration = None

    for attempt in range(
        1,
        MAX_ATTEMPTS + 1
    ):

        print(
            f"\n🔁 Attempt "
            f"{attempt}/"
            f"{MAX_ATTEMPTS}"
            f" — target "
            f"{word_target} words"
        )

        story_text = generate_story(
            word_target=word_target,
            niche=niche
        )

        with open(
            STORY_FILE,
            "w",
            encoding="utf-8"
        ) as f:

            f.write(story_text)

        print(
            "🎙️ Generating voiceover "
            "with Chatterbox TTS..."
        )

        (
            duration,
            speed_used,
            raw_duration
        ) = synthesize_with_dynamic_speed(
            story_text,
            target_wpm
        )

        print(
            f"⏱️ Final audio duration: "
            f"{duration:.1f}s"
        )

        if (
            MIN_DURATION
            <= duration
            <= MAX_DURATION
        ):

            print(
                "✅ Audio duration accepted."
            )

            break

        scale = (
            TARGET_DURATION
            /
            max(duration, 1)
        )

        word_target = int(
            round(
                word_target
                *
                scale
            )
        )

        word_target = max(
            80,
            min(
                600,
                word_target
            )
        )

        print(
            "⚠️ Adjusting story "
            f"target to "
            f"{word_target} words."
        )

    else:

        print(
            "⚠️ Maximum attempts "
            "reached. Using last result."
        )

    generate_word_timestamps(
        AUDIO_FILE
    )

    print(
        f"✅ Finished: "
        f"{len(story_text.split())} "
        f"words | "
        f"{duration:.1f}s"
    )


if __name__ == "__main__":
    main()
