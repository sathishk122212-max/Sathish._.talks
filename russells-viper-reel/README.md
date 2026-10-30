# Russell's Viper reel: edit project

Edits on top of the original 53 s talking-head clip. Your voice track plays untouched from start
to finish. On screen, the edit cuts between your footage (about 40%: zoomed or cropped only, never
altered) and full-screen visuals (about 60%).

```
python3 render.py <original.mov>                        # -> output/russells_viper_reel.mp4 (1080x1920, 30 fps)
python3 render.py <original.mov> out.mp4 --preview 8    # render only the first 8 s
```

Needs `ffmpeg`, Python 3, `numpy` and `Pillow`. A full render takes about 2–3 minutes.

## Running order

| Time | On screen |
|---|---|
| 0–2 s | You, slow push-in |
| 2–4 s | Kinetic type: MALAI PAAMBU? / PYTHON? crossed out |
| 4–6 s | Viper photo: red flash, snap-in, slow push to the head, light leak, hiss |
| 6–8 s | You |
| 8–10.5 s | Viper photo + RUSSELL'S VIPER / கண்ணாடி விரியன் title |
| 10.5–16.4 s | Full-screen India map draws itself, then the 15,000–20,000 counter |
| 16.4–19 s | You |
| 19–27 s | 43% ring infographic, 2000–2019 timeline, viper/krait/cobra bars |
| 27–28 s | You |
| 28–32.4 s | "How to identify" callouts on two photos |
| 32.4–34.5 s | You |
| 34.5–37.4 s | Head-on photo: STRIKING SPEED, lunge zoom, flash, shake, warning banner |
| 37.4–39.9 s | 10 FEET (3 m) safe-distance diagram |
| 39.9–45.8 s | You, with the RKO cartoon at `RKO_HIT` |
| 45.8–51.2 s | You + COMMENT BELOW / Follow @SathishTalks |
| 51.2–52.3 s | Sathish Talks end card |

## Files

| File | What it does |
|---|---|
| `timeline.py` | The edit list: every segment, its photo, the camera keyframes (`focus`, `zoom`), callouts, and `RKO_HIT` |
| `captions.json` | Subtitle lines with start and end times already measured from your audio. Fill in `text` (Tamil works) and re-render. |
| `render.py` | Draws every segment, the transitions and the captions, then encodes and mixes the audio |
| `gfx.py` | Text (English, Tamil, emoji), easing and compositing helpers |
| `audio.py` | Generates the background music and every SFX, so there's no copyrighted audio |
| `assets/photos/` | Your snake photos (`viper1.jpg` … `viper6.jpg`) |
| `assets/fonts/` | Anton, Bebas Neue and Noto Sans Tamil (all under the Open Font License) |

## Tweaks

- **RKO timing**: change `RKO_HIT` in `timeline.py`.
- **Swap a photo**: replace the file in `assets/photos/`, or point a segment's `img` at a new file name. `focus` is the
  point (0–1 across, 0–1 down) the camera pushes towards.
- **Add a python photo**: save it as `assets/photos/python.jpg` and change the 2–4 s segment in `timeline.py` to
  `"photo", {"img": "python", ...}`.
