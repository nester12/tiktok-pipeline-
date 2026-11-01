"""Render a cinematic illustrated short from generated scene images.

Requires scene_plan.json, scenes/scene_XX.png, narration.wav and timestamps.json.
Does not call paid APIs or publish anything.
"""
import json
import os
from pathlib import Path

from moviepy.editor import (
    AudioFileClip, CompositeVideoClip, ImageClip, concatenate_videoclips
)
from render_video import create_caption_image

WIDTH, HEIGHT = 1080, 1920
FPS = 24


def render():
    plan = json.loads(Path("scene_plan.json").read_text(encoding="utf-8"))
    scenes = plan["scenes"]
    if not scenes:
        raise ValueError("No planned scenes")
    audio = AudioFileClip("narration.wav")
    duration = audio.duration
    segments = []
    for i, scene in enumerate(scenes):
        path = Path(scene["image_path"])
        if not path.is_file():
            raise FileNotFoundError(f"Missing scene image: {path}. Generate or supply images first.")
        start = duration * i / len(scenes)
        end = duration * (i + 1) / len(scenes)
        length = end - start
        base = ImageClip(str(path))
        # Fill the vertical canvas without distorting the image.
        w, h = base.size
        scale = max(WIDTH / w, HEIGHT / h)
        base = base.resize(scale)
        w, h = base.size
        base = base.crop(x_center=w / 2, y_center=h / 2, width=WIDTH, height=HEIGHT)
        # Slow push-in. This is motion on a still image, not AI character animation.
        zoom = base.resize(lambda t: 1 + 0.04 * t / max(length, 0.1))
        moving = CompositeVideoClip(
            [zoom.set_position("center")], size=(WIDTH, HEIGHT)
        ).set_duration(length)
        segments.append(moving)
    visuals = concatenate_videoclips(segments, method="compose")
    word_data = json.loads(Path("timestamps.json").read_text(encoding="utf-8"))
    captions = []
    for item in word_data:
        word = str(item.get("word", "")).strip()
        start = max(0.0, float(item.get("start", 0)))
        end = min(duration, float(item.get("end", start)) + 0.04)
        if not word or end <= start:
            continue
        img = create_caption_image(word)
        captions.append(
            ImageClip(img).set_start(start).set_duration(end - start)
            .set_position("center")
        )
    final = CompositeVideoClip([visuals] + captions, size=(WIDTH, HEIGHT))
    final = final.set_audio(audio).set_duration(duration)
    final.write_videofile(
        os.getenv("PROTOTYPE_OUTPUT", "cinematic_prototype.mp4"),
        fps=FPS, codec="libx264", audio_codec="aac", preset="medium", threads=2
    )
    final.close()
    audio.close()


if __name__ == "__main__":
    render()
