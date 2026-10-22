import json

import pytest

from depthstrike.config import AppConfig
from depthstrike.recording import PoseRecorder
from depthstrike.sources import DemoPoseSource
from depthstrike.types import HitEvent


def record_demo(path, *, forged_events=False, frames=600, actions=None):
    config = AppConfig()
    with DemoPoseSource(config=config, total_frames=frames) as source, PoseRecorder(path, config, source.describe()) as recorder:
        while (frame := source.read()) is not None:
            recorder.write(frame, (HitEvent(frame.timestamp_s, "right", 99, 1, 999),) if forged_events else (),
                           actions=(actions or {}).get(frame.frame_id, ()))


def test_author_extracts_completed_punch_order_from_raw_motion_not_scores(tmp_path):
    from depthstrike.motion_authoring import author_recording
    a, b = tmp_path/"a.jsonl", tmp_path/"b.jsonl"
    record_demo(a)
    record_demo(b, forged_events=True)
    original, forged = author_recording(a), author_recording(b)
    assert len(original.cues) == 9
    assert [c.hand for c in original.cues] == ["left", "right", "left", "right", "left", "right", "left", "right", "left"]
    assert original.cues == forged.cues
    data = original.to_dict()
    assert data["source"]["evidence"] == "synthetic"
    assert len(data["source"]["sha256"]) == 64
    assert all(c.offset[2] < -.7 for c in original.cues)
    assert all(a.end_s <= b.start_s for a, b in zip(original.cues, original.cues[1:]))


def test_author_rejects_setup_only_and_legacy_input(tmp_path):
    from depthstrike.motion_authoring import author_recording
    path = tmp_path/"setup.jsonl"
    record_demo(path, frames=100)
    with pytest.raises(ValueError, match="completed|calibration"):
        author_recording(path)
    legacy = tmp_path/"legacy.jsonl"
    config = AppConfig(interaction_mode="legacy")
    with PoseRecorder(legacy, config) as recorder:
        with DemoPoseSource(config=config, total_frames=240) as source:
            while (frame := source.read()) is not None: recorder.write(frame, ())
    with pytest.raises(ValueError, match="guided"):
        author_recording(legacy)


def test_author_discards_a_punch_interrupted_by_tracking_loss(tmp_path):
    from depthstrike.motion_authoring import author_recording
    clean, broken = tmp_path/"clean.jsonl", tmp_path/"broken.jsonl"
    record_demo(clean)
    # First official punch extends at about 9.1 s; loss cancels that attempt.
    record_demo(broken, actions={276: ["tracking_lost"]})
    a, b = author_recording(clean), author_recording(broken)
    assert len(b.cues) == len(a.cues)-1
    assert b.cues[0].hand == "right"


def test_author_refuses_multiple_formal_rounds_in_one_recipe(tmp_path):
    from depthstrike.motion_authoring import author_recording
    path = tmp_path/"reset.jsonl"
    record_demo(path, actions={450: ["reset"]})
    with pytest.raises(ValueError, match="reset|round"):
        author_recording(path)
