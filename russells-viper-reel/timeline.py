"""Timing for the Russell's Viper reel. Every time is in seconds of the original clip.

Section boundaries are snapped to the natural pauses in the voice track
(found with ffmpeg silencedetect), so cuts land between sentences.
"""

DURATION = 52.29

# Section start times (from the edit brief, snapped to pauses in the speech)
S1_HOOK = 0.0        # Malai Paambu ah? confusion
S2_NAME = 6.15       # Kannadi Viriyan = Russell's Viper
S3_STATS = 10.50     # India map + ranking + deaths counter
S3_COUNTER = 14.25   # counter starts after the short pause
S4_CHART = 19.00     # 43% chart
S5_COMPARE = 27.10   # looks similar, deadly mistake
S6_DISTANCE = 32.40  # 10 feet / striking speed
S6_SPEED = 36.00
S7_RKO = 39.89       # comedy section
S8_END = 45.77       # comment / follow end screen

# The exact moment you say "RKO". Change this one number if the hit is early/late.
RKO_HIT = 41.90
RKO_FREEZE = 1.0     # seconds the frame stays frozen (your audio keeps playing)

# Pauses in the voice track: used for the "jump-cut" zoom rhythm (a visual change every 1-2 s)
PHRASE_BREAKS = [
    2.0, 4.0, 6.15, 8.3, 10.50, 12.4, 14.25, 16.4, 19.00, 21.0, 23.0, 25.0, 27.10,
    29.4, 32.40, 34.46, 35.67, 36.95, 38.03, 39.89, 43.44, 44.77, 45.77, 47.61,
    49.68, 50.80,
]

SECTION_STARTS = [S2_NAME, S3_STATS, S4_CHART, S5_COMPARE, S6_DISTANCE, S7_RKO, S8_END]
