#!/usr/bin/env python3
"""
Generative Pipeline - orchestrates script generation -> voice -> decor -> render,
for channels with "generation_mode": true in their profile.

Three user-facing phases, each a deliberate checkpoint (nothing auto-advances
past one without the user asking for it, since the later ones cost money or
are hard to undo):

    1. Scripts   — write `count` scripts at once (free). The user reviews and
                   edits them.
    2. Audio     — once scripts are approved, synthesize narration for all of
                   them at once (ElevenLabs, costs credits).
    3. Decor     — per video, THEN: the user picks a background video + music
                   + frame style for that specific draft and renders it. Decor
                   is deliberately the LAST thing chosen, per-video, not
                   upfront and shared — script/audio don't use it at all, so
                   there's no reason to force that choice before the content
                   exists to pair it against.

Registers generated videos as ordinary rows in the SAME `videos` table the
curation pipeline uses (via url_manager.URLManager), so everything downstream
(scheduling, upload, webapp dashboard) works unchanged once a row reaches
status='ready_for_upload' — at that point it's reviewed for title/description/
tags in the SAME "Résultats IA" wizard step as a curated video, reusing the
ai_data the script already wrote (no second AI pass over the finished video).

Statuses:

    awaiting_script -> script_generated -> audio_generated -> ready_for_upload
                                                             -> rendering_failed (on error)
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

    def create_draft(self, channel_name: str, count: int = 1, inspired_by: str = None) -> str:
        """Phase 1 kickoff: registers `count` new video rows sharing one
        batch_id — no script, no decor, nothing generated yet. Meant to be
        followed immediately by run_batch_scripts().

        inspired_by ("Refaire ce style" from a top performer): every draft
        remembers that video — its scripts get written in the same format
        and structure (on new topics), and its décor is pre-filled in phase 3
        with the winner's choices (decor_preset), still changeable."""
        extra = {}
        if inspired_by:
            winner = _db.get_video(inspired_by)
            if not winner or winner.get("source") != "generated" or winner.get("channel") != channel_name:
                raise ValueError("Vidéo modèle introuvable sur cette chaîne")
            extra = {"inspired_by": inspired_by, "decor_preset": self._decor_preset(winner)}
        videos = [
            {
                "line_number": i + 1,
                "channel": channel_name,
                "status": "awaiting_script",
                "source": "generated",
                **extra,
            }
            for i in range(count)
        ]
        return self.url_manager.add_batch(f"{channel_name}_generated", videos)

    def _decor_preset(self, winner: Dict) -> Dict:
        """The winner's décor as asset FILENAMES (what the Décor step picks
        from) — only those still present in the channel's assets folders."""
        assets = self.list_assets(winner["channel"])
        name = lambda p: os.path.basename(p) if p else None
        bg, music = name(winner.get("bg_video_path")), name(winner.get("bg_music_path"))
        return {
            "bg_video_filename": bg if bg in assets["backgrounds"] else None,
            "bg_music_filename": music if music in assets["music"] else None,
            "frame_mode": winner.get("frame_mode") or "fill",
            "rounded_corners": bool(winner.get("rounded_corners")),
            "caption_style": winner.get("caption_style") or "karaoke",
            "caption_color": winner.get("caption_color"),
        }

    RECENT_HISTORY_LIMIT = 15

    def _recent_script_history(self, channel_name: str, exclude_video_id: str):
        """This channel's most recent generated titles + formats (newest
        first, current video excluded) — passed to generate_script() so it
        has something concrete to avoid repeating, including siblings
        already scripted earlier in the same batch (sequential, so they're
        already in the DB by the time a later video's turn comes)."""
        videos = [
            v for v in self.url_manager.list_videos(channel=channel_name)
            if v.get("source") == "generated" and v.get("video_id") != exclude_video_id and v.get("title")
        ]
        videos.sort(key=lambda v: v.get("updated_at") or "", reverse=True)
        recent = videos[: self.RECENT_HISTORY_LIMIT]
        titles = [v["title"] for v in recent]
        formats = [v["script_format"] for v in recent if v.get("script_format")]
        return titles, formats

    def generate_script_for(self, video_id: str) -> Dict:
        """Writes ONE script (+ title/description/tags) for an existing
        draft. Also used to regenerate a script the user doesn't like, at any
        point before audio has been generated for it."""
        video = _db.get_video(video_id)
        if not video:
            raise ValueError(f"Unknown video_id: {video_id}")

        profile = self.channel_manager.get_channel_profile(video["channel"])
        recent_titles, recent_formats = self._recent_script_history(video["channel"], exclude_video_id=video_id)
        inspiration = None
        if video.get("inspired_by"):
            winner = _db.get_video(video["inspired_by"])
            if winner and winner.get("script_text"):
                inspiration = {"format": winner.get("script_format"), "title": winner.get("title"),
                               "script_text": winner.get("script_text")}
        script = generate_script(profile, recent_titles=recent_titles, recent_formats=recent_formats,
                                 inspiration=inspiration)

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

    def run_batch_scripts(self, batch_id: str):
        """Phase 1: writes a script for every draft in this batch that's
        still awaiting one. Background-thread entry point — stops there, and
        does NOT go on to audio: that's a separate, explicit phase 2, so the
        user gets to review/edit scripts before ElevenLabs is ever called."""
        for video in self.url_manager.list_videos(batch_id=batch_id):
            if video["status"] != "awaiting_script":
                continue
            try:
                self.generate_script_for(video["video_id"])
            except Exception as e:
                self.url_manager.update_video_status(video["video_id"], "rendering_failed", render_error=str(e))

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
        independently, without re-synthesizing. Also used to re-synthesize a
        take the user doesn't like, at any point before assembly."""
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

    def run_batch_audio(self, batch_id: str):
        """Phase 2: synthesizes narration for every draft in this batch whose
        (reviewed) script is ready but has no audio yet. Background-thread
        entry point, triggered explicitly by the user once they're happy with
        the scripts — never automatic."""
        for video in self.url_manager.list_videos(batch_id=batch_id):
            if video["status"] != "script_generated":
                continue
            try:
                self.generate_audio_for(video["video_id"])
            except Exception:
                pass  # generate_audio_for already recorded rendering_failed

    def set_decor(
        self, video_id: str, bg_video_path: str, bg_music_path: str,
        frame_mode: str = "fill", rounded_corners: bool = False, caption_style: str = "karaoke",
        caption_color: str = None,
    ) -> Dict:
        """Phase 3: assigns (or reassigns) the background video/music/cadrage/
        caption style (+ its accent color, for styles that support one) on an
        existing draft — deferred until after script+audio, so each draft can
        get its own decor instead of one shared choice upfront."""
        video = _db.get_video(video_id)
        if not video:
            raise ValueError(f"Unknown video_id: {video_id}")
        self.url_manager.update_video_status(
            video_id, video["status"],
            bg_video_path=bg_video_path, bg_music_path=bg_music_path,
            frame_mode=frame_mode, rounded_corners=rounded_corners,
            caption_style=caption_style, caption_color=caption_color,
        )
        return _db.get_video(video_id)

    def assemble(self, video_id: str, progress_cb=None) -> str:
        """Composite the final video from the already-generated narration —
        local/free, no ElevenLabs call. The only method that writes the
        final mp4. Requires decor (set_decor) to have been chosen already."""
        video = _db.get_video(video_id)
        if not video:
            raise ValueError(f"Unknown video_id: {video_id}")
        if not video.get("words_path"):
            raise ValueError(f"Video {video_id} has no generated audio yet.")
        if not video.get("bg_video_path") or not video.get("bg_music_path"):
            raise ValueError(f"Video {video_id} has no décor chosen yet.")

        out_path = os.path.join(PROCESSED_DIR, f"{video_id}.mp4")
        try:
            with open(video["words_path"], encoding="utf-8") as f:
                words = [tuple(w) for w in json.load(f)]
            render_video(
                video["narration_path"], words, video["bg_video_path"], video["bg_music_path"], out_path,
                frame_mode=video.get("frame_mode", "fill"),
                rounded_corners=video.get("rounded_corners", False),
                caption_style=video.get("caption_style", "karaoke"),
                caption_color=video.get("caption_color"),
                border_image_path=self.channel_manager.get_background_path(video["channel"]),
                progress_cb=progress_cb,
            )
        except Exception as e:
            self.url_manager.update_video_status(video_id, "rendering_failed", render_error=str(e))
            raise

        # Clear any error left over from a previous failed attempt on this
        # same video_id — otherwise it stays displayed forever even after a
        # later attempt succeeds.
        self.url_manager.update_video_status(video_id, "ready_for_upload", video_path=out_path, render_error=None)
        return out_path

    def advance_draft(self, video_id: str) -> Dict:
        """Retries exactly the step that failed on this draft (script, audio,
        or assemble) — a single step, never cascading into the next phase on
        its own, since audio and decor/assemble are gated behind explicit
        user actions (review scripts, then choose decor). No-op if the draft
        isn't currently in rendering_failed."""
        video = _db.get_video(video_id)
        if not video:
            raise ValueError(f"Unknown video_id: {video_id}")
        if video["status"] != "rendering_failed":
            return video

        if video.get("words_path"):
            failed_stage = "assemble"
        elif video.get("script_text"):
            failed_stage = "audio"
        else:
            failed_stage = "script"

        try:
            if failed_stage == "script":
                self.generate_script_for(video_id)
            elif failed_stage == "audio":
                self.generate_audio_for(video_id)
            else:
                self.assemble(video_id)
        except Exception as e:
            if failed_stage == "script":
                # generate_audio_for/assemble already record rendering_failed
                # themselves on failure — only the script step doesn't.
                self.url_manager.update_video_status(video_id, "rendering_failed", render_error=str(e))

        return _db.get_video(video_id)
