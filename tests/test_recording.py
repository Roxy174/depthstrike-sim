from dataclasses import replace
import json

import numpy as np
import pytest

from depthstrike.boxing import BoxingSimulation
from depthstrike.config import AppConfig


def test_pose_roundtrip_preserves_invalid_joints_and_config(tmp_path, skeleton):
    from depthstrike.recording import PoseRecorder, PoseReplaySource
    path = tmp_path / "pose.jsonl"
    config = replace(AppConfig(), round_duration_s=8)
    with PoseRecorder(path, config) as recorder:
        recorder.write(skeleton(0, invalid="left_wrist"), ())
        recorder.write(skeleton(.1), (), actions=["pause"])
    with PoseReplaySource(path) as source:
        first = source.read()
        assert first.timestamp_s == 0 and first.joints["left_wrist"].position is None
        assert source.config.round_duration_s == 8
        assert source.read().joints["left_wrist"].position == pytest.approx((-.2, .04, 1.85))
        assert source.actions == ["pause"]
        assert source.read() is None


@pytest.mark.parametrize("corruption", ["bad-json", "nan", "time-reversal", "version", "units"])
def test_invalid_pose_recording_rejected(tmp_path, skeleton, corruption):
    from depthstrike.recording import PoseRecorder, PoseReplaySource
    path = tmp_path / "bad.jsonl"
    with PoseRecorder(path, AppConfig()) as recorder:
        recorder.write(skeleton(0), ())
        recorder.write(skeleton(.1), ())
    rows = [json.loads(x) for x in path.read_text().splitlines()]
    if corruption == "version": rows[0]["version"] = 999
    elif corruption == "units": rows[0]["unit"] = "mm"
    elif corruption == "nan": rows[1]["joints"]["left_wrist"]["position"][0] = float("nan")
    elif corruption == "time-reversal": rows[2]["timestamp_s"] = 0.
    content = "\n".join(json.dumps(x) for x in rows)+"\n"
    path.write_text(content if corruption != "bad-json" else content+"{oops\n")
    with pytest.raises(ValueError):
        with PoseReplaySource(path) as source:
            while source.read() is not None: pass


def test_rgbd_roundtrip(tmp_path):
    from depthstrike.recording import RGBDRecorder, RGBDReplaySource
    from test_fusion import rgbd
    original = rgbd()
    directory = tmp_path / "rgbd"
    with RGBDRecorder(directory, AppConfig()) as recorder:
        recorder.write(original)
    with RGBDReplaySource(directory) as source:
        restored = source.read()
        np.testing.assert_array_equal(restored.color_rgb, original.color_rgb)
        np.testing.assert_array_equal(restored.depth_m, original.depth_m)
        assert restored.intrinsics == original.intrinsics
        assert source.read() is None


@pytest.mark.parametrize("corruption", ["escape", "missing", "object", "nan", "version"])
def test_unsafe_rgbd_recording_rejected(tmp_path, corruption):
    from depthstrike.recording import RGBDRecorder, RGBDReplaySource
    from test_fusion import rgbd
    directory = tmp_path / "rgbd"
    with RGBDRecorder(directory, AppConfig()) as recorder:
        recorder.write(rgbd())
    meta_path = directory / "frames.jsonl"
    rows = [json.loads(x) for x in meta_path.read_text().splitlines()]
    if corruption == "escape": rows[1]["color"] = "../outside.npy"
    elif corruption == "missing": rows[1]["color"] = "absent.npy"
    elif corruption == "object": np.save(directory / rows[1]["color"], np.array([object()]))
    elif corruption == "nan": rows[1]["timestamp_s"] = float("nan")
    elif corruption == "version": rows[0]["version"] = 100
    meta_path.write_text("\n".join(json.dumps(x) for x in rows)+"\n")
    with pytest.raises(ValueError):
        with RGBDReplaySource(directory) as source: source.read()


def test_demo_punches_and_replay_produce_identical_scores(tmp_path):
    from depthstrike.sources import DemoPoseSource
    from depthstrike.recording import PoseRecorder, PoseReplaySource
    path = tmp_path / "demo.jsonl"
    config = AppConfig(interaction_mode="legacy")
    sim = BoxingSimulation(config)
    events = []
    with DemoPoseSource(config=config) as source, PoseRecorder(path, config) as recorder:
        for _ in range(240):
            frame = source.read()
            state = sim.step(frame)
            events.extend(state.events)
            recorder.write(frame, state.events)
    assert sim.hits >= 4
    replay = BoxingSimulation(config)
    reproduced = []
    with PoseReplaySource(path) as source:
        while (frame := source.read()) is not None:
            reproduced.extend(replay.step(frame).events)
    assert replay.score == sim.score
    assert reproduced == events


def test_recording_never_overwrites_existing_data(tmp_path, skeleton):
    from depthstrike.recording import PoseRecorder, RGBDRecorder
    path = tmp_path / "existing.jsonl"
    path.write_text("important")
    with pytest.raises(FileExistsError): PoseRecorder(path, AppConfig())
    assert path.read_text() == "important"
    directory = tmp_path / "data"
    directory.mkdir()
    with pytest.raises(FileExistsError): RGBDRecorder(directory, AppConfig())


def test_empty_array_reports_corrupt_recording_not_raw_eof(tmp_path):
    from depthstrike.recording import RGBDRecorder, RGBDReplaySource
    from test_fusion import rgbd
    directory = tmp_path/"broken"
    with RGBDRecorder(directory, AppConfig()) as recorder: recorder.write(rgbd())
    (directory/"000000_rgb.npy").write_bytes(b"")
    with RGBDReplaySource(directory) as source:
        with pytest.raises(ValueError, match="array|recording|NPY"): source.read()


def test_array_shape_is_bounded_before_loading_payload(tmp_path, monkeypatch):
    from depthstrike.recording import RGBDRecorder, RGBDReplaySource
    from test_fusion import rgbd
    directory = tmp_path/"oversized"
    with RGBDRecorder(directory, AppConfig()) as recorder: recorder.write(rgbd())
    with (directory/"000000_rgb.npy").open("wb") as stream:
        np.lib.format.write_array_header_1_0(stream, {
            "descr": "<f4", "fortran_order": False, "shape": (10**10,)})
    # Never actually attempt the dangerous 40 GB allocation in a regression test.
    def forbidden(*args, **kwargs): raise AssertionError("Unsafe payload load before header validation")
    monkeypatch.setattr(np, "load", forbidden)
    with RGBDReplaySource(directory) as source:
        with pytest.raises(ValueError, match="large|size|shape|bytes"): source.read()


def test_quality_reason_survives_tracking_and_v2_roundtrip(tmp_path, skeleton):
    from depthstrike.recording import PoseRecorder, PoseReplaySource
    from depthstrike.tracking import SkeletonTracker
    from depthstrike.types import Joint3D
    frame = skeleton(0)
    frame = replace(frame, joints={**frame.joints,
                                  "left_wrist": Joint3D(None, invalid_reason="invalid_depth")})
    filtered = SkeletonTracker(AppConfig()).update(frame)
    assert filtered.joints["left_wrist"].invalid_reason == "invalid_depth"
    path = tmp_path/"quality.jsonl"
    with PoseRecorder(path, AppConfig()) as recorder:
        recorder.write(frame, ())
    assert json.loads(path.read_text().splitlines()[0])["version"] == 2
    with PoseReplaySource(path) as source:
        assert source.read().joints["left_wrist"].invalid_reason == "invalid_depth"
        assert source.config.interaction_mode == "guided"


def test_v1_fixture_retains_legacy_mode_and_twenty_points():
    from depthstrike.app import run_session
    from depthstrike.recording import PoseReplaySource
    from depthstrike.visualization import NullView
    with PoseReplaySource("tests/fixtures/straight_punches.jsonl") as source:
        assert source.config.interaction_mode == "legacy"
        summary = run_session(source, BoxingSimulation(source.config), NullView())
    assert (summary.frames, summary.hits, summary.score) == (4, 2, 20)


def test_v2_requires_explicit_interaction_mode(tmp_path, skeleton):
    from depthstrike.recording import PoseRecorder, PoseReplaySource
    path = tmp_path/"v2.jsonl"
    with PoseRecorder(path, AppConfig()) as recorder:
        recorder.write(skeleton(0), ())
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows[0]["version"] = 2
    rows[0]["config"].pop("interaction_mode", None)
    path.write_text("\n".join(json.dumps(row) for row in rows)+"\n")
    with pytest.raises(ValueError, match="mode|config"):
        PoseReplaySource(path)
