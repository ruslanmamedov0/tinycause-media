"""YouTube şərh növbəsi -> video açılandan sonra öz kanalımızdan şərh yazır (GitHub Actions, kompüter sönülü olsa da).

comment_queue.json: [{"id","channel","video","at_baku","text","done"}]
  channel: "steelmind" (Tiny Cause EN) və ya "kucuksebep" (Küçük Sebep TR)
Vaxtı çatmış hər element üçün: video public-dirsə və öz şərhimiz yoxdursa, şərh yazılır, "done" doldurulur,
Telegram-a xəbər gedir. Video hələ private-dirsə, növbəti işə salınmada yenidən yoxlanır; 24 saatdan çox
private qalarsa, buraxılır (Telegram ❌).

Açarlar: YT_WRITE (iki kanalın OAuth tokeni, youtube.force-ssl) və CLOUD_SECRET (Telegram) mühit dəyişənlərində.
python yt_comment.py [--yoxla]   # --yoxla: heç nə yazma, yalnız nə ediləcəyini göstər
"""
import json, os, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

import state

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = Path(__file__).resolve().parent
QUEUE = HERE / "comment_queue.json"
GIVE_UP = timedelta(hours=24)
NAMES = {"steelmind": "Tiny Cause", "kucuksebep": "Küçük Sebep"}


def tg(text):
    try:
        sec = json.loads(os.environ["CLOUD_SECRET"])["telegram"]
        requests.post(f"https://api.telegram.org/bot{sec['token']}/sendMessage",
                      data={"chat_id": sec["chat_id"], "text": text}, timeout=30)
    except Exception as e:  # Telegram xətası şərhi dayandırmamalıdır
        print("telegram xətası:", e)


_yt = {}


def yt(channel):
    if channel not in _yt:
        info = json.loads(os.environ["YT_WRITE"])[channel]
        c = Credentials.from_authorized_user_info(info)
        c.refresh(Request())
        _yt[channel] = build("youtube", "v3", credentials=c, cache_discovery=False)
    return _yt[channel]


def post(item, dry):
    """Qaytarır: ("ok", şərh id) | ("wait", status) | ("skip", səbəb)."""
    y = yt(item["channel"])
    items = y.videos().list(part="status", id=item["video"]).execute().get("items", [])
    if not items:
        return "skip", "video tapılmadı"
    st = items[0]["status"]["privacyStatus"]
    if st != "public":
        return "wait", st
    me = y.channels().list(part="id", mine=True).execute()["items"][0]["id"]
    threads = y.commentThreads().list(part="snippet", videoId=item["video"], maxResults=100).execute().get("items", [])
    if any(t["snippet"]["topLevelComment"]["snippet"].get("authorChannelId", {}).get("value") == me for t in threads):
        return "skip", "öz şərhimiz artıq var"
    if dry:
        return "ok", "(yoxla: yazılmadı)"
    r = y.commentThreads().insert(part="snippet", body={"snippet": {"videoId": item["video"], "topLevelComment": {
        "snippet": {"textOriginal": item["text"]}}}}).execute()
    return "ok", r["id"]


def main():
    dry = "--yoxla" in sys.argv
    q = state.apply("comment", json.loads(QUEUE.read_text(encoding="utf-8")) if QUEUE.exists() else [])
    now = datetime.now(timezone.utc)
    fails = 0
    try:
        for item in q:
            if item.get("done"):
                continue
            at = datetime.fromisoformat(item["at_baku"])
            if at > now:
                continue
            name = NAMES.get(item["channel"], item["channel"])
            try:
                kind, info = post(item, dry)
            except Exception as e:
                fails += 1
                print("XƏTA", item["id"], str(e)[:300])
                tg(f"❌ YouTube şərhi {name}: {item['id']} — {str(e)[:200]}")
                continue
            print(item["id"], kind, info)
            if kind == "wait":
                if now - at > GIVE_UP and not dry:
                    item["done"] = f"buraxıldı: {GIVE_UP} sonra hələ {info}"
                    tg(f"❌ YouTube şərhi {name}: {item['id']} buraxıldı, video hələ {info}")
                continue
            if dry:
                continue
            item["done"] = f"{now:%Y-%m-%d %H:%M}Z {kind}: {info}"
            if kind == "ok":
                tg(f"💬 YouTube şərhi yazıldı — {name}: https://youtu.be/{item['video']}")
    finally:
        if not dry:
            state.save("comment", q)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
