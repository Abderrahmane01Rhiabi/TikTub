"""No action ever lands on a channel by mistake: "default" (or no channel at
all) is an error, never "the first channel" (AUDIT.md §8.5)."""

import json
from pathlib import Path

import pytest

import db
import youtube_uploader as yu
from batch_processor import BatchProcessor
from channel_manager import ChannelManager


def configure(*names):
    Path("channels/channel_config.json").write_text(json.dumps({n: {"display_name": n} for n in names}))
    for n in names:
        Path("channels", n).mkdir(parents=True, exist_ok=True)
        Path("channels", n, "credentials.json").write_text(json.dumps({"installed": {"client_id": n}}))


@pytest.mark.parametrize("name", ["default", None, ""])
def test_default_or_no_channel_is_an_error_not_the_first_channel(project, name):
    configure("meme_culture", "zit_bliss")

    with pytest.raises(ValueError) as error:
        ChannelManager().get_channel_paths(name)

    assert "chaîne" in str(error.value)


def test_youtube_helpers_need_a_channel(project):
    configure("meme_culture")
    with pytest.raises(ValueError):
        yu.authenticate_youtube(interactive=False)
    with pytest.raises(ValueError):
        yu.get_credentials_path()


def test_default_is_refused_at_creation(project):
    assert ChannelManager().add_channel("default", "Default") is False
    assert not Path("channels/default").exists()


def test_an_old_root_credentials_json_is_not_turned_into_a_default_channel(project):
    import shutil
    shutil.rmtree("channels")
    Path("credentials.json").write_text(json.dumps({"installed": {"client_id": "old"}}))

    ChannelManager()

    assert not Path("channels/default").exists()
    config = Path("channels/channel_config.json")
    assert not config.exists() or "default" not in json.loads(config.read_text())


def test_a_video_without_channel_is_never_scheduled(project):
    project.add_video("ok", title="ok")
    project.add_video("orphan", channel=None, title="orphan")
    bp = BatchProcessor("config.yaml")

    schedule = bp.create_upload_schedule(schedule_method="static")

    assert [e["video_id"] for e in schedule] == ["ok"]
    saved = bp.scheduler.load_schedule()
    assert [(u["video_id"], bool(u["reason"])) for u in saved["unscheduled"]] == [("orphan", True)]
    assert "default" not in {e["channel"] for e in saved["schedule"]}


def test_a_schedule_entry_without_channel_is_not_published_anywhere(project, fake_youtube):
    configure("meme_culture")
    project.add_video("orphan", channel=None, video_path=project.add_video_file("orphan.mp4"))
    project.write_schedule([{"video_id": "orphan", "title": "orphan", "scheduled_time": "2030-01-07T18:00:00+01:00",
                             "video_data": {}}])

    results = yu.upload_all_channels_schedule()

    assert fake_youtube.inserted == []
    assert [(r["video_id"], r["success"]) for r in results] == [("orphan", False)]
    assert "chaîne" in results[0]["error"]
    assert db.get_video("orphan")["status"] == "ready_for_upload"


def test_stats_never_ask_youtube_for_a_default_channel(project, monkeypatch):
    import stats_tracker
    asked = []
    monkeypatch.setattr(yu, "get_video_stats", lambda ch, ids: asked.append(ch) or {})
    project.add_video("orphan", channel=None, status="scheduled_on_youtube", youtube_id="YT1",
                      scheduled_publish_time="2020-01-01T09:00:00+01:00")

    stats_tracker.sync_youtube_statuses(BatchProcessor("config.yaml"))

    assert None not in asked and "default" not in asked
