"""
Adaptation — rebuild a viral "explainer" Short (a voice-over over a
compilation of clips) in other languages, for other channels.

    reference.py  Gemini reads the viral Short: structure, script, banners,
                  credits — the blueprint, never re-used as footage
    sources.py    downloads the ORIGINAL source videos, cuts them into clips,
                  finds each crash/peak, the clean picture area, watermarks
    script.py     Gemini writes our own script per language, clip by clip
                  (always reviewed by a person before any voice is made)
    voices.py     ElevenLabs: the voice library (names, accents, previews)
                  and the narration with word timings
    render.py     one ffmpeg pass: clips in a rounded box, a banner per clip,
                  big captions with a coloured keyword, music + crash sounds
    checks.py     what is measured before a person sees a video: sound as
                  long as the picture, every sentence in place, loudness
    langs.py      per-language look (fonts, right-to-left, capitals)
    pipeline.py   the project: steps, statuses, and the hand-off to Publication
"""
