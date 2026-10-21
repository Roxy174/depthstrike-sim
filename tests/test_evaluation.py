from copy import deepcopy
from dataclasses import replace
import json

import pytest

from depthstrike.config import AppConfig
from depthstrike.types import Joint3D


def manifest_dict():
    return {"schema_version": 1, "evidence": "synthetic", "label_basis": "Hand-derived unit-test geometry",
            "unit": "m", "timestamp_unit": "s", "coordinates": "camera_x_right_y_down_z_forward",
            "intrinsics": {"width": 640, "height": 480, "fx": 600, "fy": 600, "cx": 320, "cy": 240},
            "targets": [{"target_id": 0, "hand": "left", "center": [-.2, .04, 1.5], "radius": .08}],
            "active_schedule": [{"start_s": 0, "end_s": 2, "hand": "left", "target_id": 0}],
            "expected_windows": [], "ignore_windows": []}


def test_match_is_one_to_one_and_duplicate_predictions_are_false_positives():
    from depthstrike.evaluation import match_events
    labels = [{"start_s": .1, "end_s": .2, "hand": "left", "target_id": 0},
              {"start_s": .4, "end_s": .5, "hand": "left", "target_id": 0}]
    predictions = [{"timestamp_s": t, "hand": "left", "target_id": 0} for t in (.15, .18, .7)]
    result = match_events(predictions, labels, [])
    assert (result["tp"], result["fp"], result["fn"], result["duplicates"]) == (1, 2, 1, 1)
    assert result["precision"] == pytest.approx(1/3)
    assert result["recall"] == .5


def test_empty_event_sets_have_null_denominators():
    from depthstrike.evaluation import match_events
    result = match_events([], [], [])
    assert result["precision"] is None and result["recall"] is None


@pytest.mark.parametrize("mutation", ["overlap", "touch", "unknown_target", "bad_intrinsics", "bad_unit", "bad_evidence", "partial_ignore", "bad_schedule", "empty_schedule", "nonfinite"])
def test_invalid_manifest_is_rejected(mutation):
    from depthstrike.evaluation import EvaluationManifest
    data = manifest_dict()
    window = {"start_s": .2, "end_s": .4, "hand": "left", "target_id": 0}
    if mutation in ("overlap", "touch"):
        data["expected_windows"] = [window, {**window, "start_s": .3 if mutation == "overlap" else .4, "end_s": .5}]
    elif mutation == "unknown_target": data["active_schedule"][0]["target_id"] = 99
    elif mutation == "bad_intrinsics": data["intrinsics"]["fx"] = -1
    elif mutation == "bad_unit": data["unit"] = "mm"
    elif mutation == "bad_evidence": data["evidence"] = "verified_human_accuracy"
    elif mutation == "partial_ignore":
        data["expected_windows"] = [window]
        data["ignore_windows"] = [{"start_s": .3, "end_s": .6}]
    elif mutation == "bad_schedule": data["active_schedule"].append({**data["active_schedule"][0]})
    elif mutation == "empty_schedule": data["active_schedule"] = []
    elif mutation == "nonfinite": data["targets"][0]["center"][0] = float("nan")
    with pytest.raises(ValueError): EvaluationManifest.from_dict(data)


def test_ignore_windows_exclude_predictions_and_wholly_contained_labels():
    from depthstrike.evaluation import match_events
    labels = [{"start_s": .1, "end_s": .2, "hand": "left", "target_id": 0}]
    predictions = [{"timestamp_s": .15, "hand": "left", "target_id": 0}]
    result = match_events(predictions, labels, [{"start_s": 0, "end_s": .3}])
    assert (result["tp"], result["fp"], result["fn"]) == (0, 0, 0)


def test_each_method_sees_same_target_schedule(skeleton):
    from depthstrike.evaluation import EvaluationManifest, evaluate_frames
    data = manifest_dict()
    data["active_schedule"][0]["end_s"] = .15
    frames = [skeleton(0), skeleton(.1, left_z=1.5), skeleton(.2), skeleton(.3, left_z=1.5)]
    result = evaluate_frames(frames, EvaluationManifest.from_dict(data), AppConfig(fist_offset_m=0, smoothing_tau_s=0))
    hashes = {r["schedule_sha256"] for r in result["methods"].values()}
    assert len(hashes) == 1
    assert all(p["timestamp_s"] < .15 for r in result["methods"].values() for p in r["predictions"])
    assert result["methods"]["3d_swept_punch"]["fp"] == 1


def test_active_hand_switch_cannot_create_contact_entry(skeleton):
    from depthstrike.evaluation import EvaluationManifest, evaluate_frames
    data = manifest_dict()
    data["active_schedule"][0]["start_s"] = .1
    frames = [skeleton(0, left_z=1.5), skeleton(.1, left_z=1.5), skeleton(.2, left_z=1.5)]
    result = evaluate_frames(frames, EvaluationManifest.from_dict(data), AppConfig(fist_offset_m=0, smoothing_tau_s=0))
    assert all(not r["predictions"] for r in result["methods"].values())


@pytest.mark.parametrize("start,end,discrete,swept", [
    (.01, .2, 1, 1),  # Entry at .06 is after activation.
    (0., .08, 0, 1),  # Swept entry is before deactivation, current sample after it.
    (.07, .2, 1, 0),  # Discrete detection is at .1; swept contact predates activation.
    (0., .05, 0, 0),  # Neither candidate time is in the active interval.
])
def test_contact_candidates_use_their_own_time_at_schedule_boundaries(skeleton, start, end, discrete, swept):
    from depthstrike.evaluation import EvaluationManifest, evaluate_frames
    data = manifest_dict()
    data["active_schedule"][0].update(start_s=start, end_s=end)
    if swept:
        data["expected_windows"] = [{"start_s": max(.05, start), "end_s": min(.11, end-.001),
                                     "hand": "left", "target_id": 0}]
    frames = [skeleton(0), skeleton(.1, left_z=1.5)]
    result = evaluate_frames(frames, EvaluationManifest.from_dict(data), AppConfig(fist_offset_m=0, smoothing_tau_s=0))
    methods = result["methods"]
    assert methods["3d_discrete_entry"]["prediction_count"] == discrete
    for name in ("3d_swept_entry", "3d_swept_punch"):
        assert methods[name]["prediction_count"] == swept
        if swept:
            assert methods[name]["predictions"][0]["timestamp_s"] == pytest.approx(.06)
            assert (methods[name]["tp"], methods[name]["fn"]) == (1, 0)


def test_rgbd_transcription_preserves_synthetic_evidence_and_original_metadata(tmp_path):
    from types import SimpleNamespace
    from depthstrike.evaluation import evaluate_recording
    from depthstrike.recording import PoseRecorder, PoseReplaySource, RGBDRecorder, RGBDReplaySource
    from depthstrike.sources import CameraPoseSource
    from test_fusion import rgbd
    config = AppConfig()
    original = {"source": "blank fixture", "evidence": "synthetic", "pose_model": {"sha256": "upstream"},
                "calibration": {"id": "fixture-calibration"}}
    directory, path, labels = tmp_path/"rgbd", tmp_path/"poses.jsonl", tmp_path/"labels.json"
    with RGBDRecorder(directory, config, original) as recorder:
        recorder.write(rgbd())
    estimator = SimpleNamespace(metadata={"sha256": "current"}, detect=lambda f: {}, close=lambda: None)
    with CameraPoseSource(config, capture=RGBDReplaySource(directory), estimator=estimator) as source:
        with PoseRecorder(path, config, source.describe()) as recorder:
            recorder.write(source.read(), ())
    with PoseReplaySource(path) as replay:
        metadata = replay.metadata
    assert metadata.get("evidence") == "synthetic"
    assert metadata["source"] == "rgbd-replay"
    assert metadata["recording_metadata"] == original
    assert metadata["pose_model"] == {"sha256": "current"}
    data = manifest_dict()
    data["evidence"] = "recorded"
    labels.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="Synthetic recording"):
        evaluate_recording(path, labels)
    data["evidence"] = "synthetic"
    labels.write_text(json.dumps(data), encoding="utf-8")
    assert evaluate_recording(path, labels)["evidence"] == "synthetic"


def test_tracking_recovery_cannot_bridge_into_a_hit(skeleton):
    from depthstrike.evaluation import EvaluationManifest, evaluate_frames
    frames = [skeleton(0), skeleton(.1, invalid="left_elbow"), skeleton(.15, left_z=1.5)]
    result = evaluate_frames(frames, EvaluationManifest.from_dict(manifest_dict()), AppConfig(fist_offset_m=0, smoothing_tau_s=0))
    assert all(not r["predictions"] for r in result["methods"].values())
    assert result["tracking_invalid_ratio"] == pytest.approx(1/3)


def test_analytic_scenarios_demonstrate_component_tradeoffs_without_fake_truth():
    from depthstrike.evaluation import evaluate_synthetic_suite
    result = evaluate_synthetic_suite()
    assert result["evidence"] == "synthetic"
    scenes = {s["name"]: s for s in result["scenarios"]}
    assert scenes["depth_mismatch"]["methods"]["2d_entry"]["fp"] == 1
    assert scenes["depth_mismatch"]["methods"]["3d_discrete_entry"]["fp"] == 0
    assert scenes["fast_crossing"]["methods"]["3d_discrete_entry"]["fn"] == 1
    assert scenes["fast_crossing"]["methods"]["3d_swept_entry"]["tp"] == 1
    assert scenes["slow_extension"]["methods"]["3d_swept_entry"]["fp"] == 1
    assert scenes["slow_extension"]["methods"]["3d_swept_punch"]["fp"] == 0
    assert scenes["contact_reentry"]["methods"]["3d_discrete_entry"]["duplicates"] == 1
    assert scenes["contact_reentry"]["methods"]["3d_swept_punch"]["duplicates"] == 0
    assert scenes["stationary_contact"]["methods"]["3d_discrete_entry"]["duplicates"] == 0
    assert result == evaluate_synthetic_suite()


def test_external_recording_uses_independent_labels_not_recorded_events(tmp_path, skeleton):
    from depthstrike.evaluation import evaluate_recording
    from depthstrike.recording import PoseRecorder
    from depthstrike.types import HitEvent
    path, labels = tmp_path/"poses.jsonl", tmp_path/"labels.json"
    config = AppConfig(fist_offset_m=0, smoothing_tau_s=0)
    with PoseRecorder(path, config, {"evidence": "synthetic"}) as recorder:
        recorder.write(skeleton(0), ())
        recorder.write(skeleton(.1, left_z=1.5), (HitEvent(.1, "right", 99, 42, 999),))
    labels.write_text(json.dumps(manifest_dict()))
    result = evaluate_recording(path, labels)
    assert result["label_count"] == 0
    assert result["methods"]["3d_swept_punch"]["fp"] == 1
    assert len(result["input_sha256"]) == 64
    assert result["methods"]["3d_swept_punch"]["parameters"]["fist_offset_m"] == 0


def test_empty_recording_and_forged_evidence_are_rejected(tmp_path):
    from depthstrike.evaluation import evaluate_recording
    from depthstrike.recording import PoseRecorder
    path, labels = tmp_path/"poses.jsonl", tmp_path/"labels.json"
    with PoseRecorder(path, AppConfig(), {"evidence": "synthetic"}): pass
    data = manifest_dict()
    labels.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="empty|frames"): evaluate_recording(path, labels)
    data["evidence"] = "recorded"
    labels.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="synthetic|evidence"): evaluate_recording(path, labels)


def test_comparison_cli_creates_report_exclusively_and_reports_bad_input(tmp_path, capsys):
    from depthstrike.evaluation import main
    output = tmp_path/"report.json"
    assert main(["--suite", "synthetic", "--output", str(output)]) == 0
    original = output.read_bytes()
    assert json.loads(original)["evidence"] == "synthetic"
    assert main(["--suite", "synthetic", "--output", str(output)]) != 0
    assert output.read_bytes() == original
    malformed = tmp_path/"labels.json"
    malformed.write_text("[]")
    assert main(["--input", "tests/fixtures/straight_punches.jsonl", "--labels", str(malformed),
                 "--output", str(tmp_path/"bad.json")]) != 0
    assert "Traceback" not in capsys.readouterr().err


def test_supplied_external_labels_have_two_hand_checked_attacks():
    from depthstrike.evaluation import evaluate_recording
    result = evaluate_recording("tests/fixtures/straight_punches.jsonl",
                                "tests/fixtures/evaluation/straight-punch-labels.json")
    method = result["methods"]["3d_swept_punch"]
    assert (method["tp"], method["fp"], method["fn"]) == (2, 0, 0)
