"""Synthesises the background music bed and every sound effect, so the reel has
no copyrighted or third-party audio. Writes two WAVs: music.wav (gets ducked under
the voice in render.py) and sfx.wav (already mixed at subtle levels)."""
import wave

import numpy as np

from timeline import *

SR = 44100
rng = np.random.default_rng(7)


def t_axis(dur):
    return np.arange(int(dur * SR)) / SR


def lowpass(x, cutoff):
    """One-pole lowpass; cutoff may be a scalar or a per-sample array (for sweeps)."""
    cutoff = np.broadcast_to(np.asarray(cutoff, dtype=float), x.shape)
    a = np.exp(-2 * np.pi * cutoff / SR)
    y = np.empty_like(x)
    acc = 0.0
    for i in range(len(x)):
        acc = (1 - a[i]) * x[i] + a[i] * acc
        y[i] = acc
    return y


def fft_band(x, lo, hi):
    spec = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    spec[(f < lo) | (f > hi)] = 0
    return np.fft.irfft(spec, len(x))


def norm(x, peak=1.0):
    m = np.max(np.abs(x)) or 1.0
    return x / m * peak


# ---------- sound effects ----------

def sfx_suspense():
    t = t_axis(3.0)
    drone = np.sin(2 * np.pi * 55 * t) + 0.5 * np.sin(2 * np.pi * 58.3 * t)  # beating low drone
    riser_f = 200 + 900 * (t / t[-1]) ** 2
    riser = 0.25 * np.sin(2 * np.pi * np.cumsum(riser_f) / SR)
    noise = lowpass(rng.standard_normal(len(t)), 300 + 3000 * (t / t[-1]) ** 2) * 0.6
    env = np.clip(t / 2.6, 0, 1) ** 2 * np.clip((3.0 - t) / 0.2, 0, 1)
    return norm((drone * 0.6 + riser + noise) * env)


def sfx_ding():
    t = t_axis(1.6)
    x = sum(a * np.sin(2 * np.pi * f * t) * np.exp(-t * d)
            for f, a, d in [(1568, 1.0, 3.5), (2352, 0.45, 5), (3136, 0.25, 7), (4704, 0.1, 9)])
    return norm(x * np.clip(t / 0.003, 0, 1))


def sfx_heartbeat():
    def thump(dur=0.22, f0=70):
        t = t_axis(dur)
        f = f0 * np.exp(-t * 6)
        return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 18)
    beat = np.zeros(int(0.9 * SR))
    lub, dub = thump(), thump(f0=60) * 0.7
    beat[:len(lub)] += lub
    beat[int(0.28 * SR):int(0.28 * SR) + len(dub)] += dub
    return norm(np.tile(beat, 2))


def sfx_impact():
    t = t_axis(1.4)
    f = 40 + 120 * np.exp(-t * 14)
    boom = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 3.2)
    crack = lowpass(rng.standard_normal(len(t)), 2500) * np.exp(-t * 30) * 0.8
    return norm(boom + crack)


def sfx_whoosh(dur=0.7, bright=1.0):
    t = t_axis(dur)
    p = t / dur
    env = np.sin(np.pi * p) ** 2
    cut = (400 + 5000 * bright * np.sin(np.pi * p) ** 1.5)
    x = lowpass(rng.standard_normal(len(t)), cut)
    x -= lowpass(x, 150)
    return norm(x * env)


def sfx_warning():
    out = []
    for f in (880, 660, 880, 660):
        t = t_axis(0.16)
        tone = np.sign(np.sin(2 * np.pi * f * t)) * 0.3 + np.sin(2 * np.pi * f * t)
        tone = lowpass(tone, 3000) * np.clip(t / 0.005, 0, 1) * np.clip((0.16 - t) / 0.02, 0, 1)
        out += [tone, np.zeros(int(0.04 * SR))]
    return norm(np.concatenate(out))


def sfx_pop():
    t = t_axis(0.12)
    f = 300 + 900 * np.exp(-t * 60)
    return norm(np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 35))


def sfx_glitch():
    n = int(0.22 * SR)
    x = np.zeros(n)
    for _ in range(7):
        s = rng.integers(0, n - 800)
        L = rng.integers(300, 1500)
        L = min(L, n - s)
        x[s:s + L] += np.round(rng.standard_normal(L) * 3) / 3 * rng.uniform(0.3, 1)
    x += np.sign(np.sin(2 * np.pi * 120 * t_axis(0.22))) * 0.15
    return norm(fft_band(x, 200, 9000))


def sfx_rko_hit():
    """Big wrestling-style slam: reversed swell into a heavy boom + crowd-ish noise tail.
    (Original synth, not the WWE sound.)"""
    swell = sfx_whoosh(0.45, 1.3)[:int(0.3 * SR)]
    swell *= np.linspace(0, 1, len(swell)) ** 2
    t = t_axis(2.2)
    f = 35 + 160 * np.exp(-t * 10)
    boom = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 2.2)
    slap = fft_band(rng.standard_normal(len(t)), 800, 6000) * np.exp(-t * 25)
    crowd = fft_band(rng.standard_normal(len(t)), 300, 2500) * np.clip(t / 0.15, 0, 1) * np.exp(-t * 1.6) * 0.35
    hit = norm(boom * 1.0 + norm(slap) * 0.5 + norm(crowd) * 0.25)
    return norm(np.concatenate([swell * 0.5, hit]))


def sfx_tick():
    t = t_axis(0.03)
    return norm(np.sin(2 * np.pi * 2500 * t) * np.exp(-t * 200))


# ---------- music bed ----------

def music_bed(dur):
    """Dark documentary pad: A-minor drone, slow pulse, sparse high bell."""
    t = t_axis(dur)
    out = np.zeros(len(t))
    # drone (A1 + E2 + slow detuned layer)
    for f, a in [(55, 0.5), (82.41, 0.3), (110.3, 0.2), (130.8, 0.12)]:
        out += a * np.sin(2 * np.pi * f * t + 0.3 * np.sin(2 * np.pi * 0.07 * t))
    # chord change every 8 s: Am -> F -> Dm -> E
    chords = [(220, 261.6, 329.6), (174.6, 220, 261.6), (146.8, 174.6, 220), (164.8, 207.7, 246.9)]
    pad = np.zeros(len(t))
    for i in range(int(dur // 8) + 1):
        s, e = int(i * 8 * SR), min(len(t), int((i + 1) * 8 * SR) + SR)
        if s >= len(t):
            break
        tt = t[s:e] - t[s]
        env = np.clip(tt / 2.0, 0, 1) * np.clip((tt[-1] - tt) / 1.0, 0, 1)
        for f in chords[i % 4]:
            pad[s:e] += env * (np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(2 * np.pi * f * 2.003 * tt)) * 0.12
    out += lowpass(pad, 1200)
    # pulse (heartbeat-like kick at 80 bpm), enters after the hook
    beat = 60 / 80
    kick_t = t_axis(0.3)
    kick = np.sin(2 * np.pi * np.cumsum(45 + 70 * np.exp(-kick_t * 25)) / SR) * np.exp(-kick_t * 12)
    bt = 7.0
    while bt < dur - 0.5:
        s = int(bt * SR)
        seg = kick[:len(out) - s]
        out[s:s + len(seg)] += seg * 0.55
        bt += beat
    # sparse bell
    for bt in np.arange(3.0, dur, 6.0):
        s = int(bt * SR)
        bl = t_axis(2.0)
        bell = np.sin(2 * np.pi * 880 * bl) * np.exp(-bl * 2.5) * 0.08
        seg = bell[:len(out) - s]
        out[s:s + len(seg)] += seg
    fade = np.clip(t / 1.0, 0, 1) * np.clip((dur - t) / 1.5, 0, 1)
    return norm(out * fade, 0.9)


def place(track, clip, at, gain_db):
    s = int(at * SR)
    if s >= len(track):
        return
    seg = clip[:len(track) - s] * 10 ** (gain_db / 20)
    track[s:s + len(seg)] += seg


def write_wav(path, x):
    x = np.clip(x, -1, 1)
    data = (np.stack([x, x], 1) * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data.tobytes())


def sfx_hiss(dur=1.2):
    t = t_axis(dur)
    x = fft_band(rng.standard_normal(len(t)), 3000, 9000)
    env = np.clip(t / 0.08, 0, 1) * np.clip((dur - t) / 0.5, 0, 1)
    return norm(x * env)


def sfx_boing():
    t = t_axis(0.6)
    f = 180 + 260 * np.exp(-t * 4) * (1 + 0.35 * np.sin(2 * np.pi * 14 * t))
    return norm(np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 4))


def sfx_riser(dur=1.0):
    t = t_axis(dur)
    f = 300 + 1500 * (t / dur) ** 2
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * 0.4 + lowpass(rng.standard_normal(len(t)), 400 + 6000 * (t / dur) ** 2)
    return norm(x * (t / dur) ** 2)


def build(out_dir):
    n = int(DURATION * SR) + SR
    sfx = np.zeros(n)
    # levels are relative to full scale; the voice peaks near 0 dBFS, so these stay under it
    place(sfx, sfx_suspense(), 0.0, -22)
    for c in CUTS:                                    # every cut gets a soft whoosh
        place(sfx, sfx_whoosh(0.5), c - 0.25, -24)
    for s0, s1, kind, opt in SEGMENTS:
        fx = opt.get("fx")
        if kind == "words":
            place(sfx, sfx_impact(), s0 + 0.02, -24)
            place(sfx, sfx_pop(), s0 + 0.72, -20)
            place(sfx, sfx_glitch(), s0 + 1.35, -22)      # crossed out
        elif fx == "reveal":
            place(sfx, sfx_impact(), s0 + 0.02, -18)
            place(sfx, sfx_hiss(1.4), s0 + 0.5, -24)
        elif fx == "title":
            place(sfx, sfx_ding(), s0 + 0.3, -20)
        elif kind == "map":
            place(sfx, sfx_impact(), s0 + 0.05, -22)
            place(sfx, sfx_heartbeat(), MAP_COUNTER, -16)
            for k in range(14):
                place(sfx, sfx_tick(), MAP_COUNTER + 0.05 + k * 0.1, -32)
            place(sfx, sfx_impact(), MAP_COUNTER + 1.45, -20)
        elif kind == "chart":
            place(sfx, sfx_whoosh(0.9, 1.2), s0 + 0.5, -20)   # data-reveal whoosh
            place(sfx, sfx_pop(), s0 + 2.65, -20)
            for k in range(3):
                place(sfx, sfx_pop(), s0 + 4.9 + k * 0.25, -26)
        elif fx == "identify":
            for _, _, st in opt.get("notes", []):
                place(sfx, sfx_pop(), s0 + st, -22)
        elif fx == "strike":
            place(sfx, sfx_hiss(1.0), s0 + 0.1, -26)
            hit = s0 + (s1 - s0) * 0.34
            place(sfx, sfx_whoosh(0.3, 1.8), hit - 0.2, -16)  # fast whoosh
            place(sfx, sfx_impact(), hit, -18)
            place(sfx, sfx_warning(), hit + 0.45, -26)
        elif kind == "distance":
            place(sfx, sfx_warning(), s0 + 0.15, -26)
            place(sfx, sfx_pop(), s0 + 0.9, -20)
        elif kind == "rko":
            place(sfx, sfx_whoosh(0.5, 1.4), s0 + RKO_IMPACT - 0.45, -18)   # the jump
            place(sfx, sfx_rko_hit(), s0 + RKO_IMPACT - 0.3, -13)         # the slam
        elif kind == "brand":
            place(sfx, sfx_riser(0.6), s0 - 0.5, -26)
            place(sfx, sfx_impact(), s0 + 0.05, -22)
        elif opt.get("end"):
            place(sfx, sfx_pop(), s0 + 0.2, -18)
            place(sfx, sfx_pop(), s0 + 1.4, -18)
            place(sfx, sfx_ding(), s0 + 3.0, -22)          # follow tap
    write_wav(f"{out_dir}/sfx.wav", sfx)

    music = music_bed(DURATION)
    # dip the music for the RKO so the slam lands, then bring it back
    t = np.arange(len(music)) / SR
    dip = 1 - 0.8 * np.clip(1 - np.abs(t - (RKO_HIT + RKO_IMPACT)) / 1.0, 0, 1)
    write_wav(f"{out_dir}/music.wav", music * dip)


if __name__ == "__main__":
    import sys
    build(sys.argv[1] if len(sys.argv) > 1 else ".")
