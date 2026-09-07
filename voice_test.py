import os
import re
import subprocess
from pathlib import Path

import gdown

# Separate voice-cloning test pipeline. It does not modify the production TikTok pipeline.
VOICE_SOURCE_URL = os.environ.get(
    "VOICE_SOURCE_URL",
    "https://drive.google.com/file/d/154LMIYT2ocStkSafa8SM8mSrbsVcpxm3/view?usp=sharing",
)
TEST_TEXT = os.environ.get(
    "VOICE_TEST_TEXT",
    "I thought it was going to be an ordinary day, but one small detail changed everything.",
)

SOURCE_VIDEO = Path("voice_source.mp4")
REFERENCE_WAV = Path("voice_reference.wav")
OUTPUT_WAV = Path("voice_test_output.wav")


def run(*args):
    subprocess.run(list(args), check=True)


def google_drive_file_id(url):
    patterns = [
        r"/file/d/([A-Za-z0-9_-]+)",
        r"[?&]id=([A-Za-z0-9_-]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    raise ValueError("Could not extract a Google Drive file ID from VOICE_SOURCE_URL")


def download_source():
    print("Downloading permitted voice reference from Google Drive...")
    file_id = google_drive_file_id(VOICE_SOURCE_URL)
    result = gdown.download(id=file_id, output=str(SOURCE_VIDEO), quiet=False)
    if not result or not SOURCE_VIDEO.exists() or SOURCE_VIDEO.stat().st_size == 0:
        raise RuntimeError(
            "Voice reference download failed. Make sure the Google Drive file is shared as Anyone with the link."
        )


def extract_reference():
    print("Extracting and normalizing reference audio...")
    run(
        "ffmpeg", "-y", "-i", str(SOURCE_VIDEO),
        "-vn", "-ac", "1", "-ar", "24000",
        "-af", "loudnorm=I=-18:TP=-2:LRA=11",
        str(REFERENCE_WAV),
    )


def clone_voice():
    print("Loading XTTS v2...")
    from TTS.api import TTS

    tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2", gpu=False)
    print("Generating voice-clone test...")
    tts.tts_to_file(
        text=TEST_TEXT,
        speaker_wav=str(REFERENCE_WAV),
        language="en",
        file_path=str(OUTPUT_WAV),
    )
    if not OUTPUT_WAV.exists() or OUTPUT_WAV.stat().st_size == 0:
        raise RuntimeError("XTTS did not create the test audio.")
    print(f"Created {OUTPUT_WAV}")


def main():
    download_source()
    extract_reference()
    clone_voice()


if __name__ == "__main__":
    main()
