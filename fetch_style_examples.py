# TikTok style/trend learning pipeline.
# - Discovers niche videos with SocialCrawl.
# - Skips videos already analysed.
# - Scores videos by engagement, velocity, recency and total views.
# - Fetches expensive transcripts only for the strongest NEW candidates.
# - Uses Gemini for structured story-beat analysis, with Groq fallback.
# - Keeps all-time history in SQLite while exporting compact JSON files
#   that the story generator can consume.

import hashlib
import json
import math
import os
import re
import sqlite3
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

SOCIAL_BASE = "https://www.socialcrawl.dev/v1/tiktok"
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

GEMINI_MODEL = os.getenv("GEMINI_STYLE_MODEL", "gemini-3.7-flash")
GROQ_MODEL = os.getenv("GROQ_STYLE_MODEL", "openai/gpt-oss-120b")

DB_FILE = "style_learning.db"
STYLE_EXAMPLES_FILE = "style_examples.json"
TRENDING_HASHTAGS_FILE = "trending_hashtags.json"
STYLE_NOTES_FILE = "style_notes.txt"
TARGET_PACE_FILE = "target_pace.json"
TREND_SUMMARY_FILE = "trend_summary.json"

CORE_HASHTAGS = [
    "redditstories",
    "redditstory",
    "storytime",
    "aitastories",
    "confession",
    "familydrama",
    "relationshipstories",
]
BLOCKED_DISCOVERY_TAGS = {
    "fyp", "fy", "foryou", "foryoupage", "viral", "trending",
}

SEED_HANDLES = ["aethryn", "textplan", "best_texting"]
OWN_HANDLE = os.getenv("TIKTOK_OWN_HANDLE", "only1_short_story")

VIDEOS_PER_HASHTAG = 10
VIDEOS_PER_HANDLE = 8
OWN_VIDEO_LIMIT = 20
MAX_NEW_EXTERNAL_TRANSCRIPTS = 16
MAX_NEW_OWN_TRANSCRIPTS = 8
MAX_EXPORT_EXAMPLES = 30
CURRENT_TREND_DAYS = 90
HOT_TREND_DAYS = 30
REQUEST_TIMEOUT = 35
MIN_TRANSCRIPT_WORDS = 35

session = requests.Session()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat()


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def first(data: Dict[str, Any], *keys: str, default=None):
    for key in keys:
        value = data.get(key)
        if value is not None:
            return value
    return default


def parse_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (ValueError, OSError, OverflowError):
            return None
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        try:
            return datetime.fromtimestamp(float(text), tz=timezone.utc)
        except (ValueError, OSError, OverflowError):
            return None
    text = text.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def extract_items(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict):
        return []
    data = payload.get("data", payload)
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for key in ("items", "videos", "posts", "results"):
            value = data.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
    return []


def social_get(api_key: str, path: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    try:
        resp = session.get(
            f"{SOCIAL_BASE}/{path.lstrip('/')}",
            headers={"x-api-key": api_key},
            params=params,
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        print(f"⚠️ SocialCrawl request failed ({path}): {exc}")
        return None
    if resp.status_code != 200:
        print(f"⚠️ SocialCrawl {path} returned {resp.status_code}: {resp.text[:240]}")
        return None
    try:
        return resp.json()
    except ValueError:
        print(f"⚠️ SocialCrawl {path} returned invalid JSON.")
        return None


def get_hashtag_videos(api_key: str, hashtag: str, limit: int) -> List[Dict[str, Any]]:
    print(f"🔎 Searching #{hashtag}...")
    payload = social_get(api_key, "search/hashtag", {"hashtag": hashtag.lstrip("#"), "limit": limit})
    return extract_items(payload)


def get_profile_videos(api_key: str, handle: str, limit: int) -> List[Dict[str, Any]]:
    print(f"🔎 Fetching @{handle}...")
    payload = social_get(api_key, "profile/videos", {"handle": handle.lstrip("@"), "limit": limit})
    return extract_items(payload)


def get_transcript(api_key: str, video_url: str) -> Optional[str]:
    payload = social_get(api_key, "post/transcript", {"url": video_url})
    if not payload:
        return None
    data = payload.get("data", payload)
    if isinstance(data, str):
        return data.strip()
    if isinstance(data, dict):
        for key in ("transcript", "text", "content"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def extract_hashtags(caption: str) -> List[str]:
    if not caption:
        return []
    return [
        tag.lower()
        for tag in re.findall(r"#([A-Za-z0-9_]+)", caption)
        if tag.lower() not in BLOCKED_DISCOVERY_TAGS
    ]


def video_url(video: Dict[str, Any]) -> Optional[str]:
    direct = first(video, "url", "video_url", "web_url", "share_url")
    if isinstance(direct, str) and direct.startswith("http"):
        return direct
    author = first(video, "author_handle", "handle", "username", "unique_id")
    vid = video_id(video)
    if author and vid:
        return f"https://www.tiktok.com/@{str(author).lstrip('@')}/video/{vid}"
    return None


def video_id(video: Dict[str, Any]) -> Optional[str]:
    value = first(video, "id", "video_id", "post_id", "aweme_id")
    if value is not None:
        return str(value)
    url = first(video, "url", "video_url", "web_url", "share_url")
    if url:
        match = re.search(r"/video/(\d+)", str(url))
        if match:
            return match.group(1)
    return None


def fallback_video_key(video: Dict[str, Any]) -> str:
    raw = "|".join([
        str(video_url(video) or ""),
        str(first(video, "caption", "desc", "description", default="")),
        str(first(video, "create_time", "created_at", "timestamp", default="")),
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def normalize_video(video: Dict[str, Any], source: str, own_account: bool = False) -> Dict[str, Any]:
    vid = video_id(video)
    url = video_url(video)
    key = vid or fallback_video_key(video)
    caption = str(first(video, "caption", "desc", "description", "text", default="") or "")
    views = safe_int(first(video, "views", "view_count", "play_count", "plays"))
    likes = safe_int(first(video, "likes", "like_count", "digg_count"))
    comments = safe_int(first(video, "comments", "comment_count"))
    shares = safe_int(first(video, "shares", "share_count"))
    duration = safe_float(first(video, "duration", "video_duration", "duration_seconds"))
    created_raw = first(video, "create_time", "created_at", "published_at", "timestamp", "createTime")
    created = parse_datetime(created_raw)
    return {
        "video_key": key,
        "video_id": vid,
        "url": url,
        "source": source,
        "own_account": bool(own_account),
        "caption": caption,
        "views": views,
        "likes": likes,
        "comments": comments,
        "shares": shares,
        "duration": duration,
        "created_at": created.isoformat() if created else None,
        "hashtags": extract_hashtags(caption),
    }


def hours_old(item: Dict[str, Any]) -> float:
    created = parse_datetime(item.get("created_at"))
    if not created:
        return 24.0 * 30.0
    return max((utc_now() - created).total_seconds() / 3600.0, 1.0)


def calculate_scores(item: Dict[str, Any]) -> Dict[str, float]:
    views = max(item.get("views", 0), 0)
    likes = max(item.get("likes", 0), 0)
    comments = max(item.get("comments", 0), 0)
    shares = max(item.get("shares", 0), 0)
    age_h = hours_old(item)
    engagement_rate = ((likes + comments + (shares * 2)) / views) if views else 0.0
    views_per_hour = views / age_h if views else 0.0
    recency = math.exp(-age_h / (24.0 * 21.0))
    view_strength = min(math.log10(views + 1) / 7.0, 1.0)
    velocity_strength = min(math.log10(views_per_hour + 1) / 5.0, 1.0)
    engagement_strength = min(engagement_rate / 0.15, 1.0)
    trend_score = 100.0 * (
        0.34 * velocity_strength
        + 0.30 * engagement_strength
        + 0.22 * recency
        + 0.14 * view_strength
    )
    return {
        "engagement_rate": round(engagement_rate, 6),
        "views_per_hour": round(views_per_hour, 2),
        "recency_score": round(recency, 6),
        "trend_score": round(trend_score, 2),
    }


def init_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS videos (
            video_key TEXT PRIMARY KEY,
            video_id TEXT,
            url TEXT,
            source TEXT,
            own_account INTEGER NOT NULL DEFAULT 0,
            caption TEXT,
            views INTEGER DEFAULT 0,
            likes INTEGER DEFAULT 0,
            comments INTEGER DEFAULT 0,
            shares INTEGER DEFAULT 0,
            duration REAL DEFAULT 0,
            created_at TEXT,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            engagement_rate REAL DEFAULT 0,
            views_per_hour REAL DEFAULT 0,
            recency_score REAL DEFAULT 0,
            trend_score REAL DEFAULT 0,
            transcript TEXT,
            beats_json TEXT,
            ai_topic TEXT,
            ai_hook_type TEXT,
            ai_summary TEXT,
            ai_model TEXT,
            analysed_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS video_hashtags (
            video_key TEXT NOT NULL,
            hashtag TEXT NOT NULL,
            PRIMARY KEY (video_key, hashtag)
        )
        """
    )
    conn.commit()
    return conn


def already_analysed(conn: sqlite3.Connection, key: str) -> bool:
    row = conn.execute("SELECT analysed_at, transcript FROM videos WHERE video_key = ?", (key,)).fetchone()
    return bool(row and row["analysed_at"] and row["transcript"])


def upsert_metadata(conn: sqlite3.Connection, item: Dict[str, Any]) -> None:
    scores = calculate_scores(item)
    item.update(scores)
    now = iso_now()
    conn.execute(
        """
        INSERT INTO videos (
            video_key, video_id, url, source, own_account, caption,
            views, likes, comments, shares, duration, created_at,
            first_seen_at, last_seen_at, engagement_rate,
            views_per_hour, recency_score, trend_score
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(video_key) DO UPDATE SET
            video_id=excluded.video_id,
            url=excluded.url,
            source=excluded.source,
            own_account=excluded.own_account,
            caption=excluded.caption,
            views=excluded.views,
            likes=excluded.likes,
            comments=excluded.comments,
            shares=excluded.shares,
            duration=excluded.duration,
            created_at=COALESCE(excluded.created_at, videos.created_at),
            last_seen_at=excluded.last_seen_at,
            engagement_rate=excluded.engagement_rate,
            views_per_hour=excluded.views_per_hour,
            recency_score=excluded.recency_score,
            trend_score=excluded.trend_score
        """,
        (
            item["video_key"], item.get("video_id"), item.get("url"), item.get("source"),
            int(item.get("own_account", False)), item.get("caption", ""), item.get("views", 0),
            item.get("likes", 0), item.get("comments", 0), item.get("shares", 0),
            item.get("duration", 0), item.get("created_at"), now, now,
            item.get("engagement_rate", 0), item.get("views_per_hour", 0),
            item.get("recency_score", 0), item.get("trend_score", 0),
        ),
    )
    for tag in item.get("hashtags", []):
        conn.execute(
            "INSERT OR IGNORE INTO video_hashtags(video_key, hashtag) VALUES (?, ?)",
            (item["video_key"], tag),
        )


def strip_json_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def parse_ai_json(text: str) -> Optional[Dict[str, Any]]:
    cleaned = strip_json_fence(text)
    try:
        data = json.loads(cleaned)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            try:
                data = json.loads(cleaned[start:end + 1])
                return data if isinstance(data, dict) else None
            except json.JSONDecodeError:
                return None
    return None


def beat_prompt(transcript: str, caption: str) -> str:
    return f"""
Analyse this TikTok story for STRUCTURE, not factual truth.

Return ONLY valid JSON with this schema:
{{
  "topic": "short topic label",
  "hook_type": "short hook label",
  "summary": "one-sentence structural summary",
  "beats": [
    {{
      "type": "hook|context|conflict|escalation|reveal|twist|resolution|cliffhanger|call_to_action|other",
      "text": "short paraphrase of this beat",
      "start_position": 0.0,
      "end_position": 0.0,
      "confidence": 0.0
    }}
  ]
}}

Rules:
- Analyse the FULL transcript.
- Do not force a twist, resolution, CTA, or any other beat if it is absent.
- Multiple beats of the same type are allowed.
- start_position/end_position are approximate fractions from 0.0 to 1.0.
- Keep each beat text short and paraphrased.
- Do not copy long phrases from the transcript.
- Output JSON only.

Caption:
{caption[:1000]}

Transcript:
{transcript}
""".strip()


def call_gemini(api_key: str, prompt: str) -> Optional[Dict[str, Any]]:
    if not api_key:
        return None
    url = f"{GEMINI_BASE}/models/{GEMINI_MODEL}:generateContent"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "maxOutputTokens": 2200,
        },
    }
    try:
        resp = session.post(url, params={"key": api_key}, json=payload, timeout=70)
        if resp.status_code != 200:
            print(f"⚠️ Gemini failed ({resp.status_code}): {resp.text[:220]}")
            return None
        body = resp.json()
        text = body["candidates"][0]["content"]["parts"][0]["text"]
        data = parse_ai_json(text)
        if data:
            data["_model"] = GEMINI_MODEL
        return data
    except (requests.RequestException, KeyError, IndexError, ValueError) as exc:
        print(f"⚠️ Gemini analysis error: {exc}")
        return None


def call_groq(api_key: str, prompt: str) -> Optional[Dict[str, Any]]:
    if not api_key:
        return None
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": "You are a structured content analyst. Return valid JSON only."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 2200,
        "response_format": {"type": "json_object"},
    }
    try:
        resp = session.post(
            GROQ_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=70,
        )
        if resp.status_code != 200:
            print(f"⚠️ Groq failed ({resp.status_code}): {resp.text[:220]}")
            return None
        text = resp.json()["choices"][0]["message"]["content"]
        data = parse_ai_json(text)
        if data:
            data["_model"] = GROQ_MODEL
        return data
    except (requests.RequestException, KeyError, IndexError, ValueError) as exc:
        print(f"⚠️ Groq analysis error: {exc}")
        return None


def analyse_story(transcript: str, caption: str, gemini_key: Optional[str], groq_key: Optional[str]) -> Optional[Dict[str, Any]]:
    prompt = beat_prompt(transcript, caption)
    result = call_gemini(gemini_key or "", prompt)
    if result:
        return result
    print("↪️ Gemini unavailable; trying Groq...")
    return call_groq(groq_key or "", prompt)


def clean_beats(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    allowed = {
        "hook", "context", "conflict", "escalation", "reveal", "twist",
        "resolution", "cliffhanger", "call_to_action", "other",
    }
    cleaned = []
    for beat in value:
        if not isinstance(beat, dict):
            continue
        beat_type = str(beat.get("type", "other")).strip().lower()
        if beat_type not in allowed:
            beat_type = "other"
        start = min(max(safe_float(beat.get("start_position")), 0.0), 1.0)
        end = min(max(safe_float(beat.get("end_position"), start), start), 1.0)
        confidence = min(max(safe_float(beat.get("confidence"), 0.5), 0.0), 1.0)
        cleaned.append({
            "type": beat_type,
            "text": str(beat.get("text", "")).strip()[:300],
            "start_position": round(start, 3),
            "end_position": round(end, 3),
            "confidence": round(confidence, 3),
        })
    return cleaned


def store_analysis(conn: sqlite3.Connection, item: Dict[str, Any], transcript: str, analysis: Dict[str, Any]) -> None:
    beats = clean_beats(analysis.get("beats"))
    conn.execute(
        """
        UPDATE videos
        SET transcript=?, beats_json=?, ai_topic=?, ai_hook_type=?,
            ai_summary=?, ai_model=?, analysed_at=?
        WHERE video_key=?
        """,
        (
            transcript,
            json.dumps(beats, ensure_ascii=False),
            str(analysis.get("topic", "")).strip()[:160],
            str(analysis.get("hook_type", "")).strip()[:160],
            str(analysis.get("summary", "")).strip()[:500],
            str(analysis.get("_model", "")).strip(),
            iso_now(),
            item["video_key"],
        ),
    )


def collect_candidates(api_key: str, conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    candidates: Dict[str, Dict[str, Any]] = {}
    discovery_tags = list(CORE_HASHTAGS)
    learned = conn.execute(
        """
        SELECT h.hashtag, AVG(v.trend_score) AS avg_score, COUNT(*) AS n
        FROM video_hashtags h
        JOIN videos v ON v.video_key = h.video_key
        WHERE v.own_account = 0 AND v.analysed_at IS NOT NULL
        GROUP BY h.hashtag
        HAVING COUNT(*) >= 2
        ORDER BY avg_score DESC, n DESC
        LIMIT 8
        """
    ).fetchall()
    for row in learned:
        tag = str(row["hashtag"]).lower()
        if tag not in BLOCKED_DISCOVERY_TAGS and tag not in discovery_tags:
            discovery_tags.append(tag)
    discovery_tags = discovery_tags[:12]

    for tag in discovery_tags:
        for raw in get_hashtag_videos(api_key, tag, VIDEOS_PER_HASHTAG):
            item = normalize_video(raw, f"#{tag}", False)
            if item.get("url"):
                current = candidates.get(item["video_key"])
                if current is None or item["views"] > current["views"]:
                    candidates[item["video_key"]] = item

    for handle in SEED_HANDLES:
        for raw in get_profile_videos(api_key, handle, VIDEOS_PER_HANDLE):
            item = normalize_video(raw, f"@{handle}", False)
            if item.get("url"):
                current = candidates.get(item["video_key"])
                if current is None or item["views"] > current["views"]:
                    candidates[item["video_key"]] = item

    for raw in get_profile_videos(api_key, OWN_HANDLE, OWN_VIDEO_LIMIT):
        item = normalize_video(raw, f"@{OWN_HANDLE}", True)
        if item.get("url"):
            candidates[item["video_key"]] = item

    result = list(candidates.values())
    for item in result:
        upsert_metadata(conn, item)
    conn.commit()
    return result


def analyse_new_candidates(api_key: str, conn: sqlite3.Connection, candidates: List[Dict[str, Any]], gemini_key: Optional[str], groq_key: Optional[str]) -> None:
    external = [
        item for item in candidates
        if not item["own_account"] and not already_analysed(conn, item["video_key"])
    ]
    own = [
        item for item in candidates
        if item["own_account"] and not already_analysed(conn, item["video_key"])
    ]
    external.sort(key=lambda x: x.get("trend_score", 0), reverse=True)
    own.sort(key=lambda x: (x.get("created_at") or "", x.get("views", 0)), reverse=True)
    selected = external[:MAX_NEW_EXTERNAL_TRANSCRIPTS] + own[:MAX_NEW_OWN_TRANSCRIPTS]

    print(f"📊 {len(candidates)} candidates seen; {len(selected)} new videos selected for transcript analysis.")
    for index, item in enumerate(selected, start=1):
        print(f"🧠 [{index}/{len(selected)}] {item['source']} score={item.get('trend_score', 0):.1f}")
        transcript = get_transcript(api_key, item["url"])
        if not transcript or len(transcript.split()) < MIN_TRANSCRIPT_WORDS:
            print("   ↳ No usable transcript; skipping.")
            continue
        analysis = analyse_story(transcript, item.get("caption", ""), gemini_key, groq_key)
        if not analysis:
            print("   ↳ AI analysis failed; video remains eligible for a future retry.")
            continue
        store_analysis(conn, item, transcript, analysis)
        conn.commit()
        time.sleep(0.15)


def row_to_example(row: sqlite3.Row) -> Dict[str, Any]:
    try:
        beats = json.loads(row["beats_json"] or "[]")
    except json.JSONDecodeError:
        beats = []
    return {
        "video_id": row["video_id"],
        "url": row["url"],
        "source": row["source"],
        "own_account": bool(row["own_account"]),
        "topic": row["ai_topic"],
        "hook_type": row["ai_hook_type"],
        "summary": row["ai_summary"],
        "views": row["views"],
        "likes": row["likes"],
        "comments": row["comments"],
        "shares": row["shares"],
        "engagement_rate": round(row["engagement_rate"] or 0, 6),
        "views_per_hour": round(row["views_per_hour"] or 0, 2),
        "trend_score": round(row["trend_score"] or 0, 2),
        "duration": row["duration"],
        "created_at": row["created_at"],
        "caption": row["caption"],
        "beats": beats,
        "full_transcript": row["transcript"],
    }


def export_files(conn: sqlite3.Connection) -> None:
    analysed = conn.execute(
        """
        SELECT * FROM videos
        WHERE analysed_at IS NOT NULL AND transcript IS NOT NULL
        ORDER BY trend_score DESC, views DESC
        """
    ).fetchall()
    if not analysed:
        print("⚠️ No analysed videos available yet; export files left unchanged.")
        return

    external = [row for row in analysed if not row["own_account"]]
    own = [row for row in analysed if row["own_account"]]
    export_rows = external[:MAX_EXPORT_EXAMPLES]
    with open(STYLE_EXAMPLES_FILE, "w", encoding="utf-8") as f:
        json.dump([row_to_example(r) for r in export_rows], f, indent=2, ensure_ascii=False)

    hashtag_rows = conn.execute(
        """
        SELECT h.hashtag, COUNT(*) AS uses, AVG(v.trend_score) AS avg_score
        FROM video_hashtags h
        JOIN videos v ON v.video_key = h.video_key
        WHERE v.own_account = 0 AND v.analysed_at IS NOT NULL
        GROUP BY h.hashtag
        ORDER BY avg_score DESC, uses DESC
        LIMIT 20
        """
    ).fetchall()
    hashtags = [
        row["hashtag"] for row in hashtag_rows
        if row["hashtag"].lower() not in BLOCKED_DISCOVERY_TAGS
    ]
    with open(TRENDING_HASHTAGS_FILE, "w", encoding="utf-8") as f:
        json.dump(hashtags, f, indent=2)

    valid_wpm = []
    for row in external[:60]:
        duration = safe_float(row["duration"])
        transcript = row["transcript"] or ""
        words = len(transcript.split())
        if duration > 5 and words >= MIN_TRANSCRIPT_WORDS:
            wpm = words / duration * 60
            if 60 <= wpm <= 240:
                valid_wpm.append(wpm)
    if valid_wpm:
        weighted = sorted(valid_wpm)
        median = weighted[len(weighted) // 2]
        with open(TARGET_PACE_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "target_wpm": round(median, 1),
                "avg_wpm": round(sum(valid_wpm) / len(valid_wpm), 1),
                "sample_size": len(valid_wpm),
            }, f, indent=2)

    beat_counter = Counter()
    hook_counter = Counter()
    topic_counter = Counter()
    for row in external[:80]:
        if row["ai_hook_type"]:
            hook_counter[row["ai_hook_type"]] += 1
        if row["ai_topic"]:
            topic_counter[row["ai_topic"]] += 1
        try:
            for beat in json.loads(row["beats_json"] or "[]"):
                beat_type = beat.get("type")
                if beat_type:
                    beat_counter[beat_type] += 1
        except json.JSONDecodeError:
            pass

    summary = {
        "generated_at": iso_now(),
        "database_video_count": len(analysed),
        "external_analysed": len(external),
        "own_analysed": len(own),
        "trend_window_days": CURRENT_TREND_DAYS,
        "hot_window_days": HOT_TREND_DAYS,
        "top_topics": topic_counter.most_common(10),
        "top_hook_types": hook_counter.most_common(10),
        "common_story_beats": beat_counter.most_common(12),
        "top_hashtags": hashtags[:12],
        "top_examples": [
            {
                "video_id": r["video_id"],
                "topic": r["ai_topic"],
                "hook_type": r["ai_hook_type"],
                "trend_score": round(r["trend_score"] or 0, 2),
                "duration": r["duration"],
            }
            for r in external[:5]
        ],
    }
    with open(TREND_SUMMARY_FILE, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    notes = [
        "CURRENT LEARNING SUMMARY",
        f"Analysed external videos: {len(external)}",
        f"Analysed own videos: {len(own)}",
        "",
        "Most common strong-story beats: " + ", ".join(f"{name} ({count})" for name, count in beat_counter.most_common(8)),
        "Most common hook types: " + ", ".join(f"{name} ({count})" for name, count in hook_counter.most_common(6)),
        "Strong topics: " + ", ".join(f"{name} ({count})" for name, count in topic_counter.most_common(6)),
        "",
        "Generation rule: use these as patterns, not templates. Do not copy source wording.",
    ]
    Path(STYLE_NOTES_FILE).write_text("\n".join(notes), encoding="utf-8")
    print(f"✅ Exported {len(export_rows)} generator-facing style examples.")
    print(f"✅ Database retains {len(analysed)} analysed videos for long-term learning.")


def main() -> None:
    social_key = os.getenv("SOCIALCRAWL_API_KEY")
    gemini_key = os.getenv("GEMINI_API_KEY")
    groq_key = os.getenv("GROQ_API_KEY")
    if not social_key:
        raise ValueError("❌ SOCIALCRAWL_API_KEY is missing.")
    if not gemini_key and not groq_key:
        raise ValueError("❌ Set GEMINI_API_KEY or GROQ_API_KEY for transcript analysis.")

    print(f"🤖 Primary analysis model: {GEMINI_MODEL}")
    print(f"🛟 Fallback analysis model: {GROQ_MODEL}")
    conn = init_db()
    try:
        candidates = collect_candidates(social_key, conn)
        analyse_new_candidates(social_key, conn, candidates, gemini_key, groq_key)
        export_files(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
