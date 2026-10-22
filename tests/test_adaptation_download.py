"""YouTube downloads (measured 2026-10-21): three videos "not available" with
the cookies came down without them thanks to a PO token, one in 360p first then
in 1080p."""

import os

import pytest
import yt_dlp

from adaptation import sources

REACHABLE = sources.reachable          # conftest replaces it in every test


class FakeYDL:
    answers = []                       # one per run: an info dict (written as a file) or an error message
    seen = []

    def __init__(self, opts):
        self.opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def extract_info(self, url, download=True, process=True):
        FakeYDL.seen.append("cookies" if "cookiefile" in self.opts else "plain")
        a = FakeYDL.answers.pop(0)
        if isinstance(a, str):
            raise yt_dlp.utils.DownloadError(a)
        if download:
            with open(self.prepare_filename(a), "w") as f:
                f.write(str(a["height"]))
        return a

    def prepare_filename(self, info):
        return self.opts["outtmpl"].replace("%(ext)s", "mp4")


@pytest.fixture
def ydl(monkeypatch, tmp_path):
    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYDL)
    (tmp_path / "youtube_cookies.txt").write_text("# cookies")
    FakeYDL.answers, FakeYDL.seen = [], []
    return FakeYDL


def test_youtube_is_tried_without_the_cookies_first_then_with_them(ydl, tmp_path):
    opts = sources.ytdlp_opts(outtmpl=str(tmp_path / "v.%(ext)s"))
    ydl.answers = ["ERROR: [youtube] x: This video is not available", {"height": 1080}]
    got = sources._fetch("https://www.youtube.com/watch?v=x", opts)
    assert ydl.seen == ["plain", "cookies"] and got["info"]["height"] == 1080
    ydl.answers, ydl.seen = [{"height": 720}], []
    sources._fetch("https://www.tiktok.com/@a/video/1", opts)
    assert ydl.seen == ["cookies"]                                   # other sites: as before


def test_a_youtube_picture_under_720p_is_fetched_once_more_and_the_best_kept(ydl, tmp_path):
    opts = sources.ytdlp_opts(cookies=False, outtmpl=str(tmp_path / "v.%(ext)s"))
    ydl.answers = [{"height": 360}, {"height": 1080}]
    got = sources._fetch("https://www.youtube.com/watch?v=x", opts)
    assert got["info"]["height"] == 1080 and open(got["path"]).read() == "1080"
    assert not [p for p in os.listdir(tmp_path) if p.endswith(".low")]
    ydl.answers = [{"height": 360}, {"height": 360}]                 # really 360p: the first file stays
    got = sources._fetch("https://www.youtube.com/watch?v=x", opts)
    assert open(got["path"]).read() == "360" and len(ydl.answers) == 0
    ydl.answers = [{"height": 360}]
    sources._fetch("https://www.youtube.com/watch?v=x", opts, again_if_low=False)
    assert ydl.answers == []


def test_reachable_says_no_only_when_refused_with_and_without_the_cookies(ydl):
    ydl.answers = ["This video is not available", {"height": 1080}]
    assert REACHABLE("https://www.youtube.com/watch?v=x") is True
    ydl.answers = ["This video is not available", "This video is not available"]
    assert REACHABLE("https://www.youtube.com/watch?v=x") is False
    ydl.answers = ["Sign in to confirm you're not a bot", "Sign in to confirm you're not a bot"]
    assert REACHABLE("https://www.youtube.com/watch?v=x") is None


def test_a_link_that_gives_no_video_is_not_sent_to_gemini(monkeypatch, tmp_path):
    from adaptation import finder

    class YDL(FakeYDL):
        def extract_info(self, url, download=True, process=True):
            path = self.opts["outtmpl"].replace("%(ext)s", "html")
            open(path, "w").write("<html>photos</html>")
            return {"ext": "html"}

        def prepare_filename(self, info):
            return self.opts["outtmpl"].replace("%(ext)s", "html")
    monkeypatch.setattr(yt_dlp, "YoutubeDL", YDL)
    sent = []

    class G:
        def _upload_video_file(self, path):
            sent.append(path)
    with pytest.raises(finder.FinderError, match="ne donne pas de vidéo"):
        finder._watch("https://www.tiktok.com/@a/video/1", G(), "prompt")
    assert sent == []
