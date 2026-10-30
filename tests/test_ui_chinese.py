from dataclasses import replace
import os
import re

import numpy as np
import pytest

from depthstrike.boxing import BoxingSimulation
from depthstrike.calibration import GuidanceState
from depthstrike.config import AppConfig
from depthstrike.feedback import HandFeedback
from depthstrike.types import DepthStrikeError, Target
from depthstrike.ui_text import MAIN_TITLE, draw_text


def test_distinct_chinese_characters_render_as_distinct_visible_glyphs():
    first = np.zeros((80, 160, 3), np.uint8)
    second = first.copy()
    draw_text(first, "中", (10, 50), 1., (0, 0, 255))
    draw_text(second, "文", (10, 50), 1., (0, 0, 255))
    assert np.count_nonzero(first) > 30
    assert np.count_nonzero(second) > 30
    assert not np.array_equal(first, second)
    assert not first[:, :, :2].any()  # The canvas remains BGR.


def test_chinese_text_respects_panel_width_and_clips_at_image_edges():
    image = np.full((60, 160, 3), 255, np.uint8)
    draw_text(image, "这是一条需要缩小或截断的中文提示", (10, 35), .8, (0, 0, 0), max_width=80)
    assert np.any(image[:, 10:90] != 255)
    assert np.all(image[:, 92:] == 255)
    draw_text(image, "中文", (-8, 5), .7)
    before = image.copy()
    draw_text(image, "不可见", (200, 200))
    assert np.array_equal(before, image)


def test_missing_explicit_chinese_font_fails_with_a_useful_error(monkeypatch, tmp_path):
    monkeypatch.setenv("DEPTHSTRIKE_FONT", str(tmp_path/"missing-font.ttf"))
    with pytest.raises(DepthStrikeError, match="DEPTHSTRIKE_FONT"):
        draw_text(np.zeros((40, 100, 3), np.uint8), "中文", (0, 30))


def assert_chinese_labels(messages):
    leftovers = [m for m in messages if re.search(r"[A-Za-z]{2,}", m.replace("Esc", ""))]
    assert not leftovers, leftovers


def test_main_pages_translate_states_sources_guidance_and_unknown_codes(monkeypatch, skeleton):
    from depthstrike import visualization
    messages = []
    monkeypatch.setattr(visualization, "draw_text", lambda image, value, *args, **kwargs: messages.append(str(value)))
    config = AppConfig(partial_tracking=True)
    base = BoxingSimulation(config).step(skeleton(0))
    target = Target(0, "left", np.array((-.2, .04, 1.5)), .08, True)
    for status in ("CALIBRATING", "RUNNING", "PAUSED", "FINISHED", "TRACKING LOST", "WAITING FOR CAMERA", "FUTURE_STATUS"):
        for mode in ("demo", "camera", "replay", "rgbd-replay", "opencv-experience", "astra-experience"):
            state = replace(base, status=status, targets=(target,),
                phases={"left":"ATTACKING", "right":"RECOVERING"},
                feedback={"left":HandFeedback("future_reason_code", .12, .22, .03)})
            visualization.render_hud(state, None, config, mode)
    for stage, message in (("REACH_LEFT", "hold_reach"), ("PRACTICE_RIGHT", "practice_right"),
                           ("REACH_RIGHT", "missing_body"), ("RUNNING", "future_message_code")):
        visualization.render_hud(replace(base, guidance=GuidanceState(stage, .4, message)), None, config)
    challenge = {"content_evidence":"synthetic", "cue_index":2, "total":9, "hand":"right", "until_window_s":.25}
    visualization.render_hud(replace(base, challenge=challenge), None, config, "replay")
    assert "左手" in messages and "右手" in messages
    assert any("主机计时" in message for message in messages)
    assert_chinese_labels(messages)


def test_review_page_translates_results_reasons_and_playback_controls(monkeypatch, skeleton):
    from depthstrike import review_view
    from test_review_view import make_report
    report = make_report(skeleton)
    messages = []
    monkeypatch.setattr(review_view, "draw_text", lambda image, value, *args, **kwargs: messages.append(str(value)))
    review_view.render_review(report)
    assert "关卡顺序" in messages
    assert any("未命中" in message for message in messages)
    assert_chinese_labels(messages)


@pytest.mark.skipif(os.name != "nt" or not os.environ.get("DEPTHSTRIKE_GUI_TESTS"), reason="Opt-in real Windows title test")
def test_real_opencv_window_uses_a_unicode_chinese_title():
    import ctypes as ct
    from ctypes import wintypes
    import cv2
    from depthstrike.ui_text import set_window_title
    identity = f"DepthStrikeUnicodeTest-{os.getpid()}"
    cv2.namedWindow(identity, cv2.WINDOW_AUTOSIZE)
    try:
        handle = set_window_title(cv2, identity, MAIN_TITLE)
        assert handle
        user32 = ct.WinDLL("user32", use_last_error=True)
        user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ct.c_int]
        user32.GetWindowTextW.restype = ct.c_int
        title = ct.create_unicode_buffer(256)
        assert user32.GetWindowTextW(handle, title, len(title)) > 0
        assert title.value == MAIN_TITLE
    finally:
        cv2.destroyWindow(identity)
