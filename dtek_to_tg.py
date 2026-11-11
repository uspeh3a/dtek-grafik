import asyncio, io, json, os, datetime as dt
import requests
from PIL import Image, ImageDraw
from curl_cffi.requests import AsyncSession
from dtek_client import DtekClient
from dtek_client.browser_auth import get_cleared_cookies

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID   = os.environ["CHAT_ID"]
GROUP     = "GPV2.2"
CITY      = os.environ["CITY"]
STREET    = os.environ["STREET"]
HOUSE     = os.environ["HOUSE"]
BASE = "https://www.dtek-oem.com.ua"

HERE  = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "last_slots.json")

COLORS = {"yes": "#4caf50", "no": "#e53935", "maybe": "#ffb300",
          "first": "#ff7043", "second": "#ff7043",
          "mfirst": "#ffb300", "msecond": "#ffb300"}


async def fetch_slots():
    url = f"{BASE}/ua/shutdowns"
    cookies, csrf = await get_cleared_cookies(url)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "uk,en;q=0.9",
        "Origin": BASE, "Referer": url,
        "X-Requested-With": "XMLHttpRequest",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    }
    if csrf:
        headers["X-CSRF-Token"] = csrf
    session = AsyncSession(timeout=20.0, headers=headers, cookies=cookies,
                           impersonate="chrome120")
    async with DtekClient("oem", ajax_url=f"{BASE}/ua/ajax", session=session) as c:
        resp = await c.get_home_num(CITY, STREET)
        return resp.fact.get_group_today(GROUP)


def snapshot(slots):
    return {k: str(getattr(v, "value", v)).lower() for k, v in slots.items()}


def intervals(snap):
    hrs = sorted(int(k) for k, v in snap.items() if v == "no")
    res, start, prev = [], None, None
    for h in hrs:
        if start is None:
            start = prev = h
        elif h == prev + 1:
            prev = h
        else:
            res.append((start, prev))
            start = prev = h
    if start is not None:
        res.append((start, prev))
    return [f"{s-1:02d}:00–{e:02d}:00" for s, e in res]


def draw(slots):
    W, H, left = 1000, 170, 20
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    now = dt.datetime.now()
    d.text((left, 10), f"Group 2.2 - {now:%d.%m.%Y %H:%M}", fill="black")
    cw = (W - 2 * left) / 24
    items = sorted(slots.items(), key=lambda kv: int(kv[0]))
    for i, (k, st) in enumerate(items):
        x = left + i * cw
        col = COLORS.get(str(getattr(st, "value", st)).lower(), "#bdbdbd")
        d.rectangle([x, 40, x + cw - 2, 100], fill=col)
        d.text((x + 3, 108), f"{i:02d}", fill="black")
    d.text((left, 135), "green = power, red = outage, yellow = maybe", fill="black")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)
    return buf


def send(buf, caption):
    r = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
        data={"chat_id": CHAT_ID, "caption": caption},
        files={"photo": ("schedule.png", buf)}, timeout=30)
    r.raise_for_status()


if __name__ == "__main__":
    slots = asyncio.run(fetch_slots())
    snap = snapshot(slots)

    if os.environ.get("DRY_RUN"):
        print(slots)
        raise SystemExit

    today = dt.date.today().isoformat()
    old = {}
    if os.path.exists(STATE):
        with open(STATE, encoding="utf-8") as f:
            old = json.load(f)

    if old.get("date") == today and old.get("slots") == snap:
        print("без змін")
        raise SystemExit

    iv = intervals(snap)
    text = "\n".join("🕯 " + x for x in iv) if iv else "Відключень немає"
    send(draw(slots), "Графік відключень, група 2.2\n" + text)

    with open(STATE, "w", encoding="utf-8") as f:
        json.dump({"date": today, "slots": snap}, f, ensure_ascii=False)
    print("надіслано")
