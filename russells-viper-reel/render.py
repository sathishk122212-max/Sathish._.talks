"""Renders the edited Russell's Viper reel.

    python3 render.py <input.mov> [output.mp4] [--preview SECONDS] [--from SECONDS] [--stills]

Your voice track plays untouched from start to finish. On screen, the edit cuts between your
original footage (zoomed or cropped only, never altered) and full-screen visuals: your snake
photos with keyframed camera moves, kinetic key words, an animated India map, the 43% infographic, a side-by-side comparison, the
10-foot safety diagram, the RKO cartoon and the Sathish Talks end card.

Photos live in assets/photos/ and are referenced by file name in timeline.py.
"""
import glob
import json
import math
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

import audio
from gfx import *
from gfx import _emoji_img
from timeline import *

WORK = os.path.join(HERE, "output", "_work")
PHOTOS = os.path.join(HERE, "assets", "photos")
GREEN = (60, 200, 110)


def ken_burns(img, p, z0=1.0, z1=1.12, pan=(0.0, -0.03), size=(W, H)):
    """Cover-crop img to size with a slow zoom/pan; p = 0..1 progress."""
    w, h = size
    base = max(w / img.width, h / img.height)
    z = base * lerp_(z0, z1, p)
    cw, ch = w / z, h / z
    cx = img.width / 2 + pan[0] * img.width * p
    cy = img.height / 2 + pan[1] * img.height * p
    box = (cx - cw / 2, cy - ch / 2, cx + cw / 2, cy + ch / 2)
    return img.transform(size, Image.EXTENT, box, Image.BICUBIC), (box, z)


def lerp_(a, b, t):
    return a + (b - a) * t


# ---------------------------------------------------------------- frame sources

class Reader:
    """Sequential ffmpeg frame reader at W x H, 30 fps."""

    def __init__(self, path, vf="", start=0.0):
        chain = f"fps={FPS},scale={W}:{H}:flags=lanczos" + ("," + vf if vf else "")
        self.p = subprocess.Popen(["ffmpeg", "-v", "error", "-ss", str(start), "-i", path, "-vf", chain,
                                   "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
        self.i = -1
        self.last = None

    def get(self, k):
        while self.i < k:
            buf = self.p.stdout.read(W * H * 3)
            if len(buf) < W * H * 3:
                break
            self.last = Image.frombuffer("RGB", (W, H), buf, "raw", "RGB", 0, 1)
            self.i += 1
        return self.last


def prep_photo(img):
    """Lightly sharpened photo + a blurred, darkened full-screen backdrop made from it."""
    img = img.filter(ImageFilter.UnsharpMask(1.2, 60, 2))
    bg, _ = ken_burns(img, 0, 1.0, 1.0)
    bg = bg.filter(ImageFilter.GaussianBlur(38))
    bg = Image.blend(bg, Image.new("RGB", (W, H), (20, 4, 6)), 0.62)
    return img, bg


def load_gif(path):
    if not os.path.exists(path):
        return None
    im = Image.open(path)
    frames = []
    try:
        while True:
            frames.append(im.convert("RGB").filter(ImageFilter.UnsharpMask(1.2, 60, 2)))
            im.seek(im.tell() + 1)
    except EOFError:
        pass
    _, bg = prep_photo(frames[0])
    return frames, bg


_feather = {}


def feather_mask(size):
    """Soft top/bottom edges so the photo band melts into the blurred backdrop."""
    w, h = size
    key = (w // 4, h // 4)
    if key not in _feather:
        y = np.arange(h // 4 + 1, dtype=np.float32)
        f = np.clip(np.minimum(y, h // 4 - y) / max(1, h // 4 * 0.08), 0, 1)
        _feather[key] = Image.fromarray((np.repeat(f[:, None], w // 4 + 1, 1) * 255).astype(np.uint8))
    return _feather[key].resize((w, h), Image.BILINEAR)


def light_leak(c, lt):
    """Warm moving light sweep for the reveal."""
    x = -400 + lt * 900
    leak = Image.new("RGBA", (W // 8, H // 8), (0, 0, 0, 0))
    ImageDraw.Draw(leak).ellipse((x / 8 - 40, -20, x / 8 + 40, H / 8 + 20), fill=(255, 140, 60, 70))
    c.alpha_composite(leak.filter(ImageFilter.GaussianBlur(14)).resize((W, H), Image.BILINEAR))


# ---------------------------------------------------------------- shared looks

def make_vignette(strength=0.6, color=(0, 0, 0)):
    v = Image.new("L", (W // 4, H // 4), 0)
    ImageDraw.Draw(v).ellipse((-W // 10, -H // 14, W // 4 + W // 10, H // 4 + H // 14), fill=255)
    v = v.filter(ImageFilter.GaussianBlur(45)).resize((W, H), Image.BILINEAR)
    im = Image.new("RGBA", (W, H), color + (255,))
    im.putalpha(v.point(lambda x: int((255 - x) * strength)))
    return im


def make_bg():
    """Dark infographic backdrop: deep red radial glow + faint grid."""
    y, x = np.mgrid[0:H, 0:W]
    r = np.sqrt(((x - W / 2) / W) ** 2 + ((y - H * 0.42) / H) ** 2)
    g = np.clip(1 - r * 1.6, 0, 1) ** 2
    arr = np.stack([12 + 48 * g, 8 + 6 * g, 10 + 8 * g], -1)
    grid = ((x % 60 == 0) | (y % 60 == 0)) * 6 * (0.3 + g)
    arr += grid[..., None]
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert("RGBA")


GRAIN = [np.random.default_rng(k).normal(0, 7, (H // 2, W // 2)).astype(np.int16) for k in range(6)]


def grain(img, k, amount=1.0):
    n = GRAIN[k % len(GRAIN)].repeat(2, 0).repeat(2, 1)
    arr = np.asarray(img.convert("RGB")).astype(np.int16) + (n * amount)[..., None].astype(np.int16)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def anim_text(c, im, cx, cy, t, start, dur=0.35, rise=40, alpha=1.0):
    """Fade + rise-in (clean, cinematic)."""
    if t < start:
        return
    p = ease_out((t - start) / dur)
    paste(c, im, cx, cy + (1 - p) * rise, 1.0, p * alpha)


def wipe_text(c, im, cx, cy, t, start, dur=0.45, alpha=1.0):
    """Left-to-right mask reveal."""
    if t < start:
        return
    p = ease_out((t - start) / dur)
    w = int(im.width * p)
    if w < 2:
        return
    part = im.crop((0, 0, w, im.height))
    canvas_x = int(cx - im.width / 2)
    paste(c, part, canvas_x + w / 2, cy, 1.0, alpha)


def lower_third(c, t, start, title, sub=None, y=1330):
    if t < start:
        return
    p = ease_out((t - start) / 0.4)
    bar_w = int(10)
    d = ImageDraw.Draw(c)
    x0 = 70
    d.rectangle((x0, y - 70, x0 + bar_w, y - 70 + int(150 * p)), fill=RED + (255,))
    ti = text_img(title, 96, WHITE, 0, path=FONT_TITLE)
    wipe_text(c, ti, x0 + 40 + ti.width / 2, y - 10, t, start + 0.1)
    if sub:
        si = text_img(sub, 46, YELLOW, 0, path=FONT_BOLD)
        anim_text(c, si, x0 + 40 + si.width / 2, y + 70, t, start + 0.35, rise=20)


def brand_bug(c):
    if not hasattr(brand_bug, "im"):
        ti = text_img("SATHISH TALKS", 34, WHITE, 0, path=FONT_TITLE, shadow=False)
        w, h = ti.width + 76, 62
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle((0, 0, w - 1, h - 1), 31, fill=(0, 0, 0, 120))
        d.ellipse((20, h // 2 - 9, 38, h // 2 + 9), fill=RED)
        im.alpha_composite(ti, (52, (h - ti.height) // 2))
        brand_bug.im = im
    c.alpha_composite(brand_bug.im, (40, 56))


# ---------------------------------------------------------------- segment renderers

class Edit:
    def __init__(self, src):
        self.src = src
        self.vignette = make_vignette(0.55)
        self.red_vig = make_vignette(0.75, (120, 0, 10))
        self.bg = make_bg()
        self.photos = {}
        for f in sorted(glob.glob(os.path.join(PHOTOS, "*.jpg"))):
            self.photos[os.path.splitext(os.path.basename(f))[0]] = prep_photo(Image.open(f).convert("RGB"))
        self._prep_map()
        self.cartoon = draw_snake("viper", 760, 460)
        self.rko_frames = load_gif(os.path.join(PHOTOS, "rko.gif"))
        self.captions = load_captions()

    # ---- your footage
    def me(self, frame, t, seg):
        s0, s1, _, opt = seg
        lt = t - s0
        if "push" in opt:
            z = 1.0 + opt["push"] * ease_in_out(lt / (s1 - s0))
        else:
            prev = [b for b in PHRASE_BREAKS if b <= t]
            levels = [1.0, 1.09, 1.03, 1.12]
            i = len(prev)
            z, zp = levels[i % 4], levels[(i - 1) % 4]
            if prev:
                z = zp + (z - zp) * ease_out((t - prev[-1]) / 0.12)
        # a short punch-in when coming back from a full-screen visual
        z *= 1 + 0.05 * (1 - ease_out(lt / 0.35))
        ax, ay = 0.48 * W, 0.47 * H
        a = 1 / z
        img = frame.transform((W, H), Image.AFFINE, (a, 0, ax - ax * a, 0, a, ay - ay * a), Image.BILINEAR)
        c = img.convert("RGBA")
        c.alpha_composite(self.vignette)
        if opt.get("end"):
            self.end_overlay(c, t, s0)
        return c

    def end_overlay(self, c, t, s0):
        lt = t - s0
        if not hasattr(self, "_end"):
            self._end = dict(
                comment=text_img("COMMENT BELOW", 96, YELLOW, 0, path=FONT_TITLE),
                arrow=emoji_cached("👇", 92),
                follow=self._button("Follow @SathishTalks", YELLOW, BLACK),
                following=self._button("Following ✓", (40, 40, 44), WHITE),
                hand=emoji_cached("👆", 100))
        e = self._end
        anim_text(c, e["comment"], 540, 250, t, s0 + 0.2)
        if lt > 0.5:
            paste(c, e["arrow"], 540, 370 + 14 * abs(math.sin(lt * 5)), 1.0, clamp((lt - 0.5) / 0.2))
        tap = s0 + 3.0
        if t < tap:
            paste(c, e["follow"], 540, 560, pop_scale(t, s0 + 1.4) * (1 + 0.035 * math.sin(lt * 6)))
        else:
            press = 1 - 0.1 * clamp(1 - (t - tap) / 0.15)
            paste(c, e["following"], 540, 560, press * back_out((t - tap) / 0.25))
        if s0 + 2.2 < t < tap + 0.8:
            p = ease_out((t - s0 - 2.2) / 0.7)
            paste(c, e["hand"], 780 - 80 * p, 760 - 140 * p + (10 if abs(t - tap) < 0.12 else 0), 1.0,
                  clamp((tap + 0.8 - t) / 0.3))

    def _button(self, label, bg, fg):
        f = font(64)
        tw = int(f.getlength(label))
        w, h = tw + 120, 130
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle((0, 0, w - 1, h - 1), h // 2, fill=bg + (255,))
        d.text((w // 2, h // 2 + 2), label, font=f, fill=fg, anchor="mm")
        return glow(pad_img(im, 50), YELLOW if bg == YELLOW else (90, 90, 90), 28, 1.5)

    # ---- your photos, with keyframed camera moves
    def place_photo(self, name, lt, dur, opt, cy=960):
        """Blurred backdrop + sharp photo band. Returns (canvas, mapper from photo 0-1 coords to screen)."""
        img, bg = self.photos[name]
        fu, fv = opt.get("focus", (0.5, 0.5))
        z0, z1 = opt.get("zoom", (1.0, 1.15))
        fx = opt.get("fx")
        p = lt / dur
        if fx == "reveal":      # fast snap-in, then a slow creeping push to the head
            k = 0.35 * ease_out(p / 0.15) + 0.65 * ease_in_out((p - 0.15) / 0.85)
        elif fx == "strike":    # slow push, then a sudden lunge at the strike beat
            k = 0.45 * ease_in_out(p / 0.33) + 0.55 * ease_out((p - 0.34) / 0.08)
        else:
            k = ease_in_out(p)
        z = lerp_(z0, z1, k)
        w = W * z
        h = w * img.height / img.width
        # the focus point travels towards the screen centre as we push in
        travel = clamp((z - 1) / max(0.01, z1 - 1)) if z1 > 1 else 0
        x0 = 540 - w / 2 - (fu - 0.5) * w * travel
        y0 = cy - h / 2 - (fv - 0.5) * h * travel
        x0 = min(0.0, max(W - w, x0))   # never let a side edge into the frame
        if h >= H:
            y0 = min(0.0, max(H - h, y0))
        c = bg.copy()
        fg = img.resize((int(w), int(h)), Image.BICUBIC)
        mask = feather_mask(fg.size)
        c.paste(fg, (int(x0), int(y0)), mask)
        c = c.convert("RGBA")
        to_screen = lambda u, v: (x0 + u * w, y0 + v * h)
        return c, to_screen

    def photo(self, t, seg):
        s0, s1, _, opt = seg
        lt = t - s0
        c, to_screen = self.place_photo(opt["img"], lt, s1 - s0, opt)
        fx = opt.get("fx")
        if fx == "strike":
            hit = (s1 - s0) * 0.34
            q = lt - hit
            if 0 <= q < 0.5:   # shake on the lunge
                amp = 26 * (1 - q / 0.5)
                c = ImageChops.offset(c, int(amp * math.sin(lt * 97)), int(amp * math.cos(lt * 83)))
        c.alpha_composite(self.vignette)
        if fx == "reveal":
            fl = clamp(1 - lt / 0.25)
            if fl > 0:
                c.alpha_composite(Image.new("RGBA", (W, H), (255, 40, 40, int(150 * fl))))
            light_leak(c, lt)
        elif fx == "title":
            self.viper_title(c, t, s0)
        elif fx == "identify":
            anim_text(c, text_img("HOW TO IDENTIFY", 92, WHITE, 0, path=FONT_TITLE), 540, 260, t, s0 + 0.05)
            anim_text(c, self._tag("RUSSELL'S VIPER", RED), 540, 370, t, s0 + 0.15)
            for (u, v), label, st in opt.get("notes", []):
                x, y = to_screen(u, v)
                self._indicator(c, t, s0 + st, x, y, label)
        elif fx == "strike":
            self.strike_overlay(c, t, s0, (s1 - s0) * 0.34)
        return c

    def words(self, t, seg):
        """MALAI PAAMBU? / PYTHON? over the python photo, then crossed out before the viper reveal."""
        s0, s1, _, opt = seg
        lt = t - s0
        if "img" in opt:
            c, _ = self.place_photo(opt["img"], lt, s1 - s0, opt)
            c.alpha_composite(self.vignette)
            y1, y2, yx = 270, 440, 610
        else:
            c = self.bg.copy()
            y1, y2, yx = 820, 1030, 1250
        w1 = text_img("MALAI PAAMBU?", 150, WHITE, 0, path=FONT_TITLE)
        w2 = text_img("PYTHON?", 190, YELLOW, 0, path=FONT_TITLE)
        drift = 1 + 0.03 * lt
        paste(c, w1, 540, y1, back_out(lt / 0.3, 2.0) * drift)
        if lt > 0.7:
            paste(c, w2, 540, y2, back_out((lt - 0.7) / 0.3, 2.4) * drift)
        if lt > 1.35:
            q = ease_out((lt - 1.35) / 0.2)
            # the photo drains to a dark red as the answer turns into "no"
            c.alpha_composite(Image.new("RGBA", (W, H), (60, 0, 5, int(110 * q))))
            d = ImageDraw.Draw(c)
            for y, half in ((y1, 430), (y2, 330)):
                d.line((540 - half, y + 20, 540 - half + 2 * half * q, y - 20), fill=RED + (255,), width=22)
            paste(c, text_img("❌", 150), 540, yx, pop_scale(t, s0 + 1.45, 0.25))
        return c

    def viper_title(self, c, t, s0):
        if not hasattr(self, "_vt"):
            self._vt = (text_img("RUSSELL'S VIPER", 150, WHITE, 0, path=FONT_TITLE),
                        text_img("கண்ணாடி விரியன்", 92, YELLOW, 0))
        en, ta = self._vt
        y = 1240
        p = ease_out((t - s0 - 0.25) / 0.5)
        d = ImageDraw.Draw(c)
        if p > 0:
            d.rectangle((540 - 300 * p, y - 120, 540 + 300 * p, y - 112), fill=RED + (255,))
        wipe_text(c, en, 540, y, t, s0 + 0.3, 0.5)
        anim_text(c, ta, 540, y + 135, t, s0 + 0.7)

    def strike_overlay(self, c, t, s0, strike_at):
        lt = t - s0
        if lt < strike_at:
            anim_text(c, text_img("STRIKING SPEED", 120, WHITE, 0, path=FONT_TITLE), 540, 300, t, s0 + 0.15)
        else:
            fl = clamp(1 - (lt - strike_at) / 0.15)
            if fl > 0:
                c.alpha_composite(Image.new("RGBA", (W, H), (255, 255, 255, int(200 * fl))))
        if lt > strike_at:
            pulse = 0.5 + 0.5 * math.sin((lt - strike_at) * 10)
            v = self.red_vig.copy()
            v.putalpha(v.getchannel("A").point(lambda a: int(a * (0.4 + 0.4 * pulse))))
            c.alpha_composite(v)
            ti = text_img("⚠ FASTER THAN YOUR REACTION", 64, WHITE, 0, path=FONT_TITLE)
            paste(c, text_img("STRIKING SPEED", 120, WHITE, 0, path=FONT_TITLE), 540, 300)
            band_h = 110
            p = ease_out((lt - strike_at) / 0.3)
            band = Image.new("RGBA", (W, band_h), RED + (230,))
            c.alpha_composite(band.crop((0, 0, int(W * p), band_h)) if p > 0.01 else band.crop((0, 0, 1, 1)), (0, 1300))
            anim_text(c, ti, 540, 1300 + band_h / 2, t, s0 + strike_at + 0.1, rise=0)

    # ---- India map
    def _prep_map(self):
        geom = json.load(open(os.path.join(HERE, "assets", "india.json")))
        lon0, lon1, lat0, lat1 = 67.5, 98.0, 6.0, 37.5
        k = math.cos(math.radians(22))
        size = 930
        sx = size / ((lon1 - lon0) * k)
        mh = int((lat1 - lat0) * sx)
        ox, oy = (W - size) / 2, 470
        rings = [[(ox + (lo - lon0) * k * sx, oy + (lat1 - la) * sx) for lo, la in r[0]] for r in geom["coordinates"]]
        rings = [r for r in rings if len(r) > 2]
        self.map_rings = sorted(rings, key=len, reverse=True)
        main = self.map_rings[0]
        seg = np.linalg.norm(np.diff(np.array(main + [main[0]]), axis=0), axis=1)
        self.map_cum = np.concatenate([[0], np.cumsum(seg)])
        fill = Image.new("L", (W, H), 0)
        d = ImageDraw.Draw(fill)
        for r in self.map_rings:
            d.polygon(r, fill=255)
        self.map_mask = fill
        # glowing fill with an inner gradient
        y, x = np.mgrid[0:H, 0:W]
        gr = np.clip(1 - np.sqrt(((x - 540) / 600) ** 2 + ((y - 1000) / 700) ** 2), 0, 1)
        col = np.stack([90 + 120 * gr, 8 + 10 * gr, 16 + 12 * gr], -1).astype(np.uint8)
        f = Image.fromarray(col).convert("RGBA")
        f.putalpha(fill)
        self.map_fill = f
        rng = np.random.default_rng(11)
        pts = []
        arr = np.asarray(fill)
        while len(pts) < 34:
            px, py = rng.uniform(ox, ox + size), rng.uniform(oy, oy + mh)
            if arr[int(py), int(px)]:
                pts.append((px, py, rng.uniform(0, 2.2)))
        self.map_dots = pts

    def map(self, t, seg):
        s0, s1, _, _ = seg
        lt = t - s0
        c = self.bg.copy()
        # outline draws itself
        p = ease_in_out(lt / 1.3)
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        main = self.map_rings[0]
        n = np.searchsorted(self.map_cum, p * self.map_cum[-1])
        if n > 1:
            d.line(main[:n], fill=(255, 70, 80, 255), width=5, joint="curve")
        if p >= 1:
            for r in self.map_rings[1:]:
                d.line(r + [r[0]], fill=(255, 70, 80, 255), width=4)
        fa = ease_out((lt - 1.0) / 0.7)
        if fa > 0:
            f = self.map_fill.copy()
            f.putalpha(f.getchannel("A").point(lambda v: int(v * fa * 0.9)))
            c.alpha_composite(f)
        c.alpha_composite(glow(layer, RED, 14, 1.4))
        # pulsing points
        d = ImageDraw.Draw(c)
        for (x, y, delay) in self.map_dots:
            st = 1.5 + delay
            if lt < st:
                continue
            q = (lt - st) % 1.6 / 1.6
            r = 6 + 34 * q
            d.ellipse((x - r, y - r, x + r, y + r), outline=(255, 80, 90, int(200 * (1 - q))), width=3)
            d.ellipse((x - 6, y - 6, x + 6, y + 6), fill=(255, 220, 220, 255))
        # radar sweep line
        sweep_y = 470 + ((lt * 380) % 1100)
        d.line((60, sweep_y, W - 60, sweep_y), fill=(255, 60, 70, 60), width=2)
        # slow camera push on the whole map
        z = 1 + 0.06 * lt / (s1 - s0)
        a = 1 / z
        c = c.transform((W, H), Image.AFFINE, (a, 0, 540 * (1 - a), 0, a, 1000 * (1 - a)), Image.BILINEAR)
        cnt = MAP_COUNTER - s0
        if lt < cnt:
            anim_text(c, text_img("SNAKEBITE DEATHS", 104, WHITE, 0, path=FONT_TITLE), 540, 240, t, s0 + 0.2)
            anim_text(c, text_img("IN INDIA", 104, RED, 0, path=FONT_TITLE), 540, 350, t, s0 + 0.4)
        else:
            lc = lt - cnt
            q = ease_out(lc / 1.4)
            num = text_img(f"{int(15000 * q):,}–{int(20000 * q):,}", 150, YELLOW if q < 1 else WHITE, 0,
                           path=FONT_TITLE)
            hit = clamp(1 - abs(lc - 1.45) / 0.18)
            if q >= 1:
                num = glow(pad_img(num, 30), RED, 24, 1.6)
            paste(c, num, 540, 250, (1 + 0.08 * hit) * back_out(lc / 0.3), 1.0)
            anim_text(c, text_img("DEATHS EVERY YEAR", 64, RED, 0, path=FONT_TITLE), 540, 390, t, s0 + cnt + 0.5)
        c.alpha_composite(self.vignette)
        return c

    # ---- 43% infographic
    def chart(self, t, seg):
        s0, s1, _, _ = seg
        lt = t - s0
        c = self.bg.copy()
        anim_text(c, text_img("RUSSELL'S VIPER", 120, RED, 0, path=FONT_TITLE), 540, 230, t, s0 + 0.1)
        anim_text(c, text_img("caused", 52, WHITE, 0, path=FONT_BOLD), 540, 345, t, s0 + 0.3)
        # circular progress
        cx, cy, R, wd = 540, 760, 290, 54
        S = 2
        ring = Image.new("RGBA", (R * 2 * S + 200, R * 2 * S + 200), (0, 0, 0, 0))
        d = ImageDraw.Draw(ring)
        o = 100
        box = (o, o, o + 2 * R * S, o + 2 * R * S)
        d.arc(box, 0, 360, fill=(48, 44, 46, 255), width=wd * S)
        p = ease_in_out((lt - 0.6) / 2.0)
        pct = 43 * p
        if pct > 0.3:
            a1 = -90 + 360 * pct / 100
            d.arc(box, -90, a1, fill=RED + (255,), width=wd * S)
            # rounded caps
            for ang in (-90, a1):
                ex = o + R * S + (R * S - wd * S / 2) * math.cos(math.radians(ang))
                ey = o + R * S + (R * S - wd * S / 2) * math.sin(math.radians(ang))
                d.ellipse((ex - wd * S / 2, ey - wd * S / 2, ex + wd * S / 2, ey + wd * S / 2), fill=RED + (255,))
        ring = ring.resize((ring.width // S, ring.height // S), Image.LANCZOS)
        ring = glow(ring, RED, 22, 0.6 + 0.8 * p)
        pop = 1 + 0.06 * clamp(1 - abs(lt - 2.65) / 0.2)
        paste(c, ring, cx, cy, back_out(lt / 0.5, 1.4) * pop)
        num = text_img(f"{int(round(pct))}%", 230, WHITE, 0, path=FONT_TITLE)
        paste(c, num, cx, cy, pop, clamp(lt / 0.3))
        anim_text(c, text_img("of all snakebite deaths in India", 50, WHITE, 0, path=FONT_BOLD), 540, 1110, t, s0 + 2.4)
        # timeline 2000 -> 2019, then the comparison bars
        bars_at = 4.6
        if lt < bars_at + 0.3:
            a = clamp((bars_at + 0.3 - lt) / 0.3) * clamp((lt - 0.8) / 0.3)
            layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            d = ImageDraw.Draw(layer)
            x0, x1, y = 170, 910, 1290
            q = ease_in_out((lt - 0.8) / 2.2)
            d.line((x0, y, x1, y), fill=(80, 76, 78, 255), width=8)
            d.line((x0, y, x0 + (x1 - x0) * q, y), fill=YELLOW + (255,), width=8)
            for k, yr in enumerate(range(2000, 2020)):
                x = x0 + (x1 - x0) * k / 19
                if x <= x0 + (x1 - x0) * q + 1:
                    hgt = 16 if yr % 5 else 26
                    d.line((x, y - hgt, x, y + hgt), fill=YELLOW + (255,), width=4)
            d.ellipse((x0 + (x1 - x0) * q - 16, y - 16, x0 + (x1 - x0) * q + 16, y + 16), fill=WHITE + (255,))
            d.text((x0, y + 70), "2000", font=font(66, FONT_TITLE), fill=WHITE, anchor="mm")
            d.text((x1, y + 70), "2019", font=font(66, FONT_TITLE), fill=WHITE, anchor="mm")
            d.text((540, y - 70), "20 YEARS OF DATA", font=font(40, FONT_BOLD), fill=(200, 200, 200), anchor="mm")
            layer.putalpha(layer.getchannel("A").point(lambda v: int(v * a)))
            c.alpha_composite(layer)
        else:
            rows = [("Russell's Viper", 43, RED), ("Kraits", 18, (200, 200, 205)), ("Cobras", 12, (150, 150, 155))]
            d = ImageDraw.Draw(c)
            for i, (name, v, col) in enumerate(rows):
                st = bars_at + 0.3 + i * 0.25
                q = ease_out((lt - st) / 0.6)
                if q <= 0:
                    continue
                y = 1235 + i * 95
                d.text((120, y), name, font=font(44, FONT_BOLD), fill=WHITE, anchor="lm")
                bx0, bx1 = 470, 470 + 430 * v / 43 * q
                d.rounded_rectangle((bx0, y - 26, max(bx0 + 2, bx1), y + 26), 12, fill=col + (255,))
                d.text((bx1 + 18, y), f"{int(v * q)}%", font=font(48, FONT_TITLE), fill=WHITE, anchor="lm")
        d = ImageDraw.Draw(c)
        d.text((540, 1850), "Source: Million Death Study, India 2000–2019 (Suraweera et al., eLife 2020)",
               font=font(26, FONT_BOLD), fill=(150, 150, 150), anchor="mm")
        c.alpha_composite(self.vignette)
        return c

    def _tag(self, label, col):
        ti = text_img(label, 40, WHITE, 0, path=FONT_TITLE, shadow=False)
        w, h = ti.width + 50, 64
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(im).rounded_rectangle((0, 0, w - 1, h - 1), 14, fill=col + (255,))
        im.alpha_composite(ti, (25, (h - ti.height) // 2))
        return im

    def _indicator(self, c, t, st, x, y, label):
        if t < st:
            return
        d = ImageDraw.Draw(c)
        r = 62 * back_out((t - st) / 0.35)
        rr = r * (1 + 0.08 * math.sin((t - st) * 8))
        d.ellipse((x - rr, y - rr, x + rr, y + rr), outline=YELLOW + (255,), width=7)
        # label sits above or below the point, leader line grows towards it
        ly = y + 230 if y < 1000 else y - 230
        q = ease_out((t - st - 0.12) / 0.3)
        if q > 0:
            d.line((x, y + (rr if ly > y else -rr), x, y + (ly - y) * q), fill=YELLOW + (255,), width=6)
            ti = text_img(label, 50, BLACK, 0, path=FONT_BOLD, shadow=False)
            pill = Image.new("RGBA", (ti.width + 48, ti.height + 30), (0, 0, 0, 0))
            ImageDraw.Draw(pill).rounded_rectangle((0, 0, pill.width - 1, pill.height - 1), 18, fill=YELLOW + (255,))
            pill.alpha_composite(ti, (24, 15))
            px = min(max(x, pill.width / 2 + 30), W - pill.width / 2 - 30)
            paste(c, add_shadow(pill, 10, 4), px, ly, 1.0, q)

    # ---- 10-foot safety diagram
    def distance(self, t, seg):
        s0, s1, _, opt = seg
        lt = t - s0
        c = self.bg.copy()
        band, _ = self.place_photo(opt["img"], lt, s1 - s0, {"focus": (0.6, 0.5), "zoom": (1.0, 1.08)}, cy=700)
        mask = Image.new("L", (W, H), 0)
        ImageDraw.Draw(mask).rectangle((0, 330, W, 1070), fill=255)
        c.paste(band, (0, 0), mask.filter(ImageFilter.GaussianBlur(30)))
        c.alpha_composite(self._hazard(lt), (0, 200))
        anim_text(c, text_img("⚠ KEEP A SAFE DISTANCE", 78, WHITE, 0, path=FONT_TITLE), 540, 330, t, s0 + 0.1)
        d = ImageDraw.Draw(c)
        base = 1500
        # snake (round crop of the photo) on the left, person on the right
        img, _ = self.photos[opt["img"]]
        if not hasattr(self, "_thumb"):
            cx, cy = 0.84 * img.width, 0.66 * img.height
            r = img.height * 0.2
            th = img.crop((int(cx - r), int(cy - r), int(cx + r), int(cy + r))).resize((190, 190), Image.LANCZOS)
            m = Image.new("L", (190, 190), 0)
            ImageDraw.Draw(m).ellipse((0, 0, 189, 189), fill=255)
            tt = Image.new("RGBA", (210, 210), (0, 0, 0, 0))
            ImageDraw.Draw(tt).ellipse((0, 0, 209, 209), fill=RED + (255,))
            tt.paste(th, (10, 10), m)
            self._thumb = tt
        paste(c, self._thumb, 190, base - 100, back_out((lt - 0.15) / 0.35))
        self._person(c, 900, base, 330, ease_out((lt - 0.3) / 0.35))
        q = ease_out((lt - 0.45) / 0.7)
        x0, x1, y = 310, 800, base - 40
        if q > 0:
            xe = x0 + (x1 - x0) * q
            d.line((x0, y, xe, y), fill=YELLOW + (255,), width=9)
            for k in range(11):
                x = x0 + (x1 - x0) * k / 10
                if x <= xe + 1:
                    hgt = 24 if k % 5 == 0 else 14
                    d.line((x, y - hgt, x, y + hgt), fill=YELLOW + (255,), width=4)
            d.polygon([(x0 - 10, y), (x0 + 22, y - 22), (x0 + 22, y + 22)], fill=YELLOW + (255,))
            if q >= 0.99:
                d.polygon([(x1 + 10, y), (x1 - 22, y - 22), (x1 - 22, y + 22)], fill=YELLOW + (255,))
        paste(c, glow(pad_img(text_img("10 FEET", 170, YELLOW, 0, path=FONT_TITLE), 20), (0, 0, 0), 16, 2),
              555, 1240, pop_scale(t, s0 + 0.9))
        anim_text(c, text_img("(3 METRES)", 52, WHITE, 0, path=FONT_TITLE), 555, 1365, t, s0 + 1.1)
        c.alpha_composite(self.vignette)
        return c

    def _person(self, c, x, yb, h, a):
        if a <= 0:
            return
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        col = (255, 255, 255, int(235 * a))
        hr = h * 0.075
        d.ellipse((x - hr, yb - h, x + hr, yb - h + 2 * hr), fill=col)
        bw = h * 0.13
        d.rounded_rectangle((x - bw, yb - h + 2.3 * hr, x + bw, yb - h * 0.45), int(bw * 0.5), fill=col)
        lw = h * 0.055
        d.rounded_rectangle((x - bw + 2, yb - h * 0.5, x - bw + 2 + 2 * lw, yb), int(lw), fill=col)
        d.rounded_rectangle((x + bw - 2 - 2 * lw, yb - h * 0.5, x + bw - 2, yb), int(lw), fill=col)
        aw = h * 0.045
        d.rounded_rectangle((x - bw - 2 * aw - 4, yb - h + 2.5 * hr, x - bw - 4, yb - h * 0.5), int(aw), fill=col)
        d.rounded_rectangle((x + bw + 4, yb - h + 2.5 * hr, x + bw + 2 * aw + 4, yb - h * 0.5), int(aw), fill=col)
        c.alpha_composite(glow(layer, (0, 0, 0), 10, 1.5))

    def _hazard(self, lt):
        band = Image.new("RGBA", (W, 70), YELLOW + (255,))
        d = ImageDraw.Draw(band)
        off = int(lt * 120) % 80
        for x in range(-80, W + 80, 80):
            d.polygon([(x + off, 0), (x + off + 40, 0), (x + off + 10, 70), (x + off - 30, 70)], fill=(15, 15, 15, 255))
        return band

    # ---- RKO cartoon
    def rko(self, t, seg):
        """Your RKO clip: plays at real speed, freezes on the slam with a flash, shake and punch-in."""
        if not self.rko_frames:
            return self.rko_cartoon(t, seg)
        s0, s1, _, _ = seg
        lt = t - s0
        frames, bg = self.rko_frames
        n = len(frames)
        impact = RKO_IMPACT
        hold = RKO_FREEZE
        g = lt if lt < impact else (impact if lt < impact + hold else lt - hold)
        fr = frames[min(n - 1, int(g / 0.06))]
        # punch in on the slam, ease back out after the freeze
        z = 1.3
        if lt >= impact:
            q = lt - impact
            z += 0.35 * ease_out(q / 0.08) if q < hold else 0.35 * (1 - ease_in_out((q - hold) / 0.3))
        w = int(W * z)
        h = int(w * fr.height / fr.width)
        c = bg.copy()
        fg = fr.resize((w, h), Image.BICUBIC)
        c.paste(fg, ((W - w) // 2, 960 - h // 2), feather_mask(fg.size))
        c = c.convert("RGBA")
        c.alpha_composite(self.vignette)
        if lt >= impact:
            q = lt - impact
            fl = clamp(1 - q / 0.12)
            if fl > 0:
                c.alpha_composite(Image.new("RGBA", (W, H), (255, 255, 255, int(255 * fl))))
            rko = text_img("RKO!", 300, YELLOW, 16, (170, 0, 10), path=FONT_TITLE)
            paste(c, rko, 540, 360, 1 + 1.4 * clamp(1 - q / 0.12), 1.0, angle=-5)
            if q > 0.12:
                paste(c, text_img("OUT OF NOWHERE!", 110, WHITE, 12, path=FONT_TITLE), 540, 1560,
                      back_out((q - 0.12) / 0.25), 1.0, angle=-3)
            amp = 34 * clamp(1 - q / 0.55)
            if amp > 0:
                c = ImageChops.offset(c, int(amp * math.sin(lt * 97)), int(amp * math.cos(lt * 83)))
        return c

    def rko_cartoon(self, t, seg):
        s0, s1, _, _ = seg
        lt = t - s0
        hit = 0.45
        c = Image.new("RGBA", (W, H), (255, 200, 0, 255))
        d = ImageDraw.Draw(c)
        ang0 = lt * 30
        for k in range(28):
            a0 = math.radians(ang0 + k * 360 / 28)
            a1 = a0 + math.radians(360 / 56)
            d.polygon([(540, 900), (540 + 2400 * math.cos(a0), 900 + 2400 * math.sin(a0)),
                       (540 + 2400 * math.cos(a1), 900 + 2400 * math.sin(a1))], fill=(230, 40, 30, 255))
        c.alpha_composite(halftone())
        if lt < hit:
            # the viper launches out of nowhere along an arc, spinning
            p = ease_in_out(lt / hit)
            x = lerp_(1250, 560, p)
            y = lerp_(1750, 900, p) - math.sin(p * math.pi) * 380
            for k in range(6):  # speed lines
                yy = y - 120 + k * 50
                d.line((x + 200, yy, x + 600, yy + 120), fill=(255, 255, 255, 200), width=10)
            paste(c, self.cartoon, x, y, 0.9, 1.0, angle=-200 * p + 30)
        else:
            q = lt - hit
            # impact star
            star = Image.new("RGBA", (900, 900), (0, 0, 0, 0))
            sd = ImageDraw.Draw(star)
            pts = []
            for k in range(32):
                rr = 440 if k % 2 == 0 else 250
                a = math.radians(k * 360 / 32 + q * 40)
                pts.append((450 + rr * math.cos(a), 450 + rr * math.sin(a)))
            sd.polygon(pts, fill=WHITE + (255,), outline=BLACK + (255,), width=10)
            paste(c, star, 540, 900, back_out(q / 0.2, 2.5))
            paste(c, self.cartoon, 540, 1300, 0.85 + 0.05 * math.sin(q * 30) * clamp(1 - q / 0.5), 1.0,
                  angle=8 * math.sin(q * 25) * clamp(1 - q / 0.6))
            rko = text_img("RKO!", 330, YELLOW, 18, (170, 0, 10), path=FONT_TITLE)
            sc = 1 + 1.6 * clamp(1 - q / 0.12)
            paste(c, rko, 540, 860, sc, 1.0, angle=-6)
            if q > 0.18:
                paste(c, text_img("OUT OF NOWHERE!", 110, WHITE, 12, path=FONT_TITLE), 540, 1080,
                      back_out((q - 0.18) / 0.25), 1.0, angle=-4)
            flash = clamp(1 - q / 0.12)
            if flash > 0:
                c.alpha_composite(Image.new("RGBA", (W, H), (255, 255, 255, int(255 * flash))))
            # screen shake
            amp = 30 * clamp(1 - q / 0.6)
            if amp > 0:
                c = ImageChops.offset(c, int(amp * math.sin(lt * 97)), int(amp * math.cos(lt * 83)))
        return c

    # ---- Sathish Talks end card
    def brand(self, t, seg):
        s0, s1, _, _ = seg
        lt = t - s0
        c = self.bg.copy()
        logo = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
        ld = ImageDraw.Draw(logo)
        ld.rounded_rectangle((0, 0, 199, 199), 48, fill=RED + (255,))
        ld.text((100, 104), "ST", font=font(110, FONT_TITLE), fill=WHITE, anchor="mm")
        paste(c, glow(pad_img(logo, 40), RED, 30, 1.2), 540, 700, back_out(lt / 0.35))
        wipe_text(c, text_img("SATHISH TALKS", 150, WHITE, 0, path=FONT_TITLE), 540, 920, t, s0 + 0.15, 0.4)
        p = ease_out((lt - 0.4) / 0.35)
        d = ImageDraw.Draw(c)
        if p > 0:
            d.rectangle((540 - 330 * p, 1020, 540 + 330 * p, 1030), fill=YELLOW + (255,))
        anim_text(c, text_img("@SathishTalks", 60, YELLOW, 0, path=FONT_BOLD), 540, 1110, t, s0 + 0.45)
        c.alpha_composite(self.vignette)
        return c


_panel_shade = None


def make_panel_shade():
    global _panel_shade
    if _panel_shade is None:
        g = np.zeros((H // 2, W), np.float32)
        y = np.arange(H // 2)[:, None]
        g += np.clip(1 - y / 380, 0, 1) * 200
        im = Image.new("RGBA", (W, H // 2), (0, 0, 0, 255))
        im.putalpha(Image.fromarray(g.astype(np.uint8)))
        _panel_shade = im
    return _panel_shade


_half = None


def halftone():
    global _half
    if _half is None:
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        for y in range(0, H, 36):
            for x in range((y // 36 % 2) * 18, W, 36):
                r = 3 + 9 * (y / H)
                d.ellipse((x - r, y - r, x + r, y + r), fill=(120, 0, 0, 70))
        _half = im
    return _half


_emo = {}


def emoji_cached(ch, size):
    if (ch, size) not in _emo:
        _emo[(ch, size)] = _emoji_img(ch, size)
    return _emo[(ch, size)]


# ---------------------------------------------------------------- captions

KEYWORDS_RED = ["russell", "viper", "43", "15,000", "20,000", "15000", "20000", "rko", "விரியன்", "கண்ணாடி"]
KEYWORDS_YELLOW = ["paambu", "malai", "kannadi", "10", "feet", "பாம்பு", "மலை", "python"]


def load_captions():
    """captions.json: [{"start": s, "end": e, "text": "..."}] (Tamil, Tanglish or English).
    Lines are split into 2-4 word chunks timed by word length."""
    path = os.path.join(HERE, "captions.json")
    if not os.path.exists(path):
        return []
    lines = [l for l in json.load(open(path)) if l.get("text", "").strip()]
    chunks = []
    for l in lines:
        words = l["text"].split()
        groups, i = [], 0
        while i < len(words):
            n = min(3, len(words) - i)
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


def draw_caption(c, t, chunks, y=1600):
    for s, e, words in chunks:
        if s <= t < e:
            key = (s, tuple(words))
            if key not in _cap_cache:
                _cap_cache[key] = [(text_img(w if any("஀" <= ch <= "௿" for ch in w) else w.upper(),
                                             84, word_color(w)[0], 9), word_color(w)[1]) for w in words]
            ims = _cap_cache[key]
            gap = 22
            tw = sum(i.width for i, _ in ims) + gap * (len(ims) - 1)
            sc_all = min(1.0, 980 / tw)
            x = 540 - tw * sc_all / 2
            for k, (im, hot) in enumerate(ims):
                st = s + k * min(0.08, (e - s) / (len(ims) + 1))
                sc = back_out((t - st) / 0.18, 2.6 if hot else 1.6) * sc_all * (1.08 if hot else 1.0)
                paste(c, im, x + im.width * sc_all / 2, y, sc, 1.0 if t >= st else 0)
                x += (im.width + gap) * sc_all
            return


# ---------------------------------------------------------------- transitions

def whip(img, t):
    """Directional motion-blur + flash around each cut (except into/out of the RKO, which flashes)."""
    for cut in CUTS:
        d = t - cut
        if -0.1 <= d < 0.1:
            s = 1 - abs(d) / 0.1
            arr = np.asarray(img.convert("RGB")).astype(np.float32)
            acc = np.zeros_like(arr)
            shifts = np.linspace(-90 * s, 90 * s, 7).astype(int)
            for sh in shifts:
                acc += np.roll(arr, sh, axis=1)
            acc /= len(shifts)
            acc = acc * (1 - 0.25 * s) + 255 * 0.25 * s * (abs(d) < 0.034)
            return Image.fromarray(np.clip(acc, 0, 255).astype(np.uint8))
    return img


# ---------------------------------------------------------------- main

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    src = args[0]
    out = args[1] if len(args) > 1 else os.path.join(HERE, "output", "russells_viper_reel.mp4")
    opt = lambda k, d: float(sys.argv[sys.argv.index(k) + 1]) if k in sys.argv else d
    preview = opt("--preview", None)
    t_from = opt("--from", 0.0)
    stills = "--stills" in sys.argv
    os.makedirs(WORK, exist_ok=True)

    audio.build(WORK)
    ed = Edit(src)
    dur = (preview or DURATION - t_from)
    footage = Reader(src, start=t_from)
    silent = os.path.join(WORK, "video.mp4")
    enc = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
         "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "17",
         "-pix_fmt", "yuv420p", silent], stdin=subprocess.PIPE)
    n_frames = int(round(dur * FPS))
    for n in range(n_frames):
        t = t_from + n / FPS
        frame = footage.get(n)          # always consume, so your footage stays in sync
        seg = segment_at(t)
        kind = seg[2]
        if kind == "me":
            c = ed.me(frame, t, seg)
        else:
            c = getattr(ed, kind)(t, seg)
        if kind not in ("brand", "rko"):
            brand_bug(c)
        draw_caption(c, t, ed.captions)
        img = c.convert("RGB")
        if kind not in ("me", "rko"):
            img = grain(img, n, 0.8)
        img = whip(img, t)
        enc.stdin.write(img.tobytes())
        if stills and n % (FPS // 2) == 0:
            img.resize((270, 480)).save(os.path.join(WORK, f"still_{t:05.1f}.jpg"), quality=80)
        if n % 150 == 0:
            print(f"  {t:5.1f}s", flush=True)
    enc.stdin.close()
    enc.wait()

    # Voice: the original track, untouched, at full level. Music ducks under it; SFX stay subtle.
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", silent, "-ss", str(t_from), "-i", src,
         "-ss", str(t_from), "-i", os.path.join(WORK, "music.wav"),
         "-ss", str(t_from), "-i", os.path.join(WORK, "sfx.wav"),
         "-filter_complex",
         "[1:a]aresample=44100,asplit=2[voice][key];"
         "[2:a]volume=0.34[mus];"
         "[mus][key]sidechaincompress=threshold=0.02:ratio=8:attack=20:release=400:makeup=1[duck];"
         "[voice][duck][3:a]amix=inputs=3:duration=first:normalize=0,alimiter=limit=0.97:level=false[a]",
         "-map", "0:v", "-map", "[a]", "-c:v", "libx264", "-preset", "slow", "-crf", "20",
         "-maxrate", "7M", "-bufsize", "14M", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
         "-t", str(dur), "-movflags", "+faststart", out], check=True)
    print("wrote", out)


if __name__ == "__main__":
    main()
