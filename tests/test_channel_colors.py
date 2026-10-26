"""Channel colors: stored in channel_config.json, sent by /api/channels."""

import json
from pathlib import Path

from channel_manager import ChannelManager

# what core.js hard-coded until now (any other channel was shown in #9aa1ac)
CORE_JS_COLORS = {"meme_culture": "#38bdf8", "animeshorts": "#b18cfd", "prince_moulay_hassan": "#fb923c",
                  "lungte888": "#e2e8f0", "zit_bliss": "#fd8cc4", "lungtemotivates": "#2dd4bf"}


def write_config(names):
    Path("channels/channel_config.json").write_text(json.dumps({n: {"display_name": n, "active": True} for n in names}))


def test_existing_channels_keep_exactly_their_current_color(client, project):
    write_config([*CORE_JS_COLORS, "cestpourca", "lihadha_alsabab"])

    colors = {c["name"]: c["color"] for c in client.get("/api/channels").json()}

    assert colors == {**CORE_JS_COLORS, "cestpourca": "#9aa1ac", "lihadha_alsabab": "#9aa1ac"}
    stored = json.loads(Path("channels/channel_config.json").read_text())
    assert {n: c["color"] for n, c in stored.items()} == colors                 # saved once, then kept


def test_a_new_channel_gets_a_color_nobody_uses(project):
    write_config([*CORE_JS_COLORS, "cestpourca"])
    manager = ChannelManager()
    manager.list_channels()

    manager.add_channel("nouvelle", "Nouvelle")
    manager.add_channel("autre", "Autre")

    colors = {c["name"]: c["color"] for c in manager.list_channels()}
    assert colors["nouvelle"] not in set(CORE_JS_COLORS.values()) | {"#9aa1ac"}
    assert colors["autre"] not in set(CORE_JS_COLORS.values()) | {"#9aa1ac", colors["nouvelle"]}


def test_the_page_no_longer_hard_codes_channel_colors():
    core = (Path(__file__).resolve().parent.parent / "webapp/static/js/core.js").read_text(encoding="utf-8")
    assert "CHANNEL_COLORS" not in core and "meme_culture" not in core
