# -------------------------------------------------------------------
# TikTok Upload
# -------------------------------------------------------------------
import os
from tiktok_uploader.upload import upload_video

VIDEO_PATH = "final_short.mp4"
CAPTION = "Caught my business partner draining company funds! #storytime #redditstories #fyp"


def main():
    session_id = os.environ.get("TIKTOK_SESSION_ID")

    if not session_id:
        raise ValueError("❌ 'TIKTOK_SESSION_ID' missing from environment (GitHub Actions secret)!")

    if not os.path.exists(VIDEO_PATH):
        raise FileNotFoundError(f"❌ '{VIDEO_PATH}' missing! Run render_video.py first.")

    print("🚀 Launching Chrome in clean process...")
    try:
        upload_video(
            filename=VIDEO_PATH,
            description=CAPTION,
            sessionid=session_id,
            headless=True
        )
        print("\n🎉 SUCCESS! Your video has been posted to TikTok!")
    except Exception as e:
        print(f"\n❌ Upload failed: {e}")
        raise


if __name__ == "__main__":
    main()
