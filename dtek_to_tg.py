import asyncio, io, json, os, datetime as dt
import requests
from PIL import Image, ImageDraw, ImageFont
from curl_cffi.requests import AsyncSession
from dtek_client import DtekClient
from dtek_client.browser_auth import get_cleared_cookies

# --- настройки (на GitHub берутся из секретов, на ПК из этих строк) ---
BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID   = os.environ["CHAT_ID"]
GROUP     = "GPV2.2"
CITY      = os.environ["CITY"]
STREET    = os.environ["STREET"]
HOUSE     = os.environ["HOUSE"]
BASE      = "https://www.dtek-oem.com.ua"
# ----------------------------------------------------------------------

HERE  = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "last_slots.json")

HALF = {
    "yes": ("on", "on"), "no": ("off", "off"),
    "first": ("off", "on"), "second": ("on", "off"),
    "maybe": ("maybe", "maybe"),
    "mfirst": ("maybe", "on"), "msecond": ("on", "maybe"),
}
HCOLOR = {"on": "#4caf50", "off": "#e53935", "maybe": "#ffb300"}


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


def half_states(snap):
    out = []
    for k in sorted(snap, key=int):
        out += HALF.get(snap[k], ("on", "on"))
    return out


def runs(states, target):
    res, start = [], None
    for i, st in enumerate(states + [None]):
        if st == target and start is None:
            start = i
        elif st != target and start is not None:
            res.append((start, i))
            start = None
    f = lambda m: f"{m // 60:02d}:{m % 60:02d}"
    return [f"{f(s * 30)}–{f(e * 30)}" for s, e in res]


TXT = {
    "title": "График отключений, очередь 2.2",
    "tab": "на сегодня",
    "upd": "Обновлено:",
    "hours": "Часовые\nпромежутки",
    "legend": ["Свет есть", "Света нет", "Света не будет первые 30 мин.",
               "Света не будет вторые 30 мин.", "Возможно"],
}

FONT_DIRS = ["C:/Windows/Fonts/", "/usr/share/fonts/truetype/dejavu/",
             "/usr/share/fonts/truetype/liberation/"]
FONT_REG = ["arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"]
FONT_BOLD = ["arialbd.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"]


def font(size, bold=False):
    for d in FONT_DIRS:
        for name in (FONT_BOLD if bold else FONT_REG):
            try:
                return ImageFont.truetype(d + name, size)
            except OSError:
                pass
    return ImageFont.load_default()


def bolt(d, cx, cy, s, fill, outline=None):
    """Молния со сглаживанием: рисуется крупно и уменьшается."""
    k = 8
    pts = [(0.15, -1), (-0.65, 0.1), (-0.05, 0.1), (-0.2, 1), (0.65, -0.25), (0.05, -0.25)]
    size = int(2 * s + 8)
    left, top = round(cx - size / 2), round(cy - size / 2)
    px, py = (cx - left) * k, (cy - top) * k
    P = [(px + x * s * k, py + y * s * k) for x, y in pts]
    big = Image.new("RGBA", (size * k, size * k), (0, 0, 0, 0))
    bd = ImageDraw.Draw(big)
    bd.polygon(P, fill=fill)
    bd.line(P + [P[0]], fill=fill, width=int(k * 1.2), joint="curve")   # скругляет углы
    if outline:
        bd.line(P + [P[0]], fill=outline, width=k, joint="curve")
    small = big.resize((size, size), Image.LANCZOS)
    d._image.paste(small, (left, top), small)


def table_image(slots):
    snap = snapshot(slots)
    ink, gray, line = "#1b2437", "#d3d4d6", "#c9cacc"
    W, H = 1090, 400
    used = set(v for k in snap for v in HALF.get(snap[k], ("on", "on")))
    if "maybe" in used:
        H += 44
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    now = dt.datetime.now()

    d.text((40, 22), TXT["title"], font=font(34, True), fill=ink)

    # вкладка с датой
    tab = f"{TXT['tab']} {now:%d.%m.%y}"
    tf = font(24, True)
    tw = int(d.textlength(tab, font=tf))
    d.rounded_rectangle([40, 82, 40 + 70 + tw, 134], radius=14, fill="#ffe600")
    bolt(d, 68, 108, 11, ink)
    d.text((92, 93), tab, font=tf, fill=ink)
    d.text((40, 160), f"{TXT['upd']} {now:%d.%m.%Y %H:%M}", font=font(17), fill="#5a6070")

    # таблица
    x0, y0, lw, cw = 40, 195, 150, 36
    hh, rh = 80, 52
    xr, yb = x0 + lw + 24 * cw, y0 + hh + rh
    d.rectangle([x0, y0, xr, yb], outline=line, width=2, fill="white")

    for i, k in enumerate(sorted(snap, key=int)):
        a, b = HALF.get(snap[k], ("on", "on"))
        x = x0 + lw + i * cw
        ya, yb2 = y0 + hh, y0 + hh + rh - 1
        mid = x + cw / 2
        for (xa, xb), st in (((x + 1, mid), a), ((mid, x + cw - 1), b)):
            if st == "off":
                d.rectangle([xa, ya + 1, xb, yb2], fill=gray)
            elif st == "maybe":
                d.rectangle([xa, ya + 1, xb, yb2], fill="#fff6bf")
        cx, cy = x + cw / 2, (ya + yb2) / 2
        if a == "off" and b == "off":
            bolt(d, cx, cy, 11, ink)
        elif a == "off" or b == "off":
            bolt(d, cx + (-8 if a == "off" else 8), cy, 10, "#ffe600", ink)
        elif a == "maybe" or b == "maybe":
            bolt(d, cx + (-8 if a == "maybe" else 8), cy, 10, "#ffffff", "#9a8f3a")

    for i in range(25):
        x = x0 + lw + i * cw
        d.line([x, y0, x, yb], fill=line, width=1)
    d.line([x0, y0 + hh, xr, y0 + hh], fill=line, width=1)
    d.rectangle([x0, y0, xr, yb], outline=line, width=2)

    d.multiline_text((x0 + 12, y0 + hh / 2 - 22), TXT["hours"], font=font(19, True),
                     fill=ink, spacing=2)

    # время начала каждого часа, повёрнутым текстом
    f = font(17, True)
    for i in range(24):
        t = f"{i:02d}:00"
        bb = d.textbbox((0, 0), t, font=f)
        w, th = bb[2] + 6, bb[3] - bb[1]
        tmp = Image.new("RGBA", (w, th + 6), (255, 255, 255, 0))
        ImageDraw.Draw(tmp).text((3, 3 - bb[1]), t, font=f, fill=ink)
        tmp = tmp.rotate(90, expand=True)
        img.paste(tmp, (int(x0 + lw + i * cw + (cw - tmp.width) / 2),
                        y0 + (hh - tmp.height) // 2), tmp)

    # легенда
    legend = TXT["legend"]
    rows = [[("on", legend[0]), ("off", legend[1]), ("first", legend[2]),
             ("second", legend[3])]]
    if "maybe" in used:
        rows.append([("maybe", legend[4])])
    for r, items in enumerate(rows):
        y, x = 350 + r * 44, 40
        for kind, label in items:
            d.rectangle([x, y, x + 34, y + 30], outline=line, fill="white")
            if kind == "off":
                d.rectangle([x + 1, y + 1, x + 34, y + 30], fill=gray)
                bolt(d, x + 17, y + 15, 8, ink)
            elif kind == "first":
                d.rectangle([x + 1, y + 1, x + 17, y + 30], fill=gray)
                bolt(d, x + 10, y + 15, 8, "#ffe600", ink)
            elif kind == "second":
                d.rectangle([x + 17, y + 1, x + 34, y + 30], fill=gray)
                bolt(d, x + 24, y + 15, 8, "#ffe600", ink)
            elif kind == "maybe":
                d.rectangle([x + 1, y + 1, x + 34, y + 30], fill="#fff6bf")
            d.text((x + 44, y + 4), label, font=font(15), fill=ink)
            x += 44 + int(d.textlength(label, font=font(15))) + 22
    return img


def draw(slots):
    img = table_image(slots)
    W, H0 = img.size
    H = max(H0, int(W / 1.8))                 # белые поля сверху и снизу
    out = Image.new("RGB", (W, H), "white")
    out.paste(img, (0, (H - H0) // 2))
    buf = io.BytesIO()
    out.save(buf, "PNG")
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
        print("без изменений")
        raise SystemExit

    st = half_states(snap)
    lines = (["🕯 " + x for x in runs(st, "off")]
             + ["❓ возможно " + x for x in runs(st, "maybe")])
    text = "\n".join(lines) if lines else "Отключений нет"
    send(draw(slots), "График отключений, группа 2.2\n" + text)

    with open(STATE, "w", encoding="utf-8") as f:
        json.dump({"date": today, "slots": snap}, f, ensure_ascii=False)
    print("отправлено")
