"""Növbə elementlərinin "dərc olundu" vəziyyəti ayrıca fayllarda: state/<növbə>__<id>.txt.
Növbə faylları (ig_queue.json, comment_queue.json) yalnız publish_all tərəfindən əlavə olunur; gözətçi onlara yazmır,
ona görə iki tərəf eyni vaxtda push etsə də konflikt olmur."""
from pathlib import Path

STATE = Path(__file__).resolve().parent / "state"


def _f(queue, item_id):
    return STATE / f"{queue}__{item_id}.txt"


def apply(queue, items):
    """Fayldakı vəziyyəti elementlərə köçürür (növbədəki köhnə "done" də qüvvədədir)."""
    for i in items:
        f = _f(queue, i["id"])
        if not i.get("done") and f.exists():
            i["done"] = f.read_text(encoding="utf-8").strip()
    return items


def save(queue, items):
    STATE.mkdir(exist_ok=True)
    for i in items:
        if i.get("done"):
            f = _f(queue, i["id"])
            if not f.exists():
                f.write_text(str(i["done"]) + "\n", encoding="utf-8")
