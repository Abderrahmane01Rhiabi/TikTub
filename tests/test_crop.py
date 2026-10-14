"""Black-border detection: judged over the whole video, not its first frame."""

import cv2
import numpy as np
import pytest

from video_processor import crop_black_borders

W, H = 360, 640


def write(path, frames):
    out = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10, (W, H))
    for f in frames:
        out.write(f)
    out.release()
    return str(path)


def black():
    return np.zeros((H, W, 3), np.uint8)


def caption_only():
    f = black()
    cv2.putText(f, "They did him dirty", (40, 330), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    return f


def picture(top=0, bottom=H):
    f = black()
    f[top:bottom] = np.random.default_rng(0).integers(60, 255, (bottom - top, W, 3), dtype=np.uint8)
    return f


def test_a_black_intro_with_a_caption_no_longer_crops_the_video_to_the_caption(tmp_path):
    """Regression: the first frame (black + caption) decided alone, so the
    whole video was cropped to the caption's thin band."""
    path = write(tmp_path / "intro.mp4", [caption_only()] * 15 + [picture()] * 45)
    crop = crop_black_borders(path)
    assert crop is None or (crop[2] >= W - 2 and crop[3] >= H - 2)


def test_real_black_bars_are_still_cut(tmp_path):
    path = write(tmp_path / "bars.mp4", [picture(200, 440)] * 40)  # 16:9-ish band in a vertical frame
    x, y, w, h = crop_black_borders(path)
    assert w == W and 180 - 2 <= y <= 200 and 240 <= h <= 240 + 40 + 4


def test_bars_with_a_black_intro_are_cut_to_the_picture_not_the_caption(tmp_path):
    path = write(tmp_path / "both.mp4", [caption_only()] * 10 + [picture(160, 480)] * 40)
    x, y, w, h = crop_black_borders(path)
    assert y <= 160 and y + h >= 480 and h < H - 100


@pytest.mark.parametrize("frames", [[black()] * 30, [caption_only()] * 30])
def test_nothing_but_black_or_a_lone_caption_is_left_whole(tmp_path, frames):
    assert crop_black_borders(write(tmp_path / "x.mp4", frames)) is None
