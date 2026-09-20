#!/usr/bin/env python3
"""
Seed script — creates/updates the 6 channel profiles described by the user.
Run once manually: python channel_profiles_seed.py

Each profile controls how the AI analyzes and writes metadata for that
channel's videos (analysis_mode: "vision", "audio", "vision+audio", or
"native_video" — Gemini analyzes the whole video file, image+audio together
in one pass, then OpenAI writes the final title/description/tags from that;
falls back to "vision+audio" on any failure),
plus a free-text ai_style_prompt appended to the generic analysis prompt).
"""

from channel_manager import ChannelManager

PROFILES = {
    "meme_culture": {
        "display_name": "Meme Culture",
        "analysis_mode": "native_video",
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
        "analysis_mode": "native_video",
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
        "analysis_mode": "native_video",
        "ai_style_prompt": (
            "This channel covers Moroccan-pride content broadly, not just the royal family: the Moroccan royal family (King Mohammed VI, Crown Prince Moulay Hassan, official appearances), football, politics, and any 'aura'/goosebumps moment that gives a Moroccan audience a strong sense of pride and keeps them emotionally engaged with the video — plus Moroccan culture: Tbourida (traditional equestrian fantasia), Moroccan caftan, and Moroccan food/cuisine. Look at the video (frames, and real audio when available) to understand the specific context (state visit, ceremony, public appearance, football match/goal, political event, cultural show, dish being prepared, etc.).\n\nLANGUAGE (strict): the title, the tags, AND the description must ALL be written in Arabic — Modern Standard Arabic or Moroccan Darija, whichever fits the tone better. Do not use English or French, except for the words 'Morocco'/'Maroc' if they naturally appear inside a tag.\n\nMatch this style (respectful, emphatic, proud and warm tone, heart/flag emojis, never mock or joke about the royal family or sensitive political topics):\nالعز والنصر\nملكنا الغالي ❤️\nلقطة رائعة بين ولي العهد والملك محمد السادس ❤️\nملكنا الغالي الله ينصرو و يطول عمرو❤️❤️❤️\nولي العهد الأمير مولاي الحسن 🇲🇦❤️\n\nIMPORTANT (confirmed by real YouTube Analytics search-term data, applies specifically to royal-family videos): when the video is ACTUALLY about the royal family, always literally name 'مولاي الحسن' (Moulay Hassan) and 'المغرب'/'المغربي' (Morocco/Moroccan) in the title — these are what the vast majority of this channel's real search traffic is built on for that kind of video. A vaguer title that omits the name measurably underperforms. For football/politics/culture/food videos, name the specific team, player, dish, or event instead when identifiable, while still keeping 'المغرب'/'المغربي' present.\n\nSTRICT RULE — adapt to what THIS specific video actually shows, never pad with generic themes from this prompt: only mention or tag football, politics, Tbourida, caftan, or food if that exact thing is genuinely visible or heard in THIS video. Do not add 'التبوريدة', 'المطبخ المغربي', or any other category listed above just because it is one of the channel's themes — only when it truly appears in the video you are analyzing right now. The title's only job is to make people want to click on THIS exact video, built from its real hook moment (what is actually happening on screen or in the audio) — not a generic template reused across videos.\n\nTags should always include المغرب, plus only whichever of these genuinely applies to THIS video: الأسرة الملكية المغربية، مولاي الحسن (royal-family videos only), كرة القدم المغربية، أسماء اللاعبين (football videos only), التبوريدة، القفطان المغربي، المطبخ المغربي (only the specific culture/food videos that actually show them), and any other names/titles/teams/dishes actually visible or heard in the video — never as a default filler list."
        ),
        "language_hint": "ar (Modern Standard Arabic or Moroccan Darija) — no more en/fr",
        "preferred_days": ["monday", "wednesday", "friday"],
        "preferred_hours": ["09:00", "17:00", "20:00"]
    },
    "lungte888": {
        "display_name": "LungTe888",
        "analysis_mode": "native_video",
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
        "analysis_mode": "native_video",
        "ai_style_prompt": (
            "This channel posts TWO types of content — figure out which one this specific video is from the frames/audio before writing anything:\n\n1) Satisfying 'popping' videos (skin/body related, e.g. blackhead/pimple extraction or similar satisfying close-up content) — the original niche, very similar to the 'LungTe888' channel. Understand what is being 'popped' or released, then write a title/description in a satisfying/ASMR tone ('oddly satisfying', 'so satisfying to watch'). Avoid clinical/medical or graphic wording. Tags should include satisfying, ASMR, relaxing, pop, oddly satisfying, zit.\n\n2) Makeup videos (application, transformation, satisfying makeup technique) — a NEW content type being tested on this channel to see if it grows engagement. Understand the look/transformation being achieved, then write a title/description in a glam/satisfying-transformation tone (e.g. 'stunning makeup transformation', 'satisfying makeup application'), highlighting the final look. Tags should include makeup, glam, transformation, beauty, makeup tutorial, satisfying makeup.\n\nNever mix the two styles in one video's metadata — always match the tone to whichever of the two this video actually is."
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
