"""
Montage auto — turns a raw imported clip into the "hopecore" Short recipe:
original audio kept, the IMAGE replaced by a black screen then two drone
shots before the punchline, cascade captions, a hook on top, and a music
bed that cuts on the black screen and comes back on the song's chosen
moment.

    transcribe.py  Whisper word timings
    planner.py     Gemini decides the edit (kept ranges, black screen,
                   drones, punchline, 3 hooks) + caption keywords
    recipes.py     the recipe and the per-channel / per-video settings
    broll.py       the shared drone-shot library (Pixabay) and its reuse memory
    render.py      one ffmpeg pass that builds the final (or preview) video

Gemini only decides WHAT happens WHEN; every duration, volume and position
is a fixed rule here, and the plan is re-checked before rendering, so a
sloppy plan degrades to "fewer effects", never to a broken video.
"""
