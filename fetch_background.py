# -------------------------------------------------------------------
# Fetch background footage from a specific CC BY 4.0 licensed
# Minecraft parkour video, downloaded fresh via yt-dlp each run.
# A random ~90s segment is sliced out so footage varies run to run.
#
# Attribution (required by CC BY 4.0):
# Video by GameplaysForFree, licensed under CC BY 4.0
# https://creativecommons.org/licenses/by/4.0/
# Source: https://youtu.be/EtVOvPyuOjk
# -------------------------------------------------------------------
import os
import random
import subprocess
from moviepy.editor import VideoFileClip

SOURCE_YOUTUBE_URL = "https://youtu.be/EtVOvPyuOjk"
SOURCE_FILE = "bg_source.mp4"
OUTPUT_FILE = "background.mp4"

TARGET_DURATION = 130  # generous cushion above the 60-120s story length


def download_source_video():
    print(f"⬇️ Downloading source parkour footage via yt-dlp...")
    subprocess.run(
        ["yt-dlp", "-f", "bestvideo[ext=mp4]/best[ext=mp4]/best",
         "-o", SOURCE_FILE, SOURCE_YOUTUBE_URL],
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
    print("ℹ️ Remember: this footage requires CC BY 4.0 attribution to 'GameplaysForFree' in the post caption.")


if __name__ == "__main__":
    main()
