# -------------------------------------------------------------------
# Fetch background footage from Google Drive.
# Rotates source videos and remembers recently used time ranges so long
# videos can supply many different non-overlapping background clips.
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
RECENT_SOURCE_LIMIT = 3
TOP_SEGMENTS_TO_CONSIDER = 4
RANGES_PER_SOURCE_LIMIT = 8
OVERLAP_BUFFER = 10


def load_history():
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                sources = data.get("recent_sources", [])
                ranges = data.get("recent_ranges", {})
                if not isinstance(sources, list):
                    sources = []
                if not isinstance(ranges, dict):
                    ranges = {}
                return {
                    "recent_sources": [s for s in sources if s in SOURCE_FILE_IDS][-RECENT_SOURCE_LIMIT:],
                    "recent_ranges": ranges,
                }
            # Backward compatibility with the old list-only history format.
            if isinstance(data, list):
                return {
                    "recent_sources": [s for s in data if s in SOURCE_FILE_IDS][-RECENT_SOURCE_LIMIT:],
                    "recent_ranges": {},
                }
    except Exception as exc:
        print(f"⚠️ Could not read background history: {exc}")
    return {"recent_sources": [], "recent_ranges": {}}


def save_history(history):
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)
    except Exception as exc:
        print(f"⚠️ Could not save background history: {exc}")


def remember_source(file_id):
    history = load_history()
    recent = [s for s in history["recent_sources"] if s != file_id]
    recent.append(file_id)
    history["recent_sources"] = recent[-RECENT_SOURCE_LIMIT:]
    save_history(history)


def remember_range(file_id, start, duration):
    history = load_history()
    ranges = history["recent_ranges"]
    source_ranges = ranges.get(file_id, [])
    if not isinstance(source_ranges, list):
        source_ranges = []
    source_ranges.append({
        "start": round(float(start), 2),
        "end": round(float(start + duration), 2),
    })
    ranges[file_id] = source_ranges[-RANGES_PER_SOURCE_LIMIT:]
    history["recent_ranges"] = ranges
    save_history(history)
    print(f"🧠 Remembered source {file_id} at t={start:.0f}s-{start + duration:.0f}s.")


def download_source_video(file_id):
    print(f"⬇️ Downloading source footage (file id: {file_id})...")
    subprocess.run(
        ["gdown", f"https://drive.google.com/uc?id={file_id}", "-O", SOURCE_FILE],
        check=True,
    )


def is_valid_video(path):
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=30,
        )
        return float(result.stdout.strip()) > 0
    except Exception:
        return False


def build_source_order():
    recent = load_history()["recent_sources"]
    fresh = [s for s in SOURCE_FILE_IDS if s not in recent]
    old = [s for s in SOURCE_FILE_IDS if s in recent]
    random.shuffle(fresh)
    random.shuffle(old)
    print(f"🎞️ Background pool: {len(fresh)} preferred, {len(old)} recently used.")
    return fresh + old


def download_valid_source():
    for file_id in build_source_order():
        for attempt in range(1, 3):
            try:
                if os.path.exists(SOURCE_FILE):
                    os.remove(SOURCE_FILE)
                download_source_video(file_id)
                if is_valid_video(SOURCE_FILE):
                    print(f"✅ Valid download confirmed (file id: {file_id})")
                    remember_source(file_id)
                    return file_id
                print(f"⚠️ Downloaded file failed validation (attempt {attempt}/2).")
            except Exception as exc:
                print(f"⚠️ Download failed (attempt {attempt}/2): {exc}")
    raise RuntimeError("❌ None of the source videos could be downloaded successfully.")


def score_motion(video_path, start, duration):
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
                diffs.append(np.mean(cv2.absdiff(gray, prev_gray)))
            prev_gray = gray
        frame_idx += 1
    cap.release()
    return float(np.mean(diffs)) if diffs else 0.0


def overlaps_recent(file_id, start, duration):
    recent_ranges = load_history()["recent_ranges"].get(file_id, [])
    end = start + duration
    for item in recent_ranges:
        try:
            old_start = float(item["start"])
            old_end = float(item["end"])
        except (KeyError, TypeError, ValueError):
            continue
        # Add a small buffer so consecutive clips do not look almost identical.
        if start < old_end + OVERLAP_BUFFER and end > old_start - OVERLAP_BUFFER:
            return True
    return False


def choose_dynamic_segment(video_path, file_id, total_duration, segment_duration):
    if total_duration <= segment_duration:
        return 0.0

    starts = []
    start = 0.0
    while start + segment_duration <= total_duration:
        starts.append(start)
        start += WINDOW_STEP
    final_start = max(total_duration - segment_duration, 0.0)
    if all(abs(s - final_start) > 1.0 for s in starts):
        starts.append(final_start)

    fresh_starts = [s for s in starts if not overlaps_recent(file_id, s, segment_duration)]
    if fresh_starts:
        print(f"🆕 {len(fresh_starts)}/{len(starts)} timestamp windows have not been used recently.")
        starts = fresh_starts
    else:
        print("♻️ All timestamp windows overlap recent clips; recycling the best available section.")

    print(f"🔍 Scoring {len(starts)} candidate background sections...")
    scored = []
    for candidate_start in starts:
        score = score_motion(video_path, candidate_start, min(segment_duration, 15))
        scored.append((candidate_start, score))
        print(f"   t={candidate_start:.0f}s → motion score {score:.2f}")

    scored.sort(key=lambda item: item[1], reverse=True)
    shortlist = scored[:min(TOP_SEGMENTS_TO_CONSIDER, len(scored))]
    weights = [max(score, 0.1) for _, score in shortlist]
    chosen_start, chosen_score = random.choices(shortlist, weights=weights, k=1)[0]
    print(f"🎲 Selected t={chosen_start:.0f}s (motion score {chosen_score:.2f}).")
    return chosen_start


def main():
    selected_source = download_valid_source()
    clip = VideoFileClip(SOURCE_FILE)
    total_duration = clip.duration
    print(f"📼 Source video duration: {total_duration:.1f}s")

    if total_duration <= TARGET_DURATION:
        start = 0.0
        segment = clip
    else:
        start = choose_dynamic_segment(
            SOURCE_FILE, selected_source, total_duration, TARGET_DURATION
        )
        segment = clip.subclip(start, start + TARGET_DURATION)

    segment.write_videofile(
        OUTPUT_FILE, fps=30, codec="libx264", audio=False, preset="fast"
    )
    remember_range(selected_source, start, min(TARGET_DURATION, total_duration))
    clip.close()
    print(f"✅ Background saved from source {selected_source}, starting at t={start:.0f}s.")


if __name__ == "__main__":
    main()
