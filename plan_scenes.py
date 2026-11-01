"""Build a scene-by-scene visual plan for an original horror short.

This stage does not call paid APIs or publish videos. It prepares scene
prompts that an image provider can use in the next implementation phase.
"""
import json
import os
import re
from pathlib import Path

STORY_PATH = Path(os.getenv("STORY_FILE", "story.txt"))
OUTPUT_PATH = Path(os.getenv("SCENE_PLAN_FILE", "scene_plan.json"))
SCENE_COUNT = int(os.getenv("SCENE_COUNT", "8"))
TARGET_SECONDS = float(os.getenv("TARGET_DURATION", "60"))
STYLE = (
    "Vertical 9:16 cinematic dark fantasy horror illustration, atmospheric "
    "lighting, dramatic composition, detailed environment, consistent "
    "character design, no text, no watermark, original artwork"
)


def split_story(text):
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def plan_scenes(text, count=SCENE_COUNT, duration=TARGET_SECONDS):
    if not text.strip():
        raise ValueError("Story is empty")
    if not 1 <= count <= 20:
        raise ValueError("SCENE_COUNT must be between 1 and 20")
    if duration <= 0:
        raise ValueError("TARGET_DURATION must be positive")

    sentences = split_story(text)
    # Distribute consecutive sentences across scenes to retain narrative order.
    count = min(count, max(1, len(sentences)))
    scenes = []
    for i in range(count):
        start_idx = i * len(sentences) // count
        end_idx = (i + 1) * len(sentences) // count
        passage = " ".join(sentences[start_idx:end_idx])
        start = round(i * duration / count, 2)
        end = round((i + 1) * duration / count, 2)
        scenes.append({
            "id": i + 1,
            "start": start,
            "end": end,
            "narration_excerpt": passage,
            "image_prompt": (
                f"{STYLE}. Visualize this story moment without writing words "
                f"into the image: {passage}"
            ),
            "motion": ["slow_push_in", "pan_left", "slow_pull_back", "pan_right"][i % 4],
            "image_path": f"scenes/scene_{i + 1:02d}.png",
        })
    return {"version": 1, "duration": duration, "style": STYLE, "scenes": scenes}


def main():
    story = STORY_PATH.read_text(encoding="utf-8")
    result = plan_scenes(story)
    OUTPUT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Planned {len(result['scenes'])} scenes in {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
