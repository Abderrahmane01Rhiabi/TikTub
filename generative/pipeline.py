#!/usr/bin/env python3
"""
Generative Pipeline - orchestrates (user picks assets) -> script generation ->
voice + render, for channels with "generation_mode": true in their profile.

The user chooses the "set" (background video + music + frame style) FIRST,
before anything is written or generated — nothing is imposed on them. Only
then is a single script generated for that specific draft.

Registers generated videos as ordinary rows in the SAME `videos` table the
curation pipeline uses (via url_manager.URLManager), so everything downstream
(scheduling, upload, webapp dashboard) works unchanged once a row reaches
status='ready_for_upload' — at that point it's reviewed for title/description/
tags in the SAME "Résultats IA" wizard step as a curated video, reusing the
ai_data the script already wrote (no second AI pass over the finished video).

Statuses introduced here:

    awaiting_script -> script_generated -> audio_generated -> ready_for_upload
                                                             -> rendering_failed (on error)

Audio generation (ElevenLabs, costs credits) and assembly (local, free) are
two separate steps rather than one combined "render" — the user can listen to
the generated voice before spending time on the composite, and re-assemble
without re-paying for audio if only the visual side needs a redo.
"""

import json
import os
from typing import Dict, List

import db as _db
from channel_manager import ChannelManager
from url_manager import URLManager
from generative.script_generator import generate_script
from generative.voice_generator import synthesize
from generative.video_composer import render_video

PROCESSED_DIR = "processed_videos"
TEMP_DIR = "temp"


class GenerativePipeline:
    def __init__(self):
        self.channel_manager = ChannelManager()
        self.url_manager = URLManager()

    def create_draft(
        self, channel_name: str, bg_video_path: str, bg_music_path: str,
        frame_mode: str = "fill", rounded_corners: bool = False,
    ) -> str:
        """Step 1: register the user's chosen background video + music + frame
        style as a new video row — no script yet, nothing generated yet."""
        video = {
            "line_number": 1,
            "channel": channel_name,
            "status": "awaiting_script",
            "source": "generated",
            "bg_video_path": bg_video_path,
            "bg_music_path": bg_music_path,
            "frame_mode": frame_mode,
            "rounded_corners": rounded_corners,
        }
        return self.url_manager.add_batch(f"{channel_name}_generated", [video])

    def generate_script_for(self, video_id: str) -> Dict:
        """Step 2: write ONE script (+ title/description/tags) for an existing
        draft. The only place script_generator.generate_script gets called."""
        video = _db.get_video(video_id)
        if not video:
            raise ValueError(f"Unknown video_id: {video_id}")

        profile = self.channel_manager.get_channel_profile(video["channel"])
        script = generate_script(profile)

        self.url_manager.update_video_status(
            video_id, "script_generated",
            # Top-level 'title' (not just nested in ai_data) so
            # youtube_scheduler.create_upload_schedule's
            # video.get('custom_title') or video.get('title') fallback shows
            # the real title instead of "Video N" in Planning.
            title=script["title"],
            script_text=script["script_text"],
            script_format=script.get("format", ""),
            ai_data={
                "optimized_title": script["title"],
                "title": script["title"],
                "description_suggestions": [script.get("description", "")],
                "description": script.get("description", ""),
                "tags": script.get("tags", []),
                "hashtags": [f"#{t}" for t in script.get("tags", [])[:3]],
                "content_type": "manifestation",
            },
        )
        return _db.get_video(video_id)

    def update_script(self, video_id: str, script_text: str):
        """Let the user edit the script text before rendering."""
        self.url_manager.update_video_status(video_id, "script_generated", script_text=script_text)

    def list_assets(self, channel_name: str) -> Dict[str, List[str]]:
        dirs = self.channel_manager.get_assets_dirs(channel_name)
        video_exts = {".mp4", ".mov", ".m4v"}
        audio_exts = {".mp3", ".wav", ".m4a"}
        return {
            "backgrounds": sorted(
                f for f in os.listdir(dirs["backgrounds"])
                if os.path.splitext(f)[1].lower() in video_exts
            ),
            "music": sorted(
                f for f in os.listdir(dirs["music"])
                if os.path.splitext(f)[1].lower() in audio_exts
            ),
        }

    def generate_audio_for(self, video_id: str) -> str:
        """Synthesize narration (ElevenLabs — costs credits) and measure its
        real word timing (Whisper). Saved to disk so assemble() can run later,
        independently, without re-synthesizing."""
        video = _db.get_video(video_id)
        if not video:
            raise ValueError(f"Unknown video_id: {video_id}")
        if not video.get("script_text"):
            raise ValueError(f"Video {video_id} has no script yet.")

        profile = self.channel_manager.get_channel_profile(video["channel"])
        narration_path = os.path.join(TEMP_DIR, video_id, "narration.mp3")
        words_path = os.path.join(TEMP_DIR, video_id, "words.json")

        try:
            words = synthesize(
                video["script_text"],
                voice_id=profile.get("tts_voice_id"),
                out_mp3_path=narration_path,
                model_id=profile.get("tts_model_id", "eleven_v3"),
            )
            with open(words_path, "w", encoding="utf-8") as f:
                json.dump(words, f)
        except Exception as e:
            self.url_manager.update_video_status(video_id, "rendering_failed", render_error=str(e))
            raise

        self.url_manager.update_video_status(
            video_id, "audio_generated",
            narration_path=narration_path, words_path=words_path, render_error=None,
        )
        return narration_path

    def assemble(self, video_id: str) -> str:
        """Composite the final video from the already-generated narration —
        local/free, no ElevenLabs call. The only method that writes the
        final mp4."""
        video = _db.get_video(video_id)
        if not video:
            raise ValueError(f"Unknown video_id: {video_id}")
        if not video.get("words_path"):
            raise ValueError(f"Video {video_id} has no generated audio yet.")

        out_path = os.path.join(PROCESSED_DIR, f"{video_id}.mp4")
        try:
            with open(video["words_path"], encoding="utf-8") as f:
                words = [tuple(w) for w in json.load(f)]
            render_video(
                video["narration_path"], words, video["bg_video_path"], video["bg_music_path"], out_path,
                frame_mode=video.get("frame_mode", "fill"),
                rounded_corners=video.get("rounded_corners", False),
                border_image_path=self.channel_manager.get_background_path(video["channel"]),
            )
        except Exception as e:
            self.url_manager.update_video_status(video_id, "rendering_failed", render_error=str(e))
            raise

        # Clear any error left over from a previous failed attempt on this
        # same video_id — otherwise it stays displayed forever even after a
        # later attempt succeeds.
        self.url_manager.update_video_status(video_id, "ready_for_upload", video_path=out_path, render_error=None)
        return out_path
