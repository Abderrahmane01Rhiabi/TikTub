"""Montage Roblox, the channel's identity (labs etude_roblox/style, flou): what the creator added is found, our mascot
takes the place of his avatars at the right moments, the texts take the channel's colours."""

import subprocess

from roblox import identite, render


def test_the_creators_elements_are_read_with_named_sides_and_kept_inside_the_moment():
    class G:
        def _generate_content(self, parts, **kw):
            assert "CREATEUR" in parts[-1]["text"] and "Melon" not in parts[-1]["text"]      # general: no example of a video
            return {"elements": [
                {"type": "avatar", "debut": 1.0, "fin": 3.0, "cadre": {"gauche": 0.6, "haut": 0.4, "droite": 1.0, "bas": 1.0},
                 "pose": "gene", "entree": "glisse_droite", "mouvement": "rebond"},
                {"type": "webcam", "debut": 0, "fin": 9, "cadre": {"gauche": 0, "haut": 0, "droite": 0.2, "bas": 0.25}},
                {"type": "avatar", "debut": 2, "fin": 4, "cadre": [0.1, 0.2, 0.3, 0.4]},                 # a list: refused
                {"type": "interface", "debut": 1, "fin": 2, "cadre": {"gauche": 0, "haut": 0, "droite": 1, "bas": 1}},
                {"type": "pseudo", "debut": 5, "fin": 4, "cadre": {"gauche": 0, "haut": 0, "droite": 1, "bas": 1}}]}
    els = identite.detect("f.mp4", 10.0, 20.0, gemini=G())
    assert [(e["type"], e["debut"], e["fin"]) for e in els] == [("avatar", 11.0, 13.0), ("webcam", 10.0, 19.0)]
    assert els[0]["cadre"] == [0.6, 0.4, 1.0, 1.0] and els[0]["pose"] == "gene" and els[0]["entree"] == "glisse_droite"
    assert els[1]["pose"] in identite.POSES                                    # no pose said: one of ours anyway


def test_the_mascot_covers_each_appearance_where_the_short_shows_it():
    segs = [{"fichier": "w0.mp4", "a": 10.0, "b": 20.0, "x": 0.5}, {"fichier": "w5.mp4", "a": 3.0, "b": 8.0, "x": 0.5}]
    apps = {"w0.mp4": [{"type": "avatar", "debut": 12.0, "fin": 15.0, "cadre": [0.7, 0.4, 1.0, 1.0], "pose": "pleure"},
                       {"type": "avatar", "debut": 30.0, "fin": 31.0, "cadre": [0.7, 0.4, 1.0, 1.0], "pose": "rire"},
                       {"type": "webcam", "debut": 0, "fin": 60, "cadre": [0, 0, 0.2, 0.2]}],
            "w5.mp4": [{"type": "avatar", "debut": 4.0, "fin": 5.0, "cadre": [0.0, 0.5, 0.3, 1.0], "pose": "pleure"}]}
    evs = identite.events(segs, apps, emotions={}, punchlines=[9.0])          # punchlines: seconds of the Short
    covers = [e for e in evs if e["couvre"]]
    assert [(round(e["t0"], 2), round(e["t1"], 2)) for e in covers] == [(1.85, 5.15), (10.85, 12.15)]  # 2nd file: after 10 s
    assert covers[0]["droite"] and not covers[1]["droite"]                     # on its avatar's side
    assert covers[1]["pose"] != covers[0]["pose"]                             # never the same pose twice in a row
    assert all(0 <= e["cx"] - e["w"] / 2 and e["cx"] + e["w"] / 2 <= render.W for e in covers)     # always whole on screen
    assert any(not e["couvre"] and abs(e["t0"] - 9.0) < 0.01 for e in evs)  # the punchline, not covered by anything


def test_the_emotions_of_the_lines_bring_the_mascot_out_when_no_avatar_is_there():
    segs = [{"fichier": "w0.mp4", "a": 0.0, "b": 10.0, "x": 0.5}]
    evs = identite.events(segs, {}, emotions={"w0.mp4": [(2.0, "colere"), (2.5, "colere"), (6.0, "rire")]}, punchlines=[])
    assert [(e["t0"], e["pose"]) for e in evs] == [(2.0, "colere"), (6.0, "rire")]   # 2.5: too close, same pose


def test_the_texts_take_the_channels_colours(tmp_path):
    ass = render.Ass(theme="identite")
    ass.add("Titre", 0, 2, f"Le {{\\c{render.JAUNE}}}pire{{\\c{render.BLANC}}} gardien")
    text = open(ass.write(str(tmp_path / "i.ass")), encoding="utf-8").read()
    assert "Lilita One" in text and identite.ORANGE in text and render.JAUNE not in text and identite.VIOLET in text
    assert "Montserrat" in open(render.Ass().write(str(tmp_path / "b.ass")), encoding="utf-8").read()   # without: unchanged


def test_the_mascot_really_appears_in_the_video(tmp_path):
    base = str(tmp_path / "base.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=gray:s=1080x1920:r=30:d=3", "-f", "lavfi",
                    "-i", "anullsrc=r=44100:cl=stereo", "-t", "3", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", base], check=True)
    evs = [{"t0": 0.5, "t1": 2.5, "pose": "rire", "cx": 300.0, "bas": 1360.0, "h": 470.0, "entree": "pop",
            "mouvement": "rebond", "droite": False, "couvre": False}]
    out = str(tmp_path / "out.mp4")
    identite.overlay(base, evs, flashes=[1.0], out=out)
    frame = str(tmp_path / "f.png")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "1.5", "-i", out, "-frames:v", "1", frame], check=True)
    from PIL import Image
    im = Image.open(frame).convert("RGB")
    r, g, b = im.getpixel((300, 1200))
    assert (r, g, b) != im.getpixel((900, 200)) and b > r                    # the purple hoodie, on the grey
