"""quota.py: quota day boundaries and per-Google-project accounting."""

from datetime import datetime

import pytz

import db
import quota

PARIS = pytz.timezone("Europe/Paris")


def test_quota_day_follows_pacific_midnight_not_paris():
    # Pacific midnight = 09:00 in Paris (both on summer time in October)
    assert quota.quota_day(PARIS.localize(datetime(2026, 10, 13, 8, 30))) == "2026-10-12"
    assert quota.quota_day(PARIS.localize(datetime(2026, 10, 13, 9, 30))) == "2026-10-13"


def test_next_reset_is_next_pacific_midnight():
    reset = quota.next_reset(PARIS.localize(datetime(2026, 10, 13, 12, 0)))
    assert reset.astimezone(PARIS) == PARIS.localize(datetime(2026, 10, 14, 9, 0))


def test_channels_from_the_same_google_project_share_one_quota(project):
    project.add_channel("chanA", client_id="project-1")
    project.add_channel("chanB", client_id="project-1")
    project.add_channel("chanC", client_id="project-2")

    keys = {ch: quota.project_key_for_channel(ch) for ch in ("chanA", "chanB", "chanC")}

    assert keys["chanA"] == keys["chanB"] != keys["chanC"]
    assert "project-1" not in keys["chanA"]  # the client_id itself is never stored


def test_channel_without_credentials_is_its_own_project(project):
    assert quota.project_key_for_channel("nocreds") == "channel:nocreds"


def test_status_estimate_uses_the_configured_cost(project):
    project.add_channel("chanA")  # config.yaml.example: upload_cost 100, daily_units 10000
    quota.record_upload("chanA")
    quota.record_upload("chanA")

    status = quota.status_for_channel("chanA")

    assert status["uploads_today"] == 2
    assert status["estimated_uploads_left"] == (10000 - 200) // 100
    assert not status["exhausted"]


def test_exhausted_is_per_day(project):
    project.add_channel("chanA")
    key = quota.project_key_for_channel("chanA")
    db.set_quota_exhausted(key, "2000-01-01")  # some past day
    assert not quota.is_exhausted("chanA")
    quota.mark_exhausted("chanA")
    assert quota.is_exhausted("chanA")


def test_bad_config_values_fall_back_to_defaults(project):
    with open("config.yaml", "w", encoding="utf-8") as f:
        f.write("youtube:\n  quota:\n    upload_cost: -5\n    daily_units: lots\n")
    assert quota.load_settings() == {"upload_cost": quota.DEFAULT_UPLOAD_COST,
                                     "daily_units": quota.DEFAULT_DAILY_UNITS}
