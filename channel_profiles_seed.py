#!/usr/bin/env python3
"""
Seed script — creates/updates the 6 channel profiles described by the user.
Run once manually: python channel_profiles_seed.py

Each profile controls how the AI analyzes and writes metadata for that
channel's videos (analysis_mode: "vision", "audio", or "vision+audio",
plus a free-text ai_style_prompt appended to the generic analysis prompt).
"""

from channel_manager import ChannelManager

PROFILES = {
    "meme_culture": {
        "display_name": "Meme Culture",
        "analysis_mode": "vision",
        "ai_style_prompt": (
            "This channel posts funny, meme-style short videos. Look at the video frames "
            "to understand the joke/situation, then write a title and description that are "
            "funny, punchy, and attention-grabbing — internet humor tone, short sentences, "
            "relevant emojis. Tags should target meme/comedy/viral audiences."
        ),
        "language_hint": "en",
        "preferred_days": [],
        "preferred_hours": []
    },
    "animeshorts": {
        "display_name": "AnimeShorts",
        "analysis_mode": "vision",
        "ai_style_prompt": (
            "This channel posts anime clips. Look at the video frames to identify the "
            "specific anime series and character(s) if recognizable (e.g. Naruto, One Piece, "
            "Attack on Titan, Dragon Ball). Write titles that name the series/character when "
            "identifiable, targeted at anime fans, with a 'POV' or hype tone. Tags should "
            "include the series name, character name, and general anime/manga terms."
        ),
        "language_hint": "en",
        "preferred_days": [],
        "preferred_hours": []
    },
    "prince_moulay_hassan": {
        "display_name": "Prince Moulay Hassan",
        "analysis_mode": "vision",
        "ai_style_prompt": (
            "This channel is dedicated to the Moroccan royal family (King Mohammed VI, "
            "Crown Prince Moulay Hassan, and related official appearances). Look at the "
            "video frames to understand the context (state visit, ceremony, public "
            "appearance, etc.) and write a respectful, emphatic title in Arabic, English, "
            "or French — mixing scripts is fine, matching this style:\n"
            "العز والنصر\n"
            "Moroccan Prince : Prince Hassan 3 ❤️\n"
            "Moroccan King & Sheikh Mohammed bin Zayed\n"
            "Moroccan Prince ❤️\n"
            "Moroccan and Saudi Princes\n"
            "Moroccan Prince ❤️❤️❤️\n"
            "ملكنا الغالي ❤️\n"
            "لقطة رائعة بين ولي العهد والملك محمد السادس ❤️\n"
            "ملكنا الغالي الله ينصرو و يطول عمرو❤️❤️❤️\n"
            "Use heart/flag emojis, a proud and warm tone. Never mock or joke about the "
            "royal family. Tags should include Morocco, Moroccan royal family, and the "
            "names/titles visible in the video."
        ),
        "language_hint": "ar/en/fr mix",
        "preferred_days": ["monday", "wednesday", "friday"],
        "preferred_hours": ["09:00", "17:00", "20:00"]
    },
    "lungte888": {
        "display_name": "LungTe888",
        "analysis_mode": "vision",
        "ai_style_prompt": (
            "This channel posts satisfying 'popping' videos (skin/body related, e.g. "
            "blackhead/pimple extraction or similar satisfying close-up content). Look at "
            "the video frames to understand what is being 'popped' or released, then write "
            "a title/description in a satisfying/ASMR tone ('oddly satisfying', 'so "
            "satisfying to watch', etc.). Avoid clinical/medical or graphic wording — keep "
            "it light and satisfying-content style. Tags should include satisfying, ASMR, "
            "relaxing, pop, oddly satisfying."
        ),
        "language_hint": "en",
        "preferred_days": [],
        "preferred_hours": []
    },
    "zit_bliss": {
        "display_name": "Zit Bliss",
        "analysis_mode": "vision",
        "ai_style_prompt": (
            "This channel posts satisfying 'popping' videos (skin/body related, e.g. "
            "blackhead/pimple extraction or similar satisfying close-up content) — very "
            "similar niche to the 'LungTe888' channel. Look at the video frames to "
            "understand what is being 'popped' or released, then write a title/description "
            "in a satisfying/ASMR tone. Avoid clinical/medical or graphic wording. Tags "
            "should include satisfying, ASMR, relaxing, pop, oddly satisfying, zit."
        ),
        "language_hint": "en",
        "preferred_days": [],
        "preferred_hours": []
    },
    "lungtemotivates": {
        "display_name": "LungTeMotivates",
        "analysis_mode": "audio",
        "ai_style_prompt": (
            "This channel posts motivational content. Most of the meaning is in the spoken "
            "audio (a voiceover or speech) rather than the visuals, so prioritize the audio "
            "transcript when available; use the on-screen text or video frames only as a "
            "fallback if no speech is detected. Write a title and description that capture "
            "the motivational message/quote, in an inspiring, growth-mindset tone. Tags "
            "should include motivation, mindset, self improvement, inspiration, discipline."
        ),
        "language_hint": "en",
        "preferred_days": [],
        "preferred_hours": []
    },
}


def main():
    manager = ChannelManager()
    existing = manager.get_config()

    for channel_name, profile in PROFILES.items():
        if channel_name not in existing:
            manager.add_channel(
                channel_name,
                profile["display_name"],
                description=f"Auto-created by channel_profiles_seed.py"
            )
        manager.save_channel_profile(channel_name, profile)
        print(f"✅ Profile written for '{profile['display_name']}' ({channel_name})")

    print("\nDone. Place OAuth credentials.json in each channels/<name>/ folder when ready.")


if __name__ == "__main__":
    main()
