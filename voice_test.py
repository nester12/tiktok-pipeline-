import os
import re
import subprocess
from pathlib import Path

import gdown
import torch
from melo.api import TTS
from openvoice import se_extractor
from openvoice.api import ToneColorConverter

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
BASE_WAV = Path("voice_base.wav")
OUTPUT_WAV = Path("voice_test_output.wav")
CHECKPOINT_DIR = Path("checkpoints_v2")


def run(*args):
    subprocess.run(list(args), check=True)


def google_drive_file_id(url):
    for pattern in (r"/file/d/([A-Za-z0-9_-]+)", r"[?&]id=([A-Za-z0-9_-]+)"):
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    raise ValueError("Could not extract a Google Drive file ID from VOICE_SOURCE_URL")


def download_source():
    print("Downloading permitted voice reference from Google Drive...")
    result = gdown.download(
        id=google_drive_file_id(VOICE_SOURCE_URL),
        output=str(SOURCE_VIDEO),
        quiet=False,
    )
    if not result or not SOURCE_VIDEO.exists() or SOURCE_VIDEO.stat().st_size == 0:
        raise RuntimeError("Voice reference download failed. Check the Google Drive sharing setting.")


def extract_reference():
    print("Extracting reference audio...")
    run(
        "ffmpeg", "-y", "-i", str(SOURCE_VIDEO),
        "-vn", "-ac", "1", "-ar", "24000",
        "-af", "loudnorm=I=-18:TP=-2:LRA=11",
        str(REFERENCE_WAV),
    )


def clone_voice():
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    converter_dir = CHECKPOINT_DIR / "converter"
    config_path = converter_dir / "config.json"
    checkpoint_path = converter_dir / "checkpoint.pth"

    if not config_path.exists() or not checkpoint_path.exists():
        raise RuntimeError("OpenVoice V2 checkpoints are missing from checkpoints_v2/converter")

    print(f"Loading OpenVoice V2 on {device}...")
    converter = ToneColorConverter(str(config_path), device=device)
    converter.load_ckpt(str(checkpoint_path))

    print("Extracting target speaker tone colour...")
    target_se, _ = se_extractor.get_se(
        str(REFERENCE_WAV), converter, vad=True
    )

    print("Generating natural English base speech with MeloTTS...")
    model = TTS(language="EN", device=device)
    speaker_ids = model.hps.data.spk2id
    preferred = next((name for name in speaker_ids if "EN-US" in name.upper()), None)
    if preferred is None:
        preferred = next(iter(speaker_ids))
    speaker_id = speaker_ids[preferred]
    model.tts_to_file(TEST_TEXT, speaker_id, str(BASE_WAV), speed=1.0)

    print(f"Converting base voice to permitted reference voice using {preferred}...")
    source_se = torch.load(
        CHECKPOINT_DIR / "base_speakers" / "ses" / f"{preferred.lower()}.pth",
        map_location=device,
    )
    converter.convert(
        audio_src_path=str(BASE_WAV),
        src_se=source_se,
        tgt_se=target_se,
        output_path=str(OUTPUT_WAV),
        message="@MyShell",
    )

    if not OUTPUT_WAV.exists() or OUTPUT_WAV.stat().st_size == 0:
        raise RuntimeError("OpenVoice did not create the cloned voice test.")
    print(f"Created {OUTPUT_WAV}")


def main():
    download_source()
    extract_reference()
    clone_voice()


if __name__ == "__main__":
    main()
