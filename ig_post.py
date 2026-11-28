"""Instagram Reels növbəsi -> dərc (GitHub Actions-da işləyir, kompüter sönülü olsa da).

ig_queue.json: [{"id","lang","at_baku","asset","caption","done"}]. Vaxtı çatmış (və 6 saatdan köhnə olmayan)
ilk dərc olunmamış element götürülür, video GitHub Release "ig-videos"-dan endirilir, Instagram-a yüklənib dərc
edilir, nəticə Telegram-a göndərilir və "done" yazılır (workflow faylı commit edir).

Açarlar: IG_TOKEN (sistem istifadəçisi tokeni) və CLOUD_SECRET (Telegram üçün) mühit dəyişənlərində.
python ig_post.py [--yoxla]   # --yoxla: yüklə və emal et, amma dərc etmə
"""
import json, os, sys, time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

import state

HERE = Path(__file__).resolve().parent
QUEUE = HERE / "ig_queue.json"
V = "v21.0"
G = f"https://graph.facebook.com/{V}"
ACCOUNTS = {"en": ("17841432548170343", "@tinycause0"), "tr": ("17841412711837590", "@kucuksebep0")}
GRACE = timedelta(hours=6)
PUBLIC = "https://github.com/ruslanmamedov0/tinycause-media/releases/download/videos"
TOKEN = os.environ["IG_TOKEN"].strip()


def tg(text):
    try:
        sec = json.loads(os.environ["CLOUD_SECRET"])["telegram"]
        requests.post(f"https://api.telegram.org/bot{sec['token']}/sendMessage",
                      data={"chat_id": sec["chat_id"], "text": text}, timeout=30)
    except Exception as e:  # Telegram xətası dərci dayandırmamalıdır
        print("telegram xətası:", e)


def api(method, path, **params):
    params["access_token"] = TOKEN
    r = requests.request(method, f"{G}/{path}", params=params if method == "GET" else None,
                         data=params if method != "GET" else None, timeout=60)
    j = r.json()
    if not r.ok or "error" in j:
        raise RuntimeError(f"API {r.status_code} ({path.split('/')[-1]}): {j.get('error', {}).get('message', j)}")
    return j


def already_posted(ig, caption):
    """İkiqat dərcin qarşısı: son dərclərdə eyni başlıq varsa, True."""
    first = caption.split("\n")[0]
    for m in api("GET", f"{ig}/media", fields="caption,permalink", limit=10).get("data", []):
        if (m.get("caption") or "").split("\n")[0] == first:
            return m.get("permalink") or "?"
    return None


def publish(item, dry):
    ig, handle = ACCOUNTS[item["lang"]]
    link = already_posted(ig, item["caption"])
    if link:
        return link, "artıq dərc olunub"
    # ictimai link (birbaşa böyük fayl yükləməsi Instagram-da ProcessingFailedError verir)
    url = f"{PUBLIC}/{item['asset']}"
    c = api("POST", f"{ig}/media", media_type="REELS", video_url=url, caption=item["caption"], share_to_feed="true")
    for _ in range(90):
        s = api("GET", c["id"], fields="status_code,status")
        if s["status_code"] == "FINISHED":
            break
        if s["status_code"] in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"emal: {s.get('status')}")
        time.sleep(10)
    else:
        raise RuntimeError("emal 15 dəqiqədə bitmədi")
    if dry:
        return None, "yoxlama OK (link ilə emal olundu, dərc edilmədi)"
    m = api("POST", f"{ig}/media_publish", creation_id=c["id"])
    return api("GET", m["id"], fields="permalink").get("permalink"), "dərc edildi"


def main():
    dry = "--yoxla" in sys.argv
    q = state.apply("ig", json.loads(QUEUE.read_text(encoding="utf-8")))
    now = datetime.now(timezone.utc)
    due = [i for i in q if not i["done"] and datetime.fromisoformat(i["at_baku"]) <= now]
    if dry:
        due = due or [next(i for i in q if not i["done"])]
    if not due:
        print("vaxtı çatmış dərc yoxdur")
        return
    try:
        run(q, due, now, dry)
    finally:
        if not dry:
            state.save("ig", q)


def run(q, due, now, dry):
    for item in due:
        handle = ACCOUNTS[item["lang"]][1]
        late = now - datetime.fromisoformat(item["at_baku"])
        if late > GRACE and not dry:  # GitHub cron saatlarla gecikə bilir: buraxmırıq, gec də olsa dərc edirik
            tg(f"⏰ Instagram {handle}: {item['id']} {late} gecikmə ilə dərc olunur (gözətçi gecikdi)")
        try:
            link, note = publish(item, dry)
        except Exception as e:
            print("XƏTA:", e)
            tg(f"❌ Instagram {handle}: {item['id']} alınmadı: {e}")
            if not dry:
                raise
            return
        print(item["id"], note, link)
        if dry:
            tg(f"🧪 Instagram {handle}: {item['id']} {note}")
            return
        item["done"] = f"{now:%Y-%m-%d %H:%M} UTC {link}"
        tg(f"📸 Instagram {handle}: {item['id']} {note}\n{link}")


if __name__ == "__main__":
    main()
