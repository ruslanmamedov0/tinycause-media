"""Gözətçi: Instagram Reels və YouTube şərhlərini DƏQİQ vaxtında dərc edir (kompüter lazım deyil).
GitHub-un "schedule" funksiyası saatlarla gecikir/atlayır, ona görə bu proses özü ~5.6 saat oyaq qalır,
hər dəqiqə növbəni yoxlayır, sonda özünü yenidən işə salır (workflow_dispatch). Zəncir qırılsa, watcher.yml-dakı
ehtiyat cron onu yenidən başladır.
Vaxtı çatan element olanda ig_post.py / yt_comment.py çağırılır; nəticə state/ qovluğuna yazılıb push olunur."""
import json, os, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path

import state

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = Path(__file__).resolve().parent
RUN_FOR = float(os.environ.get("WATCH_HOURS", "5.6")) * 3600
RETRY_AFTER = 15 * 60
MAX_TRIES = 6
QUEUES = {"ig": ("ig_queue.json", "ig_post.py"), "comment": ("comment_queue.json", "yt_comment.py")}


def sh(*cmd, check=False):
    r = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and r.returncode:
        raise RuntimeError(f"{cmd[0]} {cmd[1] if len(cmd) > 1 else ''}: {(r.stderr or r.stdout)[-300:]}")
    return r


def log(msg):
    print(f"{datetime.now(timezone.utc):%H:%M:%S} {msg}", flush=True)


def due_items(qname):
    qf = HERE / QUEUES[qname][0]
    if not qf.exists():
        return []
    q = state.apply(qname, json.loads(qf.read_text(encoding="utf-8")))
    now = datetime.now(timezone.utc)
    return [i["id"] for i in q if not i.get("done") and datetime.fromisoformat(i["at_baku"]) <= now]


def sync_push():
    sh("git", "checkout", "--", "ig_queue.json", "comment_queue.json")
    sh("git", "add", "state")
    if sh("git", "diff", "--cached", "--quiet").returncode == 0:
        return
    sh("git", "commit", "-q", "-m", f"gözətçi: vəziyyət {datetime.now(timezone.utc):%F %H:%M}")
    for _ in range(5):
        sh("git", "pull", "-q", "--rebase")
        if sh("git", "push", "-q").returncode == 0:
            return
        time.sleep(5)
    log("XƏTA: push alınmadı")


def main():
    start = time.time()
    tries, last_try, last_beat = {}, {}, 0
    log(f"gözətçi başladı, {RUN_FOR / 3600:.1f} saat")
    while time.time() - start < RUN_FOR:
        sh("git", "pull", "-q", "--rebase")
        for qname, (_, script) in QUEUES.items():
            ids = due_items(qname)
            ready = [i for i in ids if tries.get((qname, i), 0) < MAX_TRIES and time.time() - last_try.get((qname, i), 0) > (RETRY_AFTER if tries.get((qname, i)) else 0)]
            if not ready:
                continue
            log(f"{qname}: vaxtı çatıb {ready}")
            r = sh(sys.executable, script)
            print((r.stdout + r.stderr)[-1500:], flush=True)
            left = set(due_items(qname))
            for i in ready:
                if i in left:  # hələ dərc olunmayıb (xəta və ya video hələ public deyil)
                    if qname == "ig" or r.returncode:
                        tries[(qname, i)] = tries.get((qname, i), 0) + 1
                    last_try[(qname, i)] = time.time()
            sync_push()
        if time.time() - last_beat > 1800:
            log("oyaqdır")
            last_beat = time.time()
        time.sleep(60)
    log("vaxt bitdi, növbəti gözətçi işə salınır")
    r = sh("gh", "workflow", "run", "watcher.yml", "-R", os.environ.get("GITHUB_REPOSITORY", ""))
    log(f"yenidən başlatma: {r.returncode} {(r.stdout + r.stderr).strip()[:200]}")


if __name__ == "__main__":
    main()
