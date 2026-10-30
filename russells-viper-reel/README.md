# Russell's Viper reel: edit project

Edits on top of the original 53 s talking-head clip. The footage and voice are never changed:
frames only get zoomed or shaken and have graphics drawn over them, and the voice track is mixed
in at full level.

```
python3 render.py <original.mov>            # -> output/russells_viper_reel.mp4 (1080x1920, 30 fps, H.264 + AAC)
python3 render.py <original.mov> out.mp4 --preview 8   # render only the first 8 s
```

Needs `ffmpeg`, Python 3, `numpy` and `Pillow`. A full render takes about 2 minutes.

## Files

| File | What it does |
|---|---|
| `timeline.py` | All timings: section starts, the `RKO_HIT` moment, and the pauses used for the zoom rhythm |
| `captions.json` | Caption lines. Each entry is one spoken phrase with its start and end time already measured from your audio. Fill in `text` in Tanglish. |
| `render.py` | Draws the graphics, captions, zooms and glitches, then encodes the video and mixes the audio |
| `audio.py` | Generates the background music and every SFX, so there's no copyrighted audio |
| `assets/india.json` | India outline for the map (Natural Earth, public domain) |

## Things you can tweak

- **Captions**: type what you say into each `text` field of `captions.json` and re-render. Each line is split
  into 2 to 4 word chunks that pop in. Keywords (paambu, Russell's Viper, 43%, 15,000, RKO and so on)
  are coloured red or yellow automatically.
- **RKO timing**: if the freeze-frame lands early or late, change `RKO_HIT` in `timeline.py`.
- **Real snake photos**: put royalty-free photos at `assets/viper.jpg` and `assets/python.jpg`. They replace the drawn
  illustrations on every card.
- **Music and SFX volume**: the music level is `volume=0.32` in `render.py`. SFX levels are the `gain_db` values in `audio.build()`.
