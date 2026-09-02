# -------------------------------------------------------------------
# Upload video to Cloudinary using chunked REST uploads.
# This avoids Cloudinary's 413 Request Entity Too Large error for
# videos larger than 100 MB.
# -------------------------------------------------------------------
import os
import uuid
import requests

VIDEO_PATH = "final_short.mp4"
CHUNK_SIZE = 8 * 1024 * 1024  # 8 MB; Cloudinary requires >5 MB except final chunk
TIMEOUT = 180


def upload_chunked(video_path, cloud_name, upload_preset):
    url = f"https://api.cloudinary.com/v1_1/{cloud_name}/video/upload"
    total_size = os.path.getsize(video_path)
    upload_id = str(uuid.uuid4())
    start = 0
    final_data = None

    print(f"☁️ Uploading {total_size / (1024 * 1024):.1f} MB video to Cloudinary in chunks...")

    with open(video_path, "rb") as f:
        while start < total_size:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break

            end = start + len(chunk) - 1
            headers = {
                "X-Unique-Upload-Id": upload_id,
                "Content-Range": f"bytes {start}-{end}/{total_size}",
            }

            files = {
                "file": ("final_short.mp4", chunk, "video/mp4"),
            }
            data = {
                "upload_preset": upload_preset,
            }

            resp = requests.post(
                url,
                headers=headers,
                data=data,
                files=files,
                timeout=TIMEOUT,
            )

            if not resp.ok:
                print(f"❌ Cloudinary chunk upload failed ({resp.status_code}): {resp.text[:1000]}")
                resp.raise_for_status()

            response_data = resp.json()
            final_data = response_data
            uploaded_mb = (end + 1) / (1024 * 1024)
            total_mb = total_size / (1024 * 1024)
            print(f"   Uploaded {uploaded_mb:.1f}/{total_mb:.1f} MB")

            start = end + 1

    if not final_data:
        raise RuntimeError("❌ Cloudinary returned no upload response.")

    return final_data


def main():
    cloud_name = os.environ.get("CLOUDINARY_CLOUD_NAME")
    upload_preset = os.environ.get("CLOUDINARY_UPLOAD_PRESET")

    if not cloud_name or not upload_preset:
        raise ValueError("❌ Missing CLOUDINARY_CLOUD_NAME or CLOUDINARY_UPLOAD_PRESET secret!")

    if not os.path.exists(VIDEO_PATH):
        raise FileNotFoundError(f"❌ '{VIDEO_PATH}' missing! Run render_video.py first.")

    data = upload_chunked(VIDEO_PATH, cloud_name, upload_preset)

    secure_url = data.get("secure_url")
    if not secure_url:
        raise RuntimeError(f"❌ Unexpected Cloudinary response: {data}")

    print(f"✅ Uploaded! Public URL: {secure_url}")

    with open("video_url.txt", "w", encoding="utf-8") as f:
        f.write(secure_url)

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as f:
            f.write(f"video_url={secure_url}\n")


if __name__ == "__main__":
    main()
