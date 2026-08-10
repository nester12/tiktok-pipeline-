# -------------------------------------------------------------------
# TikTok Upload
# -------------------------------------------------------------------
import os
from tiktok_uploader.upload import upload_video

VIDEO_PATH = "final_short.mp4"
CAPTION = "Caught my business partner draining company funds! #storytime #redditstories #fyp"
COOKIES_FILE = "cookies.txt"


def write_cookies_file(session_id):
    """
    Writes a Netscape-format cookies file with a proper domain,
    which avoids the 'Cookie should have a url or a domain/path pair'
    error that happens when passing a bare sessionid string.
    """
    # Netscape cookie file format:
    # domain  include_subdomains  path  secure  expiry  name  value
    line = "\t".join([
        ".tiktok.com", "TRUE", "/", "TRUE", "2147483647",
        "sessionid", session_id
    ])
    with open(COOKIES_FILE, "w", encoding="utf-8") as f:
        f.write("# Netscape HTTP Cookie File\n")
        f.write(line + "\n")


def main():
    session_id = os.environ.get("TIKTOK_SESSION_ID")

    if not session_id:
        raise ValueError("❌ 'TIKTOK_SESSION_ID' missing from environment (GitHub Actions secret)!")

    if not os.path.exists(VIDEO_PATH):
        raise FileNotFoundError(f"❌ '{VIDEO_PATH}' missing! Run render_video.py first.")

    write_cookies_file(session_id)

    print("🚀 Launching Chrome in clean process...")
    try:
        upload_video(
            filename=VIDEO_PATH,
            description=CAPTION,
            cookies=COOKIES_FILE,
            headless=True
        )
        print("\n🎉 SUCCESS! Your video has been posted to TikTok!")
    except Exception as e:
        print(f"\n❌ Upload failed: {e}")
        raise


if __name__ == "__main__":
    main()
