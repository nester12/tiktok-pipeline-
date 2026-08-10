# -------------------------------------------------------------------
# Email the rendered video to yourself for review, instead of posting
# -------------------------------------------------------------------
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

VIDEO_PATH = "final_short.mp4"
STORY_PATH = "story.txt"


def main():
    gmail_address = os.environ.get("GMAIL_ADDRESS")
    gmail_app_password = os.environ.get("GMAIL_APP_PASSWORD")
    send_to = os.environ.get("EMAIL_TO", gmail_address)
    video_url = os.environ.get("VIDEO_URL")

    missing = [n for n, v in [
        ("GMAIL_ADDRESS", gmail_address),
        ("GMAIL_APP_PASSWORD", gmail_app_password),
        ("VIDEO_URL", video_url),
    ] if not v]
    if missing:
        raise ValueError(f"❌ Missing required environment variable(s): {', '.join(missing)}")

    story_text = ""
    if os.path.exists(STORY_PATH):
        with open(STORY_PATH, "r", encoding="utf-8") as f:
            story_text = f.read()

    print(f"📧 Preparing preview email to {send_to}...")

    msg = MIMEMultipart()
    msg["From"] = gmail_address
    msg["To"] = send_to
    msg["Subject"] = "🎬 New pipeline preview — TikTok video ready for review"

    body = (
        "Here's your latest pipeline output for review before it goes live.\n\n"
        "Story text:\n"
        "-----------\n"
        f"{story_text}\n\n"
        f"Watch it here:\n{video_url}\n\n"
        "Check the captions, pacing, and background before we turn auto-posting back on.\n"
    )
    msg.attach(MIMEText(body, "plain"))

    print("📤 Sending email via Gmail SMTP...")
    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(gmail_address, gmail_app_password)
        server.send_message(msg)

    print(f"\n✅ Preview email sent to {send_to}!")


if __name__ == "__main__":
    main()
