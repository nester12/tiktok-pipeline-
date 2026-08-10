# -------------------------------------------------------------------
# Upload video to Cloudinary (replaces GitHub Releases hosting,
# which gets blocked by bot-detection when fetched by third parties)
# -------------------------------------------------------------------
import os
import requests

VIDEO_PATH = "final_short.mp4"


def main():
    cloud_name = os.environ.get("CLOUDINARY_CLOUD_NAME")
    upload_preset = os.environ.get("CLOUDINARY_UPLOAD_PRESET")

    if not cloud_name or not upload_preset:
        raise ValueError("❌ Missing CLOUDINARY_CLOUD_NAME or CLOUDINARY_UPLOAD_PRESET secret!")

    if not os.path.exists(VIDEO_PATH):
        raise FileNotFoundError(f"❌ '{VIDEO_PATH}' missing! Run render_video.py first.")

    print("☁️ Uploading video to Cloudinary...")
    url = f"https://api.cloudinary.com/v1_1/{cloud_name}/video/upload"

    with open(VIDEO_PATH, "rb") as f:
        resp = requests.post(
            url,
            data={"upload_preset": upload_preset},
            files={"file": f},
            timeout=120,
        )

    if resp.status_code != 200:
        print(f"❌ Cloudinary error response: {resp.text}")
    resp.raise_for_status()
    data = resp.json()

    secure_url = data.get("secure_url")
    if not secure_url:
        raise RuntimeError(f"❌ Unexpected Cloudinary response: {data}")

    print(f"✅ Uploaded! Public URL: {secure_url}")

    # Make it available to the next GitHub Actions step
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"video_url={secure_url}\n")


if __name__ == "__main__":
    main()
