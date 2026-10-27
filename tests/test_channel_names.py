"""Every route taking a channel name checks it the same way: an allowed
format (never "..", a path) and a channel that exists (AUDIT.md §8.4)."""

import json
from pathlib import Path

import pytest

from channel_manager import ChannelManager


@pytest.fixture
def known(project):
    Path("channels/channel_config.json").write_text(json.dumps({"chana": {"display_name": "A"}}))
    Path("channels/chana").mkdir()
    return "chana"


@pytest.mark.parametrize("name, ok", [("chana", True), ("lungte888", False), ("..", False), ("a/b", False),
                                      ("", False), ("x" * 65, False), ("ça", False)])
def test_one_check_for_format_and_existence(known, name, ok):
    manager = ChannelManager()
    if ok:
        assert manager.validate_channel_name(name) == name
    else:
        with pytest.raises(ValueError):
            manager.validate_channel_name(name)


def test_dot_dot_never_writes_outside_channels(client, known):
    before = sorted(p.name for p in Path(".").iterdir())

    profile = client.put("/api/channels/%2E%2E/profile", json={"display_name": "pwned"})
    background = client.post("/api/channels/%2E%2E/background", files={"file": ("b.jpg", b"jpg", "image/jpeg")})
    removed = client.delete("/api/channels/%2E%2E/background")

    assert profile.status_code == 400 and background.status_code == 400 and removed.status_code == 400
    assert sorted(p.name for p in Path(".").iterdir()) == before                # no profile.json / background.jpg at the root


def test_an_unknown_channel_is_404_and_creates_nothing(client, known):
    assert client.get("/api/channels/inconnue/profile").status_code == 404
    assert client.post("/api/channels/inconnue/background", files={"file": ("b.jpg", b"jpg", "image/jpeg")}).status_code == 404
    assert not Path("channels/inconnue").exists()


def test_a_known_channel_still_works(client, known):
    assert client.get("/api/channels/chana/profile").status_code == 200
    assert client.put("/api/channels/chana/profile", json={"display_name": "A2"}).json()["display_name"] == "A2"


def test_names_in_request_bodies_are_checked_too(client, known):
    assert client.post("/api/publish", json={"channel_name": "../x"}).status_code == 400
    assert client.post("/api/schedule", json={"method": "static", "target_channel": "inconnue"}).status_code == 404
    assert client.post("/api/adaptations", json={"reference_url": "https://t/x", "channels": ["../x"]}).status_code == 400
    assert client.post("/api/adaptations/p1/new-version", json={"channel": "../x"}).status_code == 400
    assert client.get("/api/videos", params={"channel": "../x"}).status_code == 400


def test_every_route_with_a_channel_in_its_path_is_checked(client, known):
    """No route forgets it: each answers 400 for "..", whatever it does."""
    from fastapi.routing import APIRoute
    import webapp.main as m
    unchecked = []
    for route in m.app.routes:
        if not isinstance(route, APIRoute) or not ("{channel_name}" in route.path or "{channel}" in route.path):
            continue
        url = route.path.replace("{channel_name}", "%2E%2E").replace("{channel}", "%2E%2E")
        for param in ("{pid}", "{youtube_id}", "{filename}", "{k}"):
            url = url.replace(param, "x" if param != "{k}" else "0")
        method = sorted(route.methods)[0]
        if client.request(method, url).status_code != 400:
            unchecked.append(f"{method} {route.path}")
    assert unchecked == []
