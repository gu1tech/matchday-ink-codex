import json
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont

from .domain import timestamp

WIDTH, HEIGHT = 296, 128
# Waveshare 2in9g: 00 black, 01 white, 10 yellow, 11 red.
PALETTE = ((0, 0, 0), (255, 255, 255), (255, 204, 0), (200, 16, 46))
FONT_DIR = Path(__file__).parent / "assets" / "fonts"
DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


@lru_cache(maxsize=96)
def font(size, weight="SemiBold"):
    return ImageFont.truetype(str(FONT_DIR / f"BarlowSemiCondensed-{weight}.ttf"), size)


def upper(text):
    return str(text).upper()


def fitted(value, size, width, minimum=9, weight="SemiBold", height=None):
    value = str(value).replace("\n", " ").strip()
    while size > minimum and (
        font(size, weight).getlength(value) > width
        or (height is not None and font(size, weight).getbbox(value, anchor="lt")[3] > height)
    ):
        size -= 1
    if font(size, weight).getlength(value) > width:
        while value and font(size, weight).getlength(value + "…") > width:
            value = value[:-1]
        value = value.rstrip() + "…"
    return value, font(size, weight)


def draw_text(
    image,
    x,
    y,
    value,
    size=12,
    color=0,
    width=280,
    weight="SemiBold",
    centered=False,
    minimum=9,
    height=None,
):
    value, face = fitted(value, size, width, minimum, weight, height)
    if centered:
        x -= face.getlength(value) / 2
    mask = Image.new("L", image.size)
    ImageDraw.Draw(mask).text((round(x), y), value, font=face, fill=255, anchor="lt")
    # Threshold once into actual device ink: no grayscale / antialias colours leak.
    image.paste(PALETTE[color], (0, 0), mask.point(lambda v: 255 if v >= 110 else 0))


def render(
    fixture, timezone="Europe/Dublin", weather=None, stale=False, ai_note=None, layout="scoreboard",
    connection=None, metrics=None,
):
    if layout not in {"stacked", "scoreboard"}:
        raise ValueError("Unknown layout")
    im = Image.new("RGB", (WIDTH, HEIGHT), PALETTE[1])
    d = ImageDraw.Draw(im)
    demo = bool(fixture and fixture["demo"])
    # Three hierarchy levels: insight, fixture, logistics. No repeated masthead.
    d.rectangle((0, 0, 295, 24), fill=PALETTE[3])
    d.rounded_rectangle((5, 1, 30, 23), radius=3, fill=PALETTE[2])
    im.paste(PALETTE[0], (8, 3, 28, 23), _openai_logo_mask())
    status = "DEMO / OLD" if stale and demo else "OLD" if stale else "DEMO" if demo else None
    status_width = 57 if stale and demo else 33 if status else 0
    if status:
        d.rectangle((WIDTH - status_width - 47, 6, WIDTH - 47, 18), outline=PALETTE[1])
        draw_text(
            im,
            WIDTH - status_width / 2 - 47,
            8,
            status,
            8,
            color=1,
            width=status_width - 4,
            centered=True,
        )
    note = "Data needs updating" if stale else ai_note or "Prediction pending"
    if metrics and not stale:
        note = (f"H{metrics['home']}% D{metrics['draw']}% A{metrics['away']}%"
                f" · Pred {metrics.get('score', '—')}")
    draw_text(im, 37, 6, note, 14, color=1, width=WIDTH - status_width - 91, minimum=12)
    draw_status_icons(im, connection, fresh=bool(fixture and not stale and not demo))
    if fixture is None:
        draw_text(
            im, 148, 52, "WAITING FOR NEXT MATCH", 21, width=278, centered=True, weight="Bold"
        )
        draw_text(im, 148, 83, "Check the fixture source", 13, centered=True)
        return im

    if layout == "stacked":
        draw_text(
            im,
            148,
            44,
            upper(fixture["home"]),
            27,
            width=278,
            centered=True,
            minimum=17,
            height=20,
            weight="Bold",
        )
        d.line((111, 68, 133, 68), fill=PALETTE[3])
        d.line((163, 68, 185, 68), fill=PALETTE[3])
        draw_text(im, 148, 65, "VS", 9, centered=True, width=20, weight="Bold")
        draw_text(
            im,
            148,
            73,
            upper(fixture["away"]),
            23,
            width=278,
            centered=True,
            minimum=15,
            height=20,
            weight="Bold",
        )
    else:
        # Equal-size type; home at left edge, away at right edge.
        names = [upper(fixture["home"]), upper(fixture["away"])]
        sizes = [fitted(name, 27, 128, minimum=13, weight="Bold")[1].size for name in names]
        size = min(sizes)
        for name, right in zip(names, (False, True)):
            value, face = fitted(name, size, 128, minimum=13, weight="Bold")
            x = 288 - face.getlength(value) if right else 8
            y = 45 - face.getbbox(value, anchor="lt")[3] // 2
            draw_text(im, x, y, value, size, width=128, weight="Bold", minimum=13)
        d.line((143, 45, 153, 45), fill=PALETTE[3], width=2)
        for key, right in (("home_standing", False), ("away_standing", True)):
            standing = fixture.get(key)
            label = (
                f"#{standing['position']} · {standing['points']} pts"
                if standing
                else "Rank / pts: —"
            )
            value, face = fitted(label, 18, 128, minimum=10)
            x = 288 - face.getlength(value) if right else 8
            draw_text(im, x, 69, value, 18, width=128, minimum=10)

    local = timestamp(fixture["kickoff"]).astimezone(ZoneInfo(timezone))
    d.rectangle((0, 96, 295, 127), fill=PALETTE[3])
    # Minimal footer: no year, timezone label, venue, weather or field labels.
    date = f"{local.day} {MONTHS[local.month - 1]} / {DAYS[local.weekday()]}"
    d.line((184, 103, 184, 121), fill=PALETTE[1])
    draw_text(im, 10, 106, date, 18, width=165, minimum=12, color=1)
    draw_text(
        im, 240, 101, local.strftime("%H:%M"), 28, width=96, centered=True, weight="Bold", color=1
    )
    return im


def encode_frame(image):
    if image.size != (WIDTH, HEIGHT):
        raise ValueError("Frame must be exactly 296x128")
    panel = [[1] * 128 for _ in range(296)]
    lookup = {p: i for i, p in enumerate(PALETTE)}
    for y in range(HEIGHT):
        for x in range(WIDTH):
            color = tuple(image.getpixel((x, y)))
            if color not in lookup:
                raise ValueError("Only the four hardware palette colours are allowed")
            panel[x][127 - y] = lookup[color]
    data = bytearray()
    for row in panel:
        for x in range(0, 128, 4):
            data.append(sum(row[x + i] << (6 - 2 * i) for i in range(4)))
    return bytes(data)


@lru_cache(maxsize=1)
def _status_icons():
    return json.loads((FONT_DIR.parent / "status-icons.json").read_text())


@lru_cache(maxsize=1)
def _openai_logo_mask():
    with Image.open(FONT_DIR.parent / "openai-20-mask.png") as image:
        return image.convert("L")


def draw_status_icons(image, connected=None, fresh=False):
    wifi = "wifi_unknown" if connected is None else "wifi_on" if connected else "wifi_off"
    for name, left in [(wifi, 263), ("data_fresh" if fresh else "data_stale", 280)]:
        for index, color in enumerate(_status_icons()[name]):
            image.putpixel((left + index % 13, 6 + index // 13), PALETTE[color])
