"""Shared drawing helpers: text with emoji/Tamil, easing, compositing, and the 2D cartoon snake."""
import json
import math
import os

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

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
FONT_TITLE = os.path.join(HERE, "assets", "fonts", "Anton.woff")
FONT_TAMIL = os.path.join(HERE, "assets", "fonts", "NotoSansTamil-ExtraBold.woff")
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
    """Renders one line of text (emoji and Tamil allowed) to a tight RGBA image."""
    if any("\u0b80" <= ch <= "\u0bff" for ch in text):
        path = FONT_TAMIL
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
