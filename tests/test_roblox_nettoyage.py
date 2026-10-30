"""Montage Roblox, the cleaning (roblox/nettoyage.py, labs etude_roblox/style/nettoyage_gpu_v*): what the creator added
is hidden in its own shape before any montage — names read on screen, a webcam, the bottom band of his captions.
SAM 2 (the avatars' shapes) needs the graphics card: it is not run here; the rest really is."""

import subprocess

import numpy as np
import pytest

from roblox import nettoyage


def test_a_players_name_is_told_from_the_games_own_texts():
    nettoyage.KNOWN.clear()
    nettoyage.KNOWN.update({"rockiemanero"})
    names = ["bigman_melon", "K744P639", "CKIEMANERO", "Sunny_99"]
    game = ["TELEPORT TO END", "EVERYONE TO END", "CELLS", "SLAP EVERYONE", "10", "Buy Item"]
    assert all(nettoyage.looks_like_name(t) for t in names) and not any(nettoyage.looks_like_name(t) for t in game)


def test_known_names_come_from_the_descriptions_gemini_wrote():
    els = [{"type": "pseudo", "description": "Pseudo bigman_melon au-dessus du personnage"},
           {"type": "pseudo", "description": "Pseudo K744P639 sous TOP PLAYER"},
           {"type": "avatar", "description": "Pastèque rouge Melon"}]
    assert nettoyage.known_names(els) == {"bigman_melon", "k744p639"}


def test_a_shape_is_kept_whole_and_hidden_a_little_before_and_after():
    m = np.zeros((40, 40), bool)
    m[5:30, 5:30] = True
    m[12:18, 12:18] = False                                                    # sunglasses: a hole in the face
    assert nettoyage.whole(m)[15, 15]
    out = nettoyage.in_time({10: m})
    assert set(out) == set(range(10 - nettoyage.TWIN, 10 + nettoyage.TWIN + 1))


@pytest.fixture
def passage(tmp_path):
    path = str(tmp_path / "w0.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=1920x1080:rate=30:duration=4", "-f", "lavfi",
                    "-i", "sine=frequency=440:duration=4", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", path],
                   check=True)
    return path


def frame(path, t, tmp_path, name):
    out = str(tmp_path / f"{name}.png")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i", path, "-frames:v", "1", out], check=True)
    from PIL import Image
    return np.asarray(Image.open(out).convert("L")).astype(float)


def test_a_webcam_and_a_name_are_hidden_the_captions_band_cut_and_the_sound_kept(passage, tmp_path):
    class Reader:                                                              # a name read at (1500, 100)
        def readtext(self, jpg):
            return [([[1500, 80], [1700, 80], [1700, 130], [1500, 130]], "bigman_melon", 0.9),
                    ([[100, 900], [400, 900], [400, 950], [100, 950]], "TELEPORT TO END", 0.9)]
    els = [{"type": "webcam", "debut": 0.0, "fin": 4.0, "cadre": [0.0, 0.0, 0.25, 0.3]},
           {"type": "sous_titres_incrustes", "debut": 1.0, "fin": 2.0, "cadre": [0.3, 0.85, 0.7, 0.97]}]
    r = nettoyage.clean(passage, els, [[0.0, 4.0]], str(tmp_path / "propre.mp4"), str(tmp_path / "travail"), reader=Reader())
    assert r["keep"] == nettoyage.KEEP and r["pseudos"] == ["bigman_melon"]
    streams = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,height", "-of", "json", r["fichier"]],
                             capture_output=True, text=True).stdout
    import json
    kinds = {s["codec_type"]: s.get("height") for s in json.loads(streams)["streams"]}
    assert "audio" in kinds and kinds["video"] == int(1080 * nettoyage.KEEP) // 2 * 2         # the captions' band cut
    before, after = frame(passage, 2.0, tmp_path, "a"), frame(r["fichier"], 2.0, tmp_path, "b")
    changed = lambda y0, y1, x0, x1: np.abs(after[y0:y1, x0:x1] - before[y0:y1, x0:x1]).mean()
    assert changed(30, 280, 30, 440) > 10                                    # the webcam: hidden
    assert changed(85, 125, 1510, 1690) > 10                                 # the name: hidden
    assert changed(600, 800, 900, 1400) < 3                                  # the game: untouched


def test_nothing_found_leaves_the_passage_as_it_is(passage, tmp_path):
    class Reader:
        def readtext(self, jpg):
            return []
    r = nettoyage.clean(passage, [], [[0.0, 4.0]], str(tmp_path / "propre.mp4"), str(tmp_path / "travail"), reader=Reader())
    assert r["fichier"] == passage and r["keep"] == 1.0


def test_the_models_are_loaded_once(monkeypatch):
    made = []
    monkeypatch.setattr(nettoyage, "_MODELS", {})
    monkeypatch.setattr(nettoyage, "_load_sam", lambda: made.append("sam") or object())
    monkeypatch.setattr(nettoyage, "_load_ocr", lambda: made.append("ocr") or object())
    assert nettoyage.sam() is nettoyage.sam() and nettoyage.ocr() is nettoyage.ocr() and made == ["sam", "ocr"]
