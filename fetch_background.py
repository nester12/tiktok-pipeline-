# -------------------------------------------------------------------
# Fetch background footage: picks one of several source videos from
# Google Drive at random, then scores sliding windows across it by
# frame-to-frame motion (not just random selection) to pick the most
# dynamic, attention-grabbing segment of the target duration.
# -------------------------------------------------------------------
import os
import random
import subprocess
import cv2
import numpy as np
from moviepy.editor import VideoFileClip

SOURCE_FILE_IDS = [
    "1KGqdG2TwoTlrlzwmumV_91EJxnZ3T_Yh",
    "1Bt3VWdc-ZOEMNFA4MF1DFfDkkbBCz7Bd",
    "1xqrtTpdopXkySnZvArgSZp5kb87KhLHs",
    "1tLLb0XXBfxu5KsxSD00vb-PxEvf8b8Xv",
    "1EIOebyFi2HyI2pWgDGBZ5v0g4CnaGJL6",
]

SOURCE_FILE = "bg_source.mp4"
OUTPUT_FILE = "background.mp4"

TARGET_DURATION = 130   # generous cushion above the 60-120s story length
WINDOW_STEP = 20        # seconds between candidate window starts
SAMPLE_FPS = 2          # frames per second sampled for motion scoring (keeps it fast)


def download_source_video(file_id):
    print(f"⬇️ Downloading source footage (file id: {file_id})...")
    subprocess.run(
        ["gdown", f"https://drive.google.com/uc?id={file_id}", "-O", SOURCE_FILE],
        check=True
    )


def score_motion(video_path, start, duration):
    """Scores a segment by average frame-to-frame pixel difference —
    higher score = more visual motion/change happening."""
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    frame_interval = max(int(fps / SAMPLE_FPS), 1)

    start_frame = int(start * fps)
    end_frame = int((start + duration) * fps)
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

    prev_gray = None
    diffs = []
    frame_idx = start_frame

    while frame_idx < end_frame:
        ret, frame = cap.read()
        if not ret:
            break
        if (frame_idx - start_frame) % frame_interval == 0:
            small = cv2.resize(frame, (160, 284))
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            if prev_gray is not None:
                diff = cv2.absdiff(gray, prev_gray)
                diffs.append(np.mean(diff))
            prev_gray = gray
        frame_idx += 1

    cap.release()
    return np.mean(diffs) if diffs else 0.0


def find_best_segment(video_path, total_duration, segment_duration):
    """Slides candidate windows across the video and returns the
    start time of the most motion-heavy one."""
    if total_duration <= segment_duration:
        return 0.0

    candidates = []
    start = 0.0
    while start + segment_duration <= total_duration:
        candidates.append(start)
        start += WINDOW_STEP

    if not candidates:
        return 0.0

    print(f"🔍 Scoring {len(candidates)} candidate segments for motion...")
    best_start, best_score = 0.0, -1
    for c in candidates:
        score = score_motion(video_path, c, min(segment_duration, 15))  # sample first 15s of each window for speed
        print(f"   t={c:.0f}s → motion score {score:.2f}")
        if score > best_score:
            best_score = score
            best_start = c

    print(f"🏆 Best segment starts at t={best_start:.0f}s (score {best_score:.2f})")
    return best_start


def main():
    file_id = random.choice(SOURCE_FILE_IDS)
    download_source_video(file_id)

    clip = VideoFileClip(SOURCE_FILE)
    total_duration = clip.duration
    print(f"📼 Source video duration: {total_duration:.1f}s")

    if total_duration <= TARGET_DURATION:
        segment = clip
    else:
        best_start = find_best_segment(SOURCE_FILE, total_duration, TARGET_DURATION)
        segment = clip.subclip(best_start, best_start + TARGET_DURATION)

    segment.write_videofile(OUTPUT_FILE, fps=30, codec="libx264", audio=False, preset="fast")
    clip.close()

    print(f"\n✅ Background segment saved to '{OUTPUT_FILE}'")


if __name__ == "__main__":
    main()
