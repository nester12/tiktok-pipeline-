"""Opt-in Gemini image generation. Default is preview only."""
import base64
import json
import os
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image

PLAN = Path("scene_plan.json")
LEDGER = Path("image_spend_ledger.json")


def main():
    scenes = json.loads(PLAN.read_text(encoding="utf-8"))["scenes"]
    if len(scenes) > 8:
        raise ValueError("Maximum eight images per video")
    pending = [s for s in scenes if not Path(s["image_path"]).exists()]
    if os.getenv("ENABLE_PAID_IMAGES") != "YES":
        print(f"Preview only: {len(pending)} images planned; no paid requests")
        return

    model = os.environ["GEMINI_IMAGE_MODEL"]
    key = os.environ["GEMINI_API_KEY"]
    estimate = float(os.environ["ESTIMATED_IMAGE_PRICE_GBP"])
    cap = float(os.getenv("MONTHLY_IMAGE_BUDGET_GBP", "11"))
    if estimate <= 0 or cap <= 0:
        raise ValueError("Configure positive estimated image price and budget")
    from datetime import datetime, timezone
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    ledger = json.loads(LEDGER.read_text()) if LEDGER.exists() else {}
    for scene in pending:
        if float(ledger.get(month, 0)) + estimate > cap:
            raise RuntimeError("Image budget reached")
        # Reserve each attempted request before sending it; no automatic retries.
        ledger[month] = round(float(ledger.get(month, 0)) + estimate, 6)
        LEDGER.write_text(json.dumps(ledger, indent=2))
        response = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            params={"key": key},
            json={"contents": [{"parts": [{"text": scene["image_prompt"]}]}],
                  "generationConfig": {"responseModalities": ["IMAGE"]}},
            timeout=120,
        )
        response.raise_for_status()
        parts = response.json()["candidates"][0]["content"]["parts"]
        images = [p["inlineData"] for p in parts if "inlineData" in p]
        if not images:
            raise RuntimeError("No image returned")
        image = Image.open(BytesIO(base64.b64decode(images[0]["data"])))
        path = Path(scene["image_path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        image.convert("RGB").save(path, "PNG")
        print("Created", path)


if __name__ == "__main__":
    main()
