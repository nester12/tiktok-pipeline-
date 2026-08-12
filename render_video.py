# -------------------------------------------------------------------
# High-Visibility TikTok Caption & Video Renderer
# -------------------------------------------------------------------
import os
import json
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import VideoFileClip, AudioFileClip, ImageClip, CompositeVideoClip

BACKGROUND_VIDEO = "background.mp4"
NARRATION_AUDIO = "narration.wav"
TIMESTAMPS_JSON = "timestamps.json"
OUTPUT_VIDEO = "final_short.mp4"


def create_caption_image(text, size=(1080, 1920)):
    """Draws smaller, quick-read TikTok captions onto a transparent canvas."""
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    font_size = 58  # reduced from 82 for faster reading, less screen dominance
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
    except Exception:
        font = ImageFont.load_default()

    text = text.upper()
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]

    x = (size[0] - text_w) / 2
    y = int(size[1] * 0.62)

    stroke_width = 5
    stroke_color = "black"
    text_color = "#FFE600"

    for dx in range(-stroke_width, stroke_width + 1):
        for dy in range(-stroke_width, stroke_width + 1):
            if dx * dx + dy * dy <= stroke_width * stroke_width:
                draw.text((x + dx, y + dy), text, font=font, fill=stroke_color)

    draw.text((x, y), text, font=font, fill=text_color)
    return np.array(img)


def main():
    for f in [BACKGROUND_VIDEO, NARRATION_AUDIO, TIMESTAMPS_JSON]:
        if not os.path.exists(f):
            raise FileNotFoundError(f"❌ Missing required file: '{f}'. Run generate_audio.py first!")

    print("🎬 Loading assets and preparing video canvas...")

    audio_clip = AudioFileClip(NARRATION_AUDIO)
    audio_duration = audio_clip.duration

    with open(TIMESTAMPS_JSON, "r", encoding="utf-8") as f:
        word_data = json.load(f)

    bg_clip = VideoFileClip(BACKGROUND_VIDEO)

    if bg_clip.duration < audio_duration:
        bg_clip = bg_clip.loop(duration=audio_duration + 2)
    else:
        bg_clip = bg_clip.subclip(0, audio_duration + 0.5)

    w, h = bg_clip.size
    target_w, target_h = 1080, 1920
    aspect_target = target_w / target_h
    aspect_current = w / h

    if aspect_current > aspect_target:
        new_w = int(h * aspect_target)
        bg_clip = bg_clip.crop(x_center=w / 2, width=new_w)
    else:
        new_h = int(w / aspect_target)
        bg_clip = bg_clip.crop(y_center=h / 2, height=new_h)

    bg_clip = bg_clip.resize((target_w, target_h))

    print("🎨 Building quick-read caption overlay sequence...")
    caption_clips = []

    for entry in word_data:
        word = entry["word"].strip().upper()
        if not word:
            continue

        start_t = entry["start"]
        # Tighter timing: less lingering padding so captions feel snappier
        end_t = min(entry["end"] + 0.03, audio_duration)
        duration = max(end_t - start_t, 0.12)

        if duration > 0:
            cap_img = create_caption_image(word)
            txt_clip = (ImageClip(cap_img)
                        .set_start(start_t)
                        .set_duration(duration)
                        .set_position(("center", "center")))
            caption_clips.append(txt_clip)

    print("⚡ Compositing video, voiceover, and captions...")
    final_clip = CompositeVideoClip([bg_clip] + caption_clips, size=(target_w, target_h))
    final_clip = final_clip.set_audio(audio_clip).set_duration(audio_duration)

    final_clip.write_videofile(
        OUTPUT_VIDEO,
        fps=30,
        codec="libx264",
        audio_codec="aac",
        preset="fast",
        threads=4
    )

    print(f"\n🎉 SUCCESS! Rendered with quick-read captions -> '{OUTPUT_VIDEO}'")


if __name__ == "__main__":
    main()
