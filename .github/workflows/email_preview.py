# -------------------------------------------------------------------
# Email the rendered video to yourself for review, instead of posting
# -------------------------------------------------------------------
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders

VIDEO_PATH = "final_short.mp4"
STORY_PATH = "story.txt"


def main():
    gmail_address = os.environ.get("GMAIL_ADDRESS")
    gmail_app_password = os.environ.get("GMAIL_APP_PASSWORD")
    send_to = os.environ.get("EMAIL_TO", gmail_address)

    missing = [n for n, v in [
        ("GMAIL_ADDRESS", gmail_address),
        ("GMAIL_APP_PASSWORD", gmail_app_password),
    ] if not v]
    if missing:
        raise ValueError(f"❌ Missing required environment variable(s): {', '.join(missing)}")

    if not os.path.exists(VIDEO_PATH):
        raise FileNotFoundError(f"❌ '{VIDEO_PATH}' missing! Run render_video.py first.")

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
        "Video is attached — watch it and see how the captions, pacing, and "
        "background feel before we turn auto-posting back on.\n"
    )
    msg.attach(MIMEText(body, "plain"))

    with open(VIDEO_PATH, "rb") as f:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(f.read())
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", f"attachment; filename=final_short.mp4")
    msg.attach(part)

    print("📤 Sending email via Gmail SMTP...")
    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(gmail_address, gmail_app_password)
        server.send_message(msg)

    print(f"\n✅ Preview email sent to {send_to}!")


if __name__ == "__main__":
    main()
