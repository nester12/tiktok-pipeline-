# -------------------------------------------------------------------
# Fetch background footage from a Google Drive file (public link),
# downloaded fresh via gdown each run. A random ~90s segment is
# sliced out so footage varies run to run even from one source file.
# -------------------------------------------------------------------
import os
import random
import subprocess
from moviepy.editor import VideoFileClip

DRIVE_FILE_ID = "1KGqdG2TwoTlrlzwmumV_91EJxnZ3T_Yh"
SOURCE_FILE = "bg_source.mp4"
OUTPUT_FILE = "background.mp4"

TARGET_DURATION = 130  # generous cushion above the 60-120s story length


def download_source_video():
    print(f"⬇️ Downloading source parkour footage from Google Drive...")
    subprocess.run(
        ["gdown", f"https://drive.google.com/uc?id={DRIVE_FILE_ID}", "-O", SOURCE_FILE],
        check=True
    )


def main():
    if not os.path.exists(SOURCE_FILE):
        download_source_video()

    clip = VideoFileClip(SOURCE_FILE)
    total_duration = clip.duration
    print(f"📼 Source video duration: {total_duration:.1f}s")

    if total_duration <= TARGET_DURATION:
        segment = clip
    else:
        max_start = total_duration - TARGET_DURATION
        start = random.uniform(0, max_start)
        print(f"🎲 Picking random segment starting at {start:.1f}s")
        segment = clip.subclip(start, start + TARGET_DURATION)

    segment.write_videofile(OUTPUT_FILE, fps=30, codec="libx264", audio=False, preset="fast")
    clip.close()

    print(f"\n✅ Background segment saved to '{OUTPUT_FILE}'")


if __name__ == "__main__":
    main()
