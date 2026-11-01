"""Create clearly marked free placeholder scenes for pipeline integration testing.

These are not AI illustrations; replace them with generated scene images
before judging final video quality.
"""
import json
from pathlib import Path
from PIL import Image, ImageDraw

def main():
    plan = json.loads(Path("scene_plan.json").read_text(encoding="utf-8"))
    for scene in plan["scenes"]:
        path = Path(scene["image_path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            continue
        image = Image.new("RGB", (540, 960), (12, 17, 27))
        draw = ImageDraw.Draw(image)
        draw.rectangle((20, 20, 520, 940), outline=(80, 95, 120), width=3)
        draw.text((45, 80), "CINEMATIC PREVIEW - PLACEHOLDER", fill=(220, 220, 220))
        draw.text((45, 120), "Scene " + str(scene["id"]), fill=(180, 200, 230))
        draw.text((45, 165), "Final AI image not generated", fill=(200, 200, 200))
        image.save(path)
        print("Placeholder created:", path)

if __name__ == "__main__":
    main()
