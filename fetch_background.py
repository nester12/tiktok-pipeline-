# -------------------------------------------------------------------
# Fetch background footage from Google Drive.
#
# Improvements:
# - rotates through multiple source videos instead of repeatedly using
#   whichever one happens to be first after a shuffle
# - remembers recently used source IDs across pipeline runs
# - avoids the last few backgrounds whenever alternatives are available
# - scores candidate sections for motion, then randomly chooses from the
#   strongest sections instead of always returning the exact same clip
# -------------------------------------------------------------------
import json
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
HISTORY_FILE = "recent_backgrounds.json"

TARGET_DURATION = 130
WINDOW_STEP = 20
SAMPLE_FPS = 2

# With five available sources, avoiding the last three makes consecutive
# repetition very unlikely while still leaving alternatives on every run.
RECENT_SOURCE_LIMIT = 3

# Do not always select the single highest-motion section. Pick from the
# strongest few, weighted by motion score, so the same source can still
# produce different footage on different occasions.
TOP_SEGMENTS_TO_CONSIDER = 4


def load_recent_sources():
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return [str(item) for item in data if str(item) in SOURCE_FILE_IDS][
                    -RECENT_SOURCE_LIMIT:
                ]
    except Exception as exc:
        print(f"⚠️ Could not read background history: {exc}")
    return []


def remember_source(file_id):
    recent = load_recent_sources()
    recent = [item for item in recent if item != file_id]
    recent.append(file_id)
    recent = recent[-RECENT_SOURCE_LIMIT:]

    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(recent, f, indent=2)
        print(f"🧠 Background history updated ({len(recent)} recent source(s)).")
    except Exception as exc:
        print(f"⚠️ Could not save background history: {exc}")


def download_source_video(file_id):
    print(f"⬇️ Downloading source footage (file id: {file_id})...")
    subprocess.run(
        ["gdown", f"https://drive.google.com/uc?id={file_id}", "-O", SOURCE_FILE],
        check=True,
    )


def is_valid_video(path):
    """Check that the downloaded file is a readable video."""
    try:
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
            capture_output=True,
            text=True,
            timeout=30,
        )
        duration = float(result.stdout.strip())
        return duration > 0
    except Exception:
        return False


def build_source_order():
    """Prefer sources not used in the most recent pipeline runs."""
    recent = load_recent_sources()

    fresh = [file_id for file_id in SOURCE_FILE_IDS if file_id not in recent]
    old = [file_id for file_id in SOURCE_FILE_IDS if file_id in recent]

    random.shuffle(fresh)
    random.shuffle(old)

    print(
        f"🎞️ Background pool: {len(SOURCE_FILE_IDS)} total | "
        f"{len(fresh)} preferred | {len(old)} recently used"
    )

    return fresh + old


def download_valid_source():
    """Try unused sources first, falling back to recent ones only if needed."""
    candidates = build_source_order()

    for file_id in candidates:
        for attempt in range(1, 3):
            try:
                if os.path.exists(SOURCE_FILE):
                    os.remove(SOURCE_FILE)

                download_source_video(file_id)

                if is_valid_video(SOURCE_FILE):
                    print(f"✅ Valid download confirmed (file id: {file_id})")
                    remember_source(file_id)
                    return file_id

                print(
                    f"⚠️ Downloaded file failed validation "
                    f"(attempt {attempt}/2)."
                )
            except Exception as exc:
                print(f"⚠️ Download failed (attempt {attempt}/2): {exc}")

        print(f"🔁 Source {file_id} failed twice; trying another background...")

    raise RuntimeError("❌ None of the source videos could be downloaded successfully.")


def score_motion(video_path, start, duration):
    """Score a segment using average frame-to-frame visual change."""
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
    return float(np.mean(diffs)) if diffs else 0.0


def choose_dynamic_segment(video_path, total_duration, segment_duration):
    """Choose one of the strongest-motion windows rather than one fixed winner."""
    if total_duration <= segment_duration:
        return 0.0

    starts = []
    start = 0.0
    while start + segment_duration <= total_duration:
        starts.append(start)
        start += WINDOW_STEP

    # Include the final possible window so long clips do not leave the tail
    # permanently unused when WINDOW_STEP does not land exactly on it.
    final_start = max(total_duration - segment_duration, 0.0)
    if all(abs(existing - final_start) > 1.0 for existing in starts):
        starts.append(final_start)

    if not starts:
        return 0.0

    print(f"🔍 Scoring {len(starts)} candidate background sections...")
    scored = []

    for candidate_start in starts:
        score = score_motion(
            video_path,
            candidate_start,
            min(segment_duration, 15),
        )
        scored.append((candidate_start, score))
        print(f"   t={candidate_start:.0f}s → motion score {score:.2f}")

    scored.sort(key=lambda item: item[1], reverse=True)
    shortlist = scored[: min(TOP_SEGMENTS_TO_CONSIDER, len(scored))]

    # Keep every candidate selectable even if a score happens to be zero.
    weights = [max(score, 0.1) for _, score in shortlist]
    chosen_start, chosen_score = random.choices(shortlist, weights=weights, k=1)[0]

    print(
        f"🎲 Selected t={chosen_start:.0f}s from the top "
        f"{len(shortlist)} sections (motion score {chosen_score:.2f})."
    )

    return chosen_start


def main():
    selected_source = download_valid_source()

    clip = VideoFileClip(SOURCE_FILE)
    total_duration = clip.duration
    print(f"📼 Source video duration: {total_duration:.1f}s")

    if total_duration <= TARGET_DURATION:
        segment = clip
        print("ℹ️ Source is shorter than the target window; using the full source.")
    else:
        start = choose_dynamic_segment(SOURCE_FILE, total_duration, TARGET_DURATION)
        segment = clip.subclip(start, start + TARGET_DURATION)

    segment.write_videofile(
        OUTPUT_FILE,
        fps=30,
        codec="libx264",
        audio=False,
        preset="fast",
    )

    clip.close()

    print(f"✅ Background saved to '{OUTPUT_FILE}' from source {selected_source}.")


if __name__ == "__main__":
    main()
