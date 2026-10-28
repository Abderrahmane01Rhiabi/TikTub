#!/usr/bin/env python3
"""
Audio Transcriber - Speech-to-text for channels whose AI profile needs the
spoken audio (e.g. LungTeMotivates), via the OpenAI Whisper API.
"""

import os
import tempfile
from typing import Optional

import requests

try:
    from moviepy.editor import VideoFileClip
    MOVIEPY_AVAILABLE = True
except ImportError:
    MOVIEPY_AVAILABLE = False


# what faster-whisper writes when nobody speaks (measured on a music-only video, RESULTATS_MODELES.md):
# whisper-1 answers nothing there, so the local model's "Music" is read as no speech too
NO_SPEECH = {"music", "musique", "musik", "applause", "silence", "♪"}
_models = {}


def _local_model(size: str):
    """faster-whisper on this PC, loaded once per size ("small", "medium")."""
    if size not in _models:
        from faster_whisper import WhisperModel
        _models[size] = WhisperModel(size, device="cpu", compute_type="int8")
    return _models[size]


def _speech(text: str) -> Optional[str]:
    words = [w for w in text.lower().replace("♪", " ♪ ").split() if w.strip(".,!?()[]")]
    if not words or all(w.strip(".,!?()[]") in NO_SPEECH for w in words):
        return None
    return text.strip()


class AudioTranscriber:
    """Extracts a video's audio track and transcribes it via OpenAI Whisper."""

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv('OPENAI_API_KEY')
        self.transcription_url = "https://api.openai.com/v1/audio/transcriptions"

    def extract_audio(self, video_path: str) -> Optional[str]:
        """Extract the audio track to a temporary mp3 file. Returns its path, or None."""
        if not MOVIEPY_AVAILABLE:
            print("⚠️ moviepy not available, cannot extract audio")
            return None

        try:
            clip = VideoFileClip(video_path)
            if clip.audio is None:
                clip.close()
                return None

            tmp = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False)
            tmp.close()
            clip.audio.write_audiofile(tmp.name, logger=None)
            clip.close()
            return tmp.name
        except Exception as e:
            print(f"⚠️ Audio extraction error: {e}")
            return None

    def transcribe(self, video_path: str) -> Optional[str]:
        """Extract + transcribe the audio of video_path. Returns the transcript, or None.
        The model is chosen in Réglages → Modèles d'IA: whisper-1 (OpenAI), or faster-whisper on this PC."""
        import ai_models
        choice = ai_models.transcription_model()
        if choice.startswith("faster-whisper-"):
            return self._transcribe_local(video_path, choice.split("-")[-1])
        if not self.api_key:
            print("⚠️ No OPENAI_API_KEY set, cannot transcribe audio")
            return None

        audio_path = self.extract_audio(video_path)
        if not audio_path:
            return None

        try:
            with open(audio_path, 'rb') as audio_file:
                response = requests.post(
                    self.transcription_url,
                    headers={'Authorization': f'Bearer {self.api_key}'},
                    files={'file': (os.path.basename(audio_path), audio_file, 'audio/mpeg')},
                    data={'model': 'whisper-1'},
                    timeout=60
                )

            if response.status_code == 200:
                text = response.json().get('text', '').strip()
                return text or None

            print(f"❌ Whisper API error: {response.status_code} - {response.text}")
            return None
        except Exception as e:
            print(f"❌ Whisper transcription failed: {e}")
            return None
        finally:
            try:
                os.unlink(audio_path)
            except OSError:
                pass

    def _transcribe_local(self, video_path: str, size: str) -> Optional[str]:
        audio_path = self.extract_audio(video_path)
        if not audio_path:
            return None
        try:
            segments, _info = _local_model(size).transcribe(audio_path)
            return _speech(" ".join(seg.text.strip() for seg in segments))
        except Exception as e:
            print(f"❌ Local transcription failed: {e}")
            return None
        finally:
            try:
                os.unlink(audio_path)
            except OSError:
                pass
