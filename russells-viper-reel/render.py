"""Renders the edited Russell's Viper reel.

    python3 render.py <input.mov> [output.mp4] [--preview SECONDS]

The original footage and voice are never altered: frames are only zoomed/shaken
and have graphics composited on top, and the voice track is mixed at full level
with a ducked music bed and quiet SFX underneath.

Optional real snake photos: drop assets/viper.jpg and assets/python.jpg (any
royalty-free photo) and they replace the drawn illustrations automatically.
"""
import json
import math
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

import audio
from timeline import *

HERE = os.path.dirname(os.path.abspath(__file__))
W, H, FPS = 1080, 1920, 30

YELLOW = (255, 214, 0)
RED = (235, 30, 45)
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
CARD = (18, 18, 20)

FONT_BLACK = "/usr/share/fonts/opentype/inter/InterDisplay-Black.otf"
FONT_BOLD = "/usr/share/fonts/opentype/inter/InterDisplay-Bold.otf"
FONT_EMOJI = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"
_fonts = {}


def font(size, path=FONT_BLACK):
    key = (path, size)
    if key not in _fonts:
        _fonts[key] = ImageFont.truetype(path, size)
    return _fonts[key]


# ---------- easing ----------

def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def ease_out(p):
    p = clamp(p)
    return 1 - (1 - p) ** 3


def ease_in_out(p):
    p = clamp(p)
    return 3 * p * p - 2 * p * p * p


def back_out(p, s=2.2):
    p = clamp(p) - 1
    return p * p * ((s + 1) * p + s) + 1


def pop_scale(t, start, dur=0.28):
    """0 before start, overshoots to ~1.12 then settles at 1."""
    if t < start:
        return 0.0
    return back_out((t - start) / dur)


def window_alpha(t, start, end, fin=0.12, fout=0.18):
    if t < start or t > end:
        return 0.0
    return clamp((t - start) / fin) * clamp((end - t) / fout)


# ---------- text rendering (with colour emoji) ----------

def _is_emoji(ch):
    o = ord(ch)
    return o >= 0x1F000 or 0x2600 <= o <= 0x27BF or o in (0x274C, 0x26A0, 0xFE0F, 0x2B06)


def _runs(text):
    runs, cur, cur_e = [], "", None
    for ch in text:
        if ord(ch) == 0xFE0F:  # variation selector: keep with previous emoji
            cur += ch
            continue
        e = _is_emoji(ch)
        if cur and e != cur_e:
            runs.append((cur, cur_e))
            cur = ""
        cur, cur_e = cur + ch, e
    if cur:
        runs.append((cur, cur_e))
    return runs


def _emoji_img(ch, size):
    f = ImageFont.truetype(FONT_EMOJI, 109)
    im = Image.new("RGBA", (136, 128), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((0, 0), ch, font=f, embedded_color=True)
    im = im.crop(im.getbbox() or (0, 0, 1, 1))
    s = size / 109 * 1.05
    return im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.LANCZOS)


def text_img(text, size, fill=WHITE, stroke=0, stroke_fill=BLACK, path=FONT_BLACK, shadow=True):
    """Renders one line of text (emoji allowed) to a tight RGBA image."""
    f = font(size, path)
    pieces = []
    for run, is_e in _runs(text):
        if is_e:
            for ch in run:
                if ord(ch) != 0xFE0F:
                    pieces.append(("e", _emoji_img(ch, size)))
        else:
            pieces.append(("t", run))
    pad = stroke + 12
    asc, desc = f.getmetrics()
    line_h = asc + desc
    widths = []
    for kind, p in pieces:
        widths.append(p.width + int(size * 0.12) if kind == "e" else int(f.getlength(p)))
    total_w = sum(widths) + pad * 2
    im = Image.new("RGBA", (total_w, line_h + pad * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x = pad
    for (kind, p), w in zip(pieces, widths):
        if kind == "e":
            im.alpha_composite(p, (x + int(size * 0.06), pad + (line_h - p.height) // 2 - int(size * 0.05)))
        else:
            d.text((x, pad), p, font=f, fill=fill, stroke_width=stroke, stroke_fill=stroke_fill)
        x += w
    im = im.crop(im.getbbox())
    if shadow:
        sh = Image.new("RGBA", (im.width + 40, im.height + 40), (0, 0, 0, 0))
        a = im.getchannel("A").point(lambda v: int(v * 0.85))
        blk = Image.new("RGBA", im.size, (0, 0, 0, 255))
        blk.putalpha(a)
        sh.alpha_composite(blk, (20, 26))
        sh = sh.filter(ImageFilter.GaussianBlur(8))
        sh.alpha_composite(im, (20, 20))
        im = sh
    return im


def multi_color_line(parts, size, stroke=8):
    """parts: [(text, colour), ...] on one line."""
    ims = [text_img(t, size, c, stroke, shadow=False) for t, c in parts]
    gap = int(size * 0.18)
    w = sum(i.width for i in ims) + gap * (len(ims) - 1)
    h = max(i.height for i in ims)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    x = 0
    for i in ims:
        out.alpha_composite(i, (x, h - i.height if False else (h - i.height) // 2))
        x += i.width + gap
    return add_shadow(out)


def add_shadow(im, blur=8, off=6):
    sh = Image.new("RGBA", (im.width + 40, im.height + 40), (0, 0, 0, 0))
    blk = Image.new("RGBA", im.size, (0, 0, 0, 255))
    blk.putalpha(im.getchannel("A").point(lambda v: int(v * 0.85)))
    sh.alpha_composite(blk, (20, 20 + off))
    sh = sh.filter(ImageFilter.GaussianBlur(blur))
    sh.alpha_composite(im, (20, 20))
    return sh


def paste(canvas, im, cx, cy, scale=1.0, alpha=1.0, angle=0.0):
    if scale <= 0.01 or alpha <= 0.01:
        return
    if abs(scale - 1) > 0.005:
        im = im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))), Image.BILINEAR)
    if angle:
        im = im.rotate(angle, resample=Image.BICUBIC, expand=True)
    if alpha < 0.999:
        a = im.getchannel("A").point(lambda v: int(v * alpha))
        im = im.copy()
        im.putalpha(a)
    x, y = int(cx - im.width / 2), int(cy - im.height / 2)
    if x >= canvas.width or y >= canvas.height or x + im.width <= 0 or y + im.height <= 0:
        return
    canvas.alpha_composite(im, (max(0, x), max(0, y)), (max(0, -x), max(0, -y)))


def glow(im, color, radius=18, strength=2):
    a = im.getchannel("A").filter(ImageFilter.GaussianBlur(radius))
    a = a.point(lambda v: min(255, int(v * strength)))
    g = Image.new("RGBA", im.size, color + (255,))
    g.putalpha(a)
    pad = Image.new("RGBA", im.size, (0, 0, 0, 0))
    pad.alpha_composite(g)
    pad.alpha_composite(im)
    return pad


def pad_img(im, p):
    out = Image.new("RGBA", (im.width + 2 * p, im.height + 2 * p), (0, 0, 0, 0))
    out.alpha_composite(im, (p, p))
    return out


# ---------- snake illustrations (used when no photo is supplied) ----------

def _snake_path(w, h, kind):
    n = 400
    pts = []
    for i in range(n):
        u = i / (n - 1)
        if kind == "viper":  # thick, coiled S, head raised on the right
            x = w * (0.08 + 0.78 * u)
            y = h * (0.62 + 0.18 * math.sin(u * 2.6 * math.pi + 0.4) * (1 - 0.6 * u)) - h * 0.18 * u ** 3
        else:  # python: longer, flatter undulation
            x = w * (0.06 + 0.82 * u)
            y = h * (0.58 + 0.14 * math.sin(u * 3.4 * math.pi))
        pts.append((x, y))
    return pts


def draw_snake(kind, w, h):
    """Stylised but pattern-accurate illustration: Russell's viper = chain of dark
    oval rings on tan; Indian rock python = irregular dark blotches on grey-tan."""
    S = 2
    W2, H2 = w * S, h * S
    im = Image.new("RGBA", (W2, H2), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    pts = [(x * S, y * S) for x, y in _snake_path(w, h, kind)]
    n = len(pts)
    maxw = (h * 0.16 if kind == "viper" else h * 0.12) * S
    body = (196, 160, 104) if kind == "viper" else (150, 138, 112)
    belly = (226, 205, 160) if kind == "viper" else (190, 180, 150)

    def width_at(u):
        return maxw * (0.25 + 0.75 * math.sin(math.pi * min(1, u * 1.05)) ** 0.6) if u < 0.93 else maxw * 0.55

    # body as overlapping circles (smooth tube)
    for i, (x, y) in enumerate(pts):
        r = width_at(i / (n - 1)) / 2
        d.ellipse((x - r, y - r + 3 * S, x + r, y + r + 3 * S), fill=(10, 8, 6, 255))  # outline/shadow
    for i, (x, y) in enumerate(pts):
        r = width_at(i / (n - 1)) / 2 - 2 * S
        d.ellipse((x - r, y - r, x + r, y + r), fill=body)
    for i, (x, y) in enumerate(pts):
        r = width_at(i / (n - 1)) / 2 * 0.45
        d.ellipse((x - r, y + r * 0.6, x + r, y + r * 1.4), fill=belly)

    rng = np.random.default_rng(3 if kind == "viper" else 5)
    step = 14 if kind == "viper" else 11
    for i in range(18, n - 30, step):
        u = i / (n - 1)
        x, y = pts[i]
        x2, y2 = pts[i + 1]
        ang = math.atan2(y2 - y, x2 - x)
        r = width_at(u) / 2
        nx, ny = -math.sin(ang), math.cos(ang)
        if kind == "viper":
            # central chain of oval spots: black ring, dark brown fill, pale edge
            for off, sc in ((0.0, 1.0), (-0.62, 0.55), (0.62, 0.55)):
                cx, cy = x + nx * r * off, y + ny * r * off
                a, b = r * 0.48 * sc, r * 0.36 * sc
                d.ellipse((cx - a - 2 * S, cy - b - 2 * S, cx + a + 2 * S, cy + b + 2 * S), fill=(240, 225, 190))
                d.ellipse((cx - a, cy - b, cx + a, cy + b), fill=(20, 12, 8))
                d.ellipse((cx - a * 0.7, cy - b * 0.65, cx + a * 0.7, cy + b * 0.65), fill=(110, 62, 30))
        else:
            if rng.random() < 0.85:
                cx = x + nx * r * rng.uniform(-0.4, 0.4)
                cy = y + ny * r * rng.uniform(-0.4, 0.4)
                a, b = r * rng.uniform(0.35, 0.7), r * rng.uniform(0.25, 0.5)
                poly = [(cx + a * math.cos(k) * rng.uniform(0.7, 1.2), cy + b * math.sin(k) * rng.uniform(0.7, 1.2))
                        for k in np.linspace(0, 2 * math.pi, 9)[:-1]]
                d.polygon(poly, fill=(58, 46, 34))

    # head
    hx, hy = pts[-1]
    px, py = pts[-12]
    ang = math.atan2(hy - py, hx - px)
    hl = maxw * (1.05 if kind == "viper" else 0.85)
    hw = maxw * (0.72 if kind == "viper" else 0.5)
    ca, sa = math.cos(ang), math.sin(ang)

    def tr(lx, ly):
        return (hx + lx * ca - ly * sa, hy + lx * sa + ly * ca)

    if kind == "viper":  # broad flat triangular head
        head = [tr(-hl * 0.15, -hw * 0.45), tr(hl * 0.35, -hw * 0.62), tr(hl * 0.85, -hw * 0.3),
                tr(hl, 0), tr(hl * 0.85, hw * 0.3), tr(hl * 0.35, hw * 0.62), tr(-hl * 0.15, hw * 0.45)]
    else:  # narrow elongated head
        head = [tr(-hl * 0.1, -hw * 0.5), tr(hl * 0.5, -hw * 0.55), tr(hl, -hw * 0.25),
                tr(hl * 1.05, 0), tr(hl, hw * 0.25), tr(hl * 0.5, hw * 0.55), tr(-hl * 0.1, hw * 0.5)]
    d.polygon([(x, y + 3 * S) for x, y in head], fill=(10, 8, 6))
    d.polygon(head, fill=body)
    if kind == "viper":  # V-mark and dark stripes behind eyes
        d.line([tr(hl * 0.75, 0), tr(hl * 0.15, -hw * 0.35)], fill=(40, 24, 12), width=5 * S)
        d.line([tr(hl * 0.75, 0), tr(hl * 0.15, hw * 0.35)], fill=(40, 24, 12), width=5 * S)
    else:  # python's dark arrowhead mark
        d.polygon([tr(hl * 0.95, 0), tr(hl * 0.1, -hw * 0.3), tr(hl * 0.25, 0), tr(hl * 0.1, hw * 0.3)], fill=(58, 46, 34))
    for sgn in (-1, 1):
        ex, ey = tr(hl * 0.58, sgn * hw * 0.42)
        er = hw * 0.11
        d.ellipse((ex - er, ey - er, ex + er, ey + er), fill=(230, 180, 40) if kind == "viper" else (180, 150, 90))
        d.ellipse((ex - er * 0.3, ey - er * 0.9, ex + er * 0.3, ey + er * 0.9), fill=BLACK)
    # tongue
    tx, ty = tr(hl * 1.02, 0)
    t2 = tr(hl * 1.3, 0)
    d.line([(tx, ty), t2], fill=(200, 30, 40), width=3 * S)
    d.line([t2, tr(hl * 1.42, -hw * 0.1)], fill=(200, 30, 40), width=3 * S)
    d.line([t2, tr(hl * 1.42, hw * 0.1)], fill=(200, 30, 40), width=3 * S)
    return im.resize((w, h), Image.LANCZOS)


def cover(photo, w, h):
    r = max(w / photo.width, h / photo.height)
    p = photo.resize((int(photo.width * r) + 1, int(photo.height * r) + 1), Image.LANCZOS)
    x, y = (p.width - w) // 2, (p.height - h) // 2
    return p.crop((x, y, x + w, y + h))


def snake_card(kind, w, h, label, accent, sub=None):
    """Rounded card with photo (if supplied) or illustration, plus label strip."""
    card = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), 28, fill=255)
    photo_path = os.path.join(HERE, "assets", f"{kind}.jpg")
    inner = Image.new("RGBA", (w, h), CARD + (255,))
    if os.path.exists(photo_path):
        inner.paste(cover(Image.open(photo_path).convert("RGB"), w, h))
    else:
        # dramatic radial backdrop + illustration
        bg = Image.new("RGBA", (w, h), (0, 0, 0, 255))
        rad = Image.new("L", (w, h), 0)
        ImageDraw.Draw(rad).ellipse((-w * 0.2, -h * 0.1, w * 1.2, h * 1.2), fill=90)
        rad = rad.filter(ImageFilter.GaussianBlur(60))
        tint = Image.new("RGBA", (w, h), (90, 20, 20, 255) if kind == "viper" else (40, 50, 40, 255))
        bg = Image.composite(tint, bg, rad)
        inner = bg
        inner.alpha_composite(draw_snake(kind, w, int(h * 0.92)), (0, 0))
    # label strip
    strip_h = int(h * 0.2)
    grad = Image.new("RGBA", (w, strip_h * 2), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    for y in range(strip_h * 2):
        gd.line([(0, y), (w, y)], fill=(0, 0, 0, int(230 * y / (strip_h * 2))))
    inner.alpha_composite(grad, (0, h - strip_h * 2))
    lab = text_img(label, int(h * 0.1), WHITE, 0, shadow=False)
    if lab.width > w * 0.9:
        lab = lab.resize((int(w * 0.9), int(lab.height * w * 0.9 / lab.width)), Image.LANCZOS)
    inner.alpha_composite(lab, ((w - lab.width) // 2, h - lab.height - int(h * 0.05)))
    if sub:
        s = text_img(sub, int(h * 0.06), accent, 0, shadow=False, path=FONT_BOLD)
        inner.alpha_composite(s, ((w - s.width) // 2, h - lab.height - s.height - int(h * 0.06)))
    card.paste(inner, (0, 0), mask)
    ImageDraw.Draw(card).rounded_rectangle((0, 0, w - 1, h - 1), 28, outline=accent, width=6)
    return add_shadow(card, 14, 8)


# ---------- India map ----------

def india_map(size):
    geom = json.load(open(os.path.join(HERE, "assets", "india.json")))
    lon0, lon1, lat0, lat1 = 67.5, 98.0, 6.0, 37.5
    k = math.cos(math.radians(22))
    S = 2
    sw = size * S
    sx = sw / ((lon1 - lon0) * k)
    sh = int((lat1 - lat0) * sx)
    im = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    polys = [[((lo - lon0) * k * sx, (lat1 - la) * sx) for lo, la in ring[0]] for ring in geom["coordinates"]]
    for p in polys:
        if len(p) > 2:
            d.polygon(p, fill=(120, 10, 18, 255))
    for p in polys:
        if len(p) > 2:
            d.line(p + [p[0]], fill=(255, 60, 70, 255), width=3 * S, joint="curve")
    im = im.resize((size, sh // S), Image.LANCZOS)
    return pad_img(im, 30)


# ---------- the overlay timeline ----------

class Overlays:
    def __init__(self):
        cw, ch = 470, 380
        self.python_card = snake_card("python", cw, ch, "MALAI PAAMBU", (150, 150, 150), "Indian Rock Python")
        self.viper_card = snake_card("viper", cw, ch, "RUSSELL'S VIPER", RED, "Kannadi Viriyan")
        self.viper_big = snake_card("viper", 900, 520, "RUSSELL'S VIPER", RED, "Daboia russelii")
        self.vs = text_img("VS", 90, YELLOW, 8)
        self.q = text_img("?", 200, YELLOW, 10)
        self.malai = multi_color_line([("Malai Paambu ah?", WHITE), ("❌", WHITE)], 78)
        self.kannadi = multi_color_line([("Kannadi Viriyan", YELLOW), ("=", WHITE)], 72)
        self.russell = multi_color_line([("Russell's Viper", RED), ("🐍", WHITE)], 86)
        self.map = glow(india_map(430), RED, 22, 1.6)
        self.top_title = text_img("TOP DANGEROUS SNAKES", 50, WHITE, 6)
        self.top_title2 = text_img("IN INDIA", 50, YELLOW, 6)
        rows = [("#1", "Russell's Viper", RED), ("#2", "Common Krait", None),
                ("#3", "Indian Cobra", None), ("#4", "Saw-scaled Viper", None)]
        self.rows = [self._rank_row(*r) for r in rows]
        self.deaths_lbl = text_img("deaths per year", 62, WHITE, 6)
        self.india_lbl = text_img("in India", 50, YELLOW, 6)
        self.chart_lbl1 = text_img("of snakebite deaths", 58, WHITE, 6)
        self.chart_lbl2 = text_img("(2000–2019)", 50, YELLOW, 6)
        self.similar = text_img("Looks similar.", 80, WHITE, 8)
        self.deadly = multi_color_line([("Deadly mistake", RED), ("⚠️", WHITE)], 84)
        self.feet = text_img("10 FEET", 150, YELLOW, 10)
        self.safe = text_img("SAFE DISTANCE", 52, WHITE, 6)
        self.speed1 = text_img("STRIKING SPEED", 80, YELLOW, 8)
        self.speed2 = text_img(">", 110, RED, 8)
        self.speed3 = text_img("YOUR REACTION", 80, WHITE, 8)
        self.bolt = self._bolt(160, 300)
        self.rko = glow(text_img("RKO", 330, YELLOW, 16, (160, 0, 10), shadow=False), RED, 30, 2)
        self.rko2 = text_img("OUT OF NOWHERE!", 92, WHITE, 10)
        self.comment = text_img("Comment below", 92, YELLOW, 9)
        self.follow_btn = self._button("Follow @SathishTalks", YELLOW, BLACK)
        self.following_btn = self._button("Following ✓", (40, 40, 44), WHITE)
        self.snake_emoji = _emoji_img("🐍", 110)
        self.person_emoji = _emoji_img("🧍", 120)
        self.burst = self._burst(1300)
        self.vignette = self._vignette()

    def _rank_row(self, num, name, color):
        w, h = 620, 86
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        fill = (150, 10, 20, 235) if color else (25, 25, 28, 220)
        d.rounded_rectangle((0, 0, w - 1, h - 1), 18, fill=fill, outline=(255, 70, 80) if color else (70, 70, 75), width=3)
        d.text((24, h // 2), num, font=font(48), fill=YELLOW if color else (170, 170, 170), anchor="lm")
        d.text((110, h // 2), name, font=font(44 if color else 40, FONT_BLACK if color else FONT_BOLD),
               fill=WHITE, anchor="lm")
        if color:
            d.text((w - 24, h // 2), "☠", font=font(46, "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
                   fill=YELLOW, anchor="rm")
        return im

    def _button(self, label, bg, fg):
        f = font(64)
        tw = int(f.getlength(label))
        w, h = tw + 120, 130
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle((0, 0, w - 1, h - 1), h // 2, fill=bg + (255,))
        d.text((w // 2, h // 2 + 2), label, font=f, fill=fg, anchor="mm")
        return glow(pad_img(im, 50), YELLOW if bg == YELLOW else (90, 90, 90), 28, 1.5)

    def _bolt(self, w, h):
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        pts = [(0.62, 0), (0.12, 0.55), (0.45, 0.55), (0.3, 1.0), (0.9, 0.38), (0.55, 0.38), (0.8, 0)]
        ImageDraw.Draw(im).polygon([(x * w, y * h) for x, y in pts], fill=YELLOW)
        return glow(pad_img(im, 40), (255, 240, 120), 20, 2)

    def _burst(self, size):
        im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        c = size / 2
        for k in range(24):
            a0 = 2 * math.pi * k / 24
            a1 = a0 + 2 * math.pi / 48
            col = (200, 0, 20, 200) if k % 2 == 0 else (255, 200, 0, 140)
            d.polygon([(c, c), (c + c * 1.5 * math.cos(a0), c + c * 1.5 * math.sin(a0)),
                       (c + c * 1.5 * math.cos(a1), c + c * 1.5 * math.sin(a1))], fill=col)
        return im

    def _vignette(self):
        v = Image.new("L", (W // 4, H // 4), 0)
        ImageDraw.Draw(v).ellipse((-W // 8, -H // 16, W // 4 + W // 8, H // 4 + H // 16), fill=255)
        v = v.filter(ImageFilter.GaussianBlur(40)).resize((W, H), Image.BILINEAR)
        a = v.point(lambda x: int((255 - x) * 0.55))
        im = Image.new("RGBA", (W, H), (25, 0, 0, 255))
        im.putalpha(a)
        return im

    # --- per-section drawing ---

    def draw(self, c, t):
        c.alpha_composite(self.vignette)
        if t < S2_NAME:
            self.hook(c, t)
        elif t < S3_STATS:
            self.name(c, t)
        elif t < S4_CHART:
            self.stats(c, t)
        elif t < S5_COMPARE:
            self.chart(c, t)
        elif t < S6_DISTANCE:
            self.compare(c, t)
        elif t < S7_RKO:
            self.distance(c, t)
        elif t < S8_END:
            self.rko_fx(c, t)
        else:
            self.end(c, t)

    def hook(self, c, t):
        a = window_alpha(t, 0.3, S2_NAME + 0.05)
        s1 = ease_out((t - 0.3) / 0.4)
        s2 = ease_out((t - 0.6) / 0.4)
        paste(c, self.python_card, 280 - (1 - s1) * 500, 330, 1.0, a * s1, angle=2)
        paste(c, self.viper_card, 800 + (1 - s2) * 500, 330, 1.0, a * s2, angle=-2)
        paste(c, self.vs, 540, 330, pop_scale(t, 1.0), a)
        # the "?" wobbles over the viper while you build the suspense
        if 1.1 < t < 2.0:
            paste(c, self.q, 800, 300, pop_scale(t, 1.1) * (1 + 0.05 * math.sin(t * 12)), a)
        paste(c, self.malai, 540, 640, pop_scale(t, 2.0), a)
        if t > 2.0:  # red X stamp over the python card
            sx = pop_scale(t, 2.0, 0.22)
            x = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
            d = ImageDraw.Draw(x)
            d.line((40, 40, 260, 260), fill=RED, width=34)
            d.line((260, 40, 40, 260), fill=RED, width=34)
            paste(c, x, 280, 300, sx * 0.9, a * 0.85)

    def name(self, c, t):
        a = window_alpha(t, S2_NAME, S3_STATS + 0.05)
        lt = t - S2_NAME
        # slow push into the close-up
        paste(c, self.viper_big, 540, 330, (0.85 + 0.12 * ease_out(lt / 0.5) + 0.03 * lt / 4) , a)
        paste(c, self.kannadi, 540, 660, pop_scale(t, S2_NAME + 0.4), a)
        paste(c, self.russell, 540, 760, pop_scale(t, S2_NAME + 0.6), a)

    def stats(self, c, t):
        lt = t - S3_STATS
        a = window_alpha(t, S3_STATS, S4_CHART + 0.05)
        pulse = 0.85 + 0.15 * math.sin(t * 6)
        if t < S3_COUNTER:
            # map on the left, ranking on the right
            paste(c, self.map, 250, 350, 0.62 * back_out(lt / 0.35), a * pulse)
            paste(c, self.top_title, 540, 105, pop_scale(t, S3_STATS + 0.2), a)
            paste(c, self.top_title2, 540, 165, pop_scale(t, S3_STATS + 0.35), a)
            for i, row in enumerate(self.rows):
                st = S3_STATS + 0.5 + 0.25 * i
                p = ease_out((t - st) / 0.3)
                if t < st:
                    continue
                sc = 0.78 * (1.06 if i == 0 else 1.0) * (1 + 0.04 * math.sin(t * 8) * (i == 0))
                paste(c, row, 760 + (1 - p) * 600, 265 + i * 82, sc, a * p)
        else:
            # big counter over the glowing map
            lc = t - S3_COUNTER
            paste(c, self.map, 540, 400, 1.05, a * 0.55 * pulse)
            p = ease_out(lc / 1.3)
            lo, hi = int(15000 * p), int(20000 * p)
            num = text_img(f"{lo:,}–{hi:,}", 118, RED if p >= 1 else YELLOW, 10)
            shake = 6 * math.sin(lc * 70) * clamp(1 - abs(lc - 1.35) / 0.25) if lc > 1.1 else 0
            paste(c, glow(num, RED, 22, 1.4) if p >= 1 else num, 540 + shake, 330,
                  pop_scale(t, S3_COUNTER, 0.3) * (1 + 0.06 * clamp(1 - abs(lc - 1.35) / 0.2)), a)
            paste(c, self.deaths_lbl, 540, 460, pop_scale(t, S3_COUNTER + 0.5), a)
            paste(c, self.india_lbl, 540, 540, pop_scale(t, S3_COUNTER + 0.7), a)

    def chart(self, c, t):
        lt = t - S4_CHART
        a = window_alpha(t, S4_CHART, S5_COMPARE + 0.05)
        size = 380
        S = 2
        im = Image.new("RGBA", (size * S, size * S), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        r = size * S
        wd = 60 * S
        d.ellipse((0, 0, r - 1, r - 1), fill=(20, 20, 22, 230))
        d.arc((wd // 2, wd // 2, r - wd // 2, r - wd // 2), 0, 360, fill=(60, 60, 64), width=wd)
        p = ease_in_out((lt - 0.3) / 1.8)
        pct = 43 * p
        if pct > 0.2:
            d.arc((wd // 2, wd // 2, r - wd // 2, r - wd // 2), -90, -90 + 360 * pct / 100, fill=RED, width=wd)
        im = im.resize((size, size), Image.LANCZOS)
        im = glow(pad_img(im, 40), RED, 20, 0.9 + 0.5 * p)
        sc = back_out(lt / 0.4) * (1 + 0.05 * clamp(1 - abs(lt - 2.15) / 0.2))
        paste(c, im, 540, 330, sc, a)
        num = text_img(f"{int(round(pct))}%", 110, RED if p >= 1 else WHITE, 8)
        paste(c, num, 540, 330, sc * (1 + 0.2 * clamp(1 - abs(lt - 2.15) / 0.2)), a)
        paste(c, self.chart_lbl1, 540, 590, pop_scale(t, S4_CHART + 0.8), a)
        paste(c, self.chart_lbl2, 540, 665, pop_scale(t, S4_CHART + 1.1), a)

    def compare(self, c, t):
        lt = t - S5_COMPARE
        a = window_alpha(t, S5_COMPARE, S6_DISTANCE + 0.05)
        # quick zoom-ins: punch on each card in turn
        z1 = 1 + 0.12 * clamp(1 - abs(lt - 1.8) / 0.25)
        z2 = 1 + 0.12 * clamp(1 - abs(lt - 2.6) / 0.25)
        paste(c, self.python_card, 280, 330, back_out(lt / 0.3) * z1, a)
        paste(c, self.viper_card, 800, 330, back_out((lt - 0.12) / 0.3) * z2, a)
        paste(c, self.vs, 540, 330, pop_scale(t, S5_COMPARE + 0.3), a)
        paste(c, self.similar, 540, 600, pop_scale(t, S5_COMPARE + 0.5), a)
        warn = 1 + 0.05 * math.sin(lt * 14) if lt > 1.2 else 1
        paste(c, self.deadly, 540, 700, pop_scale(t, S5_COMPARE + 1.2) * warn, a)
        if lt > 1.2:  # red warning border flash
            fa = 0.5 * (0.5 + 0.5 * math.sin(lt * 14))
            b = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ImageDraw.Draw(b).rectangle((0, 0, W - 1, H - 1), outline=RED + (int(255 * fa),), width=18)
            c.alpha_composite(b)

    def distance(self, c, t):
        lt = t - S6_DISTANCE
        a = window_alpha(t, S6_DISTANCE, S7_RKO + 0.05)
        if t < S6_SPEED:
            p = ease_out((lt - 0.2) / 0.6)
            y = 330
            half = 380 * p
            d = ImageDraw.Draw(c)
            col = YELLOW + (int(255 * a),)
            if half > 5:
                d.line((540 - half, y, 540 + half, y), fill=col, width=10)
                for sx in (-1, 1):
                    x = 540 + sx * half
                    d.polygon([(x, y), (x - sx * 36, y - 24), (x - sx * 36, y + 24)], fill=col)
                for k in range(-5, 6):  # ruler ticks, one per foot
                    if abs(k) * 38 < half - 30:
                        x = 540 + k * 38 * 2 * 0.5 * (1 if True else 0)
                        d.line((x, y - 16, x, y + 16), fill=col, width=4)
            paste(c, self.snake_emoji, 540 - 470, y, back_out((lt - 0.3) / 0.3) * 0.9, a)
            paste(c, self.person_emoji, 540 + 470, y, back_out((lt - 0.3) / 0.3) * 0.9, a)
            paste(c, self.feet, 540, 190, pop_scale(t, S6_DISTANCE + 0.5), a)
            paste(c, self.safe, 540, 430, pop_scale(t, S6_DISTANCE + 0.8), a)
            ok = text_img("✔ Keep this gap", 46, (120, 230, 120), 5, path=FONT_BOLD)
            paste(c, ok, 540, 510, pop_scale(t, S6_DISTANCE + 1.6), a)
        else:
            ls = t - S6_SPEED
            # speed lines streaking across the top
            rng = np.random.default_rng(int(t * FPS))
            d = ImageDraw.Draw(c)
            for _ in range(26):
                y = rng.uniform(60, 720)
                x = rng.uniform(-200, W)
                L = rng.uniform(150, 500)
                d.line((x, y, x + L, y), fill=(255, 255, 255, int(rng.uniform(40, 140) * a)), width=int(rng.uniform(2, 6)))
            flash = clamp(1 - ls / 0.25)
            if flash > 0:
                c.alpha_composite(Image.new("RGBA", (W, H), (255, 255, 230, int(120 * flash))))
            x_off = (1 - ease_out(ls / 0.25)) * 900
            paste(c, self.speed1, 540 - x_off, 230, 1.0, a)
            paste(c, self.speed2, 540, 345, pop_scale(t, S6_SPEED + 0.25), a)
            paste(c, self.speed3, 540 + x_off, 460, 1.0, a)
            bolt_a = a * (0.6 + 0.4 * (int(t * 15) % 2))
            paste(c, self.bolt, 160, 345, pop_scale(t, S6_SPEED + 0.2) * 0.8, bolt_a, angle=10)
            paste(c, self.bolt, 920, 345, pop_scale(t, S6_SPEED + 0.3) * 0.8, bolt_a, angle=-10)

    def rko_fx(self, c, t):
        lt = t - RKO_HIT
        if -0.05 <= lt < RKO_FREEZE + 0.2:
            a = window_alpha(t, RKO_HIT - 0.05, RKO_HIT + RKO_FREEZE + 0.2, 0.05, 0.2)
            paste(c, self.burst, 540, 960, 1.0, a * 0.3, angle=lt * 40)
            flash = clamp(1 - (lt + 0.05) / 0.18)
            if flash > 0:
                c.alpha_composite(Image.new("RGBA", (W, H), (255, 255, 255, int(230 * flash))))
            paste(c, self.rko, 540, 520, back_out((lt) / 0.22, 3.0) * (1 + 0.03 * math.sin(lt * 40)), a, angle=-6)
            paste(c, self.rko2, 540, 760, pop_scale(t, RKO_HIT + 0.15), a, angle=-4)

    def end(self, c, t):
        lt = t - S8_END
        a = window_alpha(t, S8_END, DURATION + 1)
        bounce = 14 * abs(math.sin(lt * 5)) if lt > 0.6 else 0
        paste(c, self.comment, 540, 300 - bounce * 0, pop_scale(t, S8_END + 0.3), a)
        if lt > 0.6:
            arrow = _emoji_img("👇", 90)
            paste(c, arrow, 540, 420 + bounce, 1.0, a)
        tap = S8_END + 3.0
        if t < tap:
            breathe = 1 + 0.04 * math.sin(lt * 6)
            paste(c, self.follow_btn, 540, 620, pop_scale(t, S8_END + 1.6) * breathe, a)
        else:
            press = 1 - 0.1 * clamp(1 - (t - tap) / 0.15)
            paste(c, self.following_btn, 540, 620, press * back_out((t - tap) / 0.25), a)
        # hand cursor tapping the button
        if S8_END + 2.2 < t < tap + 0.8:
            hand = _emoji_img("👆", 100)
            p = ease_out((t - S8_END - 2.2) / 0.7)
            paste(c, hand, 760 - 60 * p + 0, 820 - 120 * p + (10 if abs(t - tap) < 0.12 else 0), 1.0,
                  a * clamp((tap + 0.8 - t) / 0.3))


# ---------- captions ----------

KEYWORDS_RED = ["russell", "viper", "43%", "15,000", "20,000", "rko", "deadly", "viriyan"]
KEYWORDS_YELLOW = ["paambu", "malai", "kannadi", "10", "feet", "follow", "comment"]


def load_captions():
    """captions.json: [{"start": s, "end": e, "text": "..."}]. Lines are split into
    2-4 word chunks timed proportionally to word length within the line."""
    path = os.path.join(HERE, "captions.json")
    if not os.path.exists(path):
        return []
    lines = [l for l in json.load(open(path)) if l.get("text", "").strip()]
    chunks = []
    for l in lines:
        words = l["text"].split()
        groups, i = [], 0
        while i < len(words):
            n = 3 if len(words) - i != 4 else 2
            n = min(n, len(words) - i)
            if len(words) - i - n == 1:
                n += 1
            groups.append(words[i:i + n])
            i += n
        total = sum(len("".join(g)) for g in groups)
        t0 = l["start"]
        for g in groups:
            dur = (l["end"] - l["start"]) * len("".join(g)) / total
            chunks.append((t0, t0 + dur, g))
            t0 += dur
    return chunks


def word_color(w):
    lw = w.lower().strip(".,!?\"'")
    if any(k in lw for k in KEYWORDS_RED):
        return RED, True
    if any(lw.startswith(k) for k in KEYWORDS_YELLOW):
        return YELLOW, True
    return WHITE, False


_cap_cache = {}


def draw_caption(c, t, chunks, y=1490):
    for s, e, words in chunks:
        if s <= t < e:
            key = (s, tuple(words))
            if key not in _cap_cache:
                _cap_cache[key] = [(text_img(w.upper(), 92, word_color(w)[0], 9), word_color(w)[1]) for w in words]
            ims = _cap_cache[key]
            gap = 22
            tw = sum(i.width for i, _ in ims) + gap * (len(ims) - 1)
            sc_all = min(1.0, 980 / tw)
            x = 540 - tw * sc_all / 2
            for k, (im, hot) in enumerate(ims):
                # each word pops in with a stagger; keywords pop bigger
                st = s + k * min(0.08, (e - s) / (len(ims) + 1))
                sc = back_out((t - st) / 0.18, 2.6 if hot else 1.6) * sc_all * (1.08 if hot else 1.0)
                paste(c, im, x + im.width * sc_all / 2, y, sc, 1.0 if t >= st else 0)
                x += (im.width + gap) * sc_all
            return


# ---------- video transforms ----------

def zoom_at(t):
    if t < S2_NAME:  # slow punch-in on the hook
        return 1.0 + 0.16 * ease_in_out(t / S2_NAME)
    if RKO_HIT - 0.15 <= t < RKO_HIT + RKO_FREEZE + 0.5:
        lt = t - RKO_HIT
        if lt < 0:
            return 1.04 + 0.4 * ease_out((lt + 0.15) / 0.15)
        if lt < RKO_FREEZE:
            return 1.44
        return 1.44 - 0.4 * ease_in_out((lt - RKO_FREEZE) / 0.5)
    levels = [1.0, 1.1, 1.04, 1.14]
    prev = [b for b in PHRASE_BREAKS if b <= t and b >= S2_NAME]
    if not prev:
        return 1.0
    i = len(prev)
    z = levels[i % 4]
    zp = levels[(i - 1) % 4]
    return zp + (z - zp) * ease_out((t - prev[-1]) / 0.12)


def shake_at(t):
    lt = t - RKO_HIT
    amp = 0
    if 0 <= lt < 0.6:
        amp = 26 * (1 - lt / 0.6)
    lc = t - (S3_COUNTER + 1.3)
    if 0 <= lc < 0.35:
        amp = max(amp, 10 * (1 - lc / 0.35))
    ls = t - S6_SPEED
    if 0 <= ls < 0.3:
        amp = max(amp, 8 * (1 - ls / 0.3))
    if amp == 0:
        return 0, 0
    return amp * math.sin(t * 97), amp * math.cos(t * 83)


def glitch_strength(t):
    g = 0
    for s in SECTION_STARTS + [2.0]:
        d = t - (s - 0.05)
        if 0 <= d < 0.15:
            g = max(g, 1 - d / 0.15)
    return g


def transform(frame, t, anchor=(0.48, 0.47)):
    z = zoom_at(t)
    dx, dy = shake_at(t)
    ax, ay = anchor[0] * W, anchor[1] * H
    # output pixel (X,Y) samples input at ax + (X-ax)/z - dx/z ...
    a = 1 / z
    coeffs = (a, 0, ax - ax * a - dx * a, 0, a, ay - ay * a - dy * a)
    return frame.transform((W, H), Image.AFFINE, coeffs, resample=Image.BILINEAR)


def glitch(img, g, t):
    if g <= 0:
        return img
    arr = np.asarray(img).copy()
    off = int(18 * g)
    arr[:, :, 0] = np.roll(arr[:, :, 0], off, axis=1)
    arr[:, :, 2] = np.roll(arr[:, :, 2], -off, axis=1)
    rng = np.random.default_rng(int(t * 1000))
    for _ in range(int(8 * g)):
        y = rng.integers(0, H - 80)
        h = rng.integers(10, 80)
        arr[y:y + h] = np.roll(arr[y:y + h], rng.integers(-60, 60), axis=1)
    return Image.fromarray(arr)


def grade(img, t):
    """Very light dark/red tint for the drama; stronger during the RKO freeze."""
    lt = t - RKO_HIT
    if 0 <= lt < RKO_FREEZE:
        g = img.convert("L").convert("RGB")
        red = Image.new("RGB", (W, H), (255, 60, 60))
        return Image.blend(ImageChops.multiply(g, red), img, 0.55)
    return img


# ---------- main ----------

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    src = args[0]
    out = args[1] if len(args) > 1 else os.path.join(HERE, "output", "russells_viper_reel.mp4")
    preview = None
    if "--preview" in sys.argv:
        preview = float(sys.argv[sys.argv.index("--preview") + 1])
    stills = "--stills" in sys.argv
    work = os.path.join(HERE, "output", "_work")
    os.makedirs(work, exist_ok=True)

    audio.build(work)
    ov = Overlays()
    chunks = load_captions()

    dur = preview or DURATION
    dec = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-i", src, "-t", str(dur),
         "-vf", f"fps={FPS},scale={W}:{H}:flags=lanczos", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        stdout=subprocess.PIPE)
    silent = os.path.join(work, "video.mp4")
    enc = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
         "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
         "-pix_fmt", "yuv420p", silent],
        stdin=subprocess.PIPE)

    frame_bytes = W * H * 3
    frozen = None
    n = 0
    while True:
        buf = dec.stdout.read(frame_bytes)
        if len(buf) < frame_bytes:
            break
        t = n / FPS
        frame = Image.frombuffer("RGB", (W, H), buf, "raw", "RGB", 0, 1)
        # freeze-frame on the RKO hit (picture holds, your audio keeps running)
        if RKO_HIT <= t < RKO_HIT + RKO_FREEZE:
            if frozen is None:
                frozen = frame.copy()
            frame = frozen
        img = grade(transform(frame, t), t).convert("RGBA")
        ov.draw(img, t)
        draw_caption(img, t, chunks)
        img = glitch(img.convert("RGB"), glitch_strength(t), t)
        enc.stdin.write(img.tobytes())
        if stills and n % FPS == 0:
            img.resize((360, 640)).save(os.path.join(work, f"still_{int(t):02d}.jpg"), quality=80)
        n += 1
        if n % 150 == 0:
            print(f"  {t:5.1f}s / {dur:.1f}s", flush=True)
    enc.stdin.close()
    enc.wait()
    dec.wait()

    # Voice: untouched original track at full level. Music: ducked under the voice.
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", silent, "-i", src,
         "-i", os.path.join(work, "music.wav"), "-i", os.path.join(work, "sfx.wav"),
         "-filter_complex",
         "[1:a]aresample=44100,asplit=2[voice][key];"
         "[2:a]volume=0.32[mus];"
         "[mus][key]sidechaincompress=threshold=0.02:ratio=8:attack=20:release=400:makeup=1[duck];"
         "[3:a]volume=1.0[fx];"
         "[voice][duck][fx]amix=inputs=3:duration=first:normalize=0,alimiter=limit=0.97:level=false[a]",
         "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
         "-t", str(dur), "-movflags", "+faststart", out],
        check=True)
    print("wrote", out)


if __name__ == "__main__":
    main()
