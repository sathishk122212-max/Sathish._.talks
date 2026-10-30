"""Edit decision list for the Russell's Viper reel. All times are seconds of the original clip.

The voice track always plays straight through, untouched. Each segment below only decides
what is on screen at that moment. Cuts are snapped to the natural pauses in the speech
(found with ffmpeg silencedetect), so pictures change between phrases.
"""

DURATION = 52.29

RKO_HIT = 41.90      # the moment you say "RKO". Change this one number if the hit is early or late.
RKO_LEN = 1.6        # length of the RKO cartoon

# (start, end, kind, options). kind "me" = your original footage, "photo" = one of your photos
# with keyframed camera moves. "focus" is the point (0-1 across, 0-1 down) the camera pushes towards.
SEGMENTS = [
    (0.00, 2.00, "me", {"push": 0.08}),
    (2.00, 4.00, "words", {}),                                  # Malai Paambu? -> python? -> NO
    (4.00, 6.15, "photo", {"img": "viper2", "focus": (0.86, 0.22), "zoom": (1.0, 1.9), "fx": "reveal"}),
    (6.15, 8.30, "me", {}),
    (8.30, 10.50, "photo", {"img": "viper6", "focus": (0.17, 0.36), "zoom": (1.25, 1.6), "fx": "title"}),
    (10.50, 16.40, "map", {}),
    (16.40, 19.00, "me", {}),
    (19.00, 27.10, "chart", {}),
    (27.10, 28.00, "me", {}),
    (28.00, 30.20, "photo", {"img": "viper3", "focus": (0.6, 0.5), "zoom": (1.0, 1.12), "fx": "identify",
                             "notes": [((0.84, 0.72), "Flat, triangular head", 0.35),
                                       ((0.44, 0.63), "Dark spots ringed in black & white", 1.0)]}),
    (30.20, 32.40, "photo", {"img": "viper1", "focus": (0.5, 0.5), "zoom": (1.0, 1.1), "fx": "identify",
                             "notes": [((0.62, 0.45), "Thick, heavy body", 0.25),
                                       ((0.2, 0.68), "Loud hiss when disturbed", 0.9)]}),
    (32.40, 34.46, "me", {}),
    (34.46, 37.40, "photo", {"img": "viper4", "focus": (0.47, 0.6), "zoom": (1.0, 1.45), "fx": "strike"}),
    (37.40, 39.89, "distance", {"img": "viper5"}),
    (39.89, RKO_HIT, "me", {}),
    (RKO_HIT, RKO_HIT + RKO_LEN, "rko", {}),
    (RKO_HIT + RKO_LEN, 45.77, "me", {}),
    (45.77, 51.20, "me", {"end": True}),
    (51.20, DURATION, "brand", {}),
]

MAP_COUNTER = 14.25  # the counter starts after the short pause

# Pauses in the voice, used for small jump-cut zoom changes while you're on screen
PHRASE_BREAKS = [6.15, 8.3, 16.40, 17.7, 27.10, 32.40, 33.5, 39.89, 43.44, 44.77, 45.77, 47.61, 49.68]


def segment_at(t):
    for s in SEGMENTS:
        if s[0] <= t < s[1]:
            return s
    return SEGMENTS[-1]


CUTS = [s[0] for s in SEGMENTS[1:]]
