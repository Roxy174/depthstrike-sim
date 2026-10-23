from dataclasses import replace

import numpy as np
import pytest

from depthstrike.config import AppConfig
from depthstrike.types import Intrinsics, Joint3D, Landmark, RGBDFrame, SkeletonFrame


def frame(depth=2., t=0.):
    return RGBDFrame(round(t*1000), t, np.zeros((21, 21, 3), np.uint8),
                     np.full((21, 21), depth, np.float32), Intrinsics(21, 21, 50, 50, 10, 10))


def test_masked_hole_recovery_needs_recent_matching_surface():
    from depthstrike.fusion import estimate_joint
    f = frame()
    f.depth_m[10, 10] = 0
    c = replace(AppConfig(), fusion_mode="masked")
    p = Landmark(10/21, 10/21, .95)
    mask = np.ones((21, 21), np.float32)
    recovered = estimate_joint(p, f, c, mask=mask, previous=Joint3D((0, 0, 2), .95))
    assert recovered.position == pytest.approx((0, 0, 2))
    assert recovered.provenance == "depth_patch" and 0 < recovered.depth_quality < 1
    assert estimate_joint(p, f, c, mask=mask).position is None
    assert estimate_joint(p, f, c, mask=np.zeros_like(mask), previous=Joint3D((0, 0, 2), .9)).position is None
    assert estimate_joint(p, f, c, mask=mask, previous=Joint3D((0, 0, 1), .9)).position is None


def test_masked_fusion_rejects_mixed_foreground_and_background():
    from depthstrike.fusion import estimate_joint
    f = frame()
    f.depth_m[8:13, 8:10] = 3.
    f.depth_m[10, 10] = 0
    assert estimate_joint(Landmark(10/21, 10/21, .9), f,
        replace(AppConfig(), fusion_mode="masked"), mask=np.ones((21, 21)),
        previous=Joint3D((0, 0, 2), .9)).position is None


def test_hand_observation_does_not_require_visible_elbow(skeleton):
    from depthstrike.interaction import estimate_hand
    f = skeleton(0, invalid="left_elbow")
    f.joints.update(left_index=Joint3D((-.18, .04, 1.78), .9),
                    left_pinky=Joint3D((-.22, .04, 1.78), .9))
    j = estimate_hand(f.joints, "left", replace(AppConfig(), fist_mode="hand"))
    assert j.position == pytest.approx((-.2, .04, 1.78))
    assert j.provenance == "hand_surface"


def test_prediction_provenance_survives_recording(tmp_path):
    from depthstrike.recording import PoseRecorder, PoseReplaySource
    j = Joint3D((0, 0, 2), .4, provenance="predicted", depth_quality=.2, age_s=.1)
    path = tmp_path/"p.jsonl"
    with PoseRecorder(path, AppConfig()) as r:
        r.write(SkeletonFrame(0, 0., {"left_wrist": j}), ())
    with PoseReplaySource(path) as r:
        restored = r.read().joints["left_wrist"]
    assert restored.provenance == "predicted" and restored.age_s == .1
    assert not restored.is_observed


def test_prediction_is_display_only_and_expires(skeleton):
    from depthstrike.tracking import SkeletonTracker
    c = replace(AppConfig(), partial_tracking=True, smoothing_tau_s=0)
    tracker = SkeletonTracker(c)
    tracker.update(skeleton(0, left_z=1.9))
    tracker.update(skeleton(.05, left_z=1.8))
    missing = tracker.update(skeleton(.10, invalid="left_wrist"))
    assert missing.joints["left_wrist"].position is None
    ghost = tracker.display_joints["left_wrist"]
    assert ghost.provenance == "predicted" and ghost.position[2] == pytest.approx(1.7)
    tracker.update(skeleton(.19, invalid="left_wrist"))
    assert "left_wrist" not in tracker.display_joints
    tracker.reset()
    assert tracker.display_joints == {}


def test_one_euro_reduces_jitter_and_does_not_bridge_missing(skeleton):
    from depthstrike.tracking import SkeletonTracker
    tracker = SkeletonTracker(replace(AppConfig(), filter_mode="one_euro"))
    zs = [tracker.update(skeleton(n*.03, left_z=1.85+(-1)**n*.01)).joints["left_wrist"].position[2]
          for n in range(40)]
    assert np.std(zs[10:]) < .005
    tracker.update(skeleton(1.20, invalid="left_wrist"))
    assert tracker.update(skeleton(1.23, left_z=1.4)).joints["left_wrist"].position[2] == 1.4


def test_one_euro_cutoff_responds_to_motion_speed(skeleton):
    from depthstrike.tracking import SkeletonTracker
    slow, fast = [SkeletonTracker(AppConfig(filter_mode="one_euro", one_euro_beta=b)) for b in (.001, 10.)]
    for tracker in (slow, fast): tracker.update(skeleton(0))
    a = slow.update(skeleton(.05, left_z=1.4)).joints["left_wrist"].position[2]
    b = fast.update(skeleton(.05, left_z=1.4)).joints["left_wrist"].position[2]
    assert b < a-.15


def test_left_reach_preserves_progress_with_other_wrist_missing(skeleton):
    from test_calibration import Driver
    d = Driver(skeleton, AppConfig(partial_tracking=True, fist_offset_m=0, smoothing_tau_s=0))
    d.hold(.7)
    assert d.hold(.5, left_z=1.4, invalid="right_wrist").guidance.stage == "RETURN_LEFT"
    assert d.hold(.3, invalid="right_wrist").guidance.stage == "REACH_RIGHT"


def test_other_arm_loss_allows_observed_active_hand_hit(skeleton):
    from test_calibration import Driver
    d = Driver(skeleton, AppConfig(partial_tracking=True, fist_offset_m=0, smoothing_tau_s=0))
    d.running()
    state = d.hold(0, left_z=1.4, invalid="right_elbow")
    assert state.score == 10 and state.hits == 1


def test_lost_active_hand_cannot_score_on_reappearance(skeleton):
    from test_calibration import Driver
    d = Driver(skeleton, AppConfig(partial_tracking=True, fist_offset_m=0, smoothing_tau_s=0))
    d.running()
    d.hold(0, invalid="left_wrist")
    assert d.hold(0, left_z=1.4).score == 0
    d.hold(.1)
    assert d.hold(0, left_z=1.4).score == 10


def test_predicted_input_is_not_promoted_to_scoring_observation(skeleton):
    from depthstrike.tracking import SkeletonTracker
    f = skeleton(0)
    f.joints["left_wrist"] = Joint3D((0, 0, 1), 1, provenance="predicted")
    assert SkeletonTracker(AppConfig()).update(f).joints["left_wrist"].position is None


def test_partial_right_practice_works_without_left_wrist(skeleton):
    from test_calibration import Driver
    d = Driver(skeleton, AppConfig(partial_tracking=True, fist_offset_m=0, smoothing_tau_s=0))
    d.calibrate()
    d.hold(.1)
    d.hold(0, left_z=1.4)
    d.hold(.15, invalid="left_wrist")
    assert d.hold(0, right_z=1.4, invalid="left_wrist").guidance.stage == "COUNTDOWN"


def test_workspace_rejects_obstacles_and_unknown_depth():
    from depthstrike.spatial import DepthWorkspace
    assert DepthWorkspace(frame(3.)).path_status((0, 0, 1), (0, 0, 2), .05) == "clear"
    assert DepthWorkspace(frame(1.5)).path_status((0, 0, 1), (0, 0, 2), .05) == "blocked"
    assert DepthWorkspace(frame(0.)).path_status((0, 0, 1), (0, 0, 2), .05) == "unknown"
    assert DepthWorkspace(frame(3.)).path_status((0, 0, 1), (10, 0, 2), .05) == "unknown"


def test_virtual_sphere_is_occluded_by_nearer_real_surface():
    from depthstrike.spatial import target_visibility_mask
    f = frame(3.)
    f.depth_m[:, :10] = 1.
    visible = target_visibility_mask(f, np.array((0, 0, 2)), .2)
    assert not visible[10, 8] and visible[10, 12]
    f.depth_m[:] = 0
    assert not target_visibility_mask(f, np.array((0, 0, 2)), .2).any()


def test_setup_preview_is_visible_but_never_scores(skeleton):
    from depthstrike.boxing import BoxingSimulation
    sim = BoxingSimulation(AppConfig(preview_targets=True))
    state = sim.step(skeleton(0))
    assert len(state.targets) == 2 and all(t.preview and not t.active for t in state.targets)
    assert state.score == 0 and not state.events


def test_workspace_prevents_blocked_calibration_target(skeleton):
    from test_calibration import Driver
    from depthstrike.spatial import DepthWorkspace
    d = Driver(skeleton, AppConfig(spatial_layout=True, fist_offset_m=0, smoothing_tau_s=0))
    # Broad synthetic camera sees a wall at 1 m in front of the entire player.
    f = frame(1.)
    d.sim.set_workspace(DepthWorkspace(f))
    state = d.calibrate()
    assert state.guidance.profile is None
    assert state.guidance.message_code == "workspace_blocked"


@pytest.mark.parametrize("variant", ["lite", "full", "heavy"])
def test_model_variant_selects_matching_official_endpoint(tmp_path, variant):
    import io
    import runpy
    api = runpy.run_path("scripts/download_pose_model.py")
    def opener(url, timeout):
        assert url == f"https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_{variant}/float16/1/pose_landmarker_{variant}.task"
        return io.BytesIO(b"synthetic weights")
    metadata = api["download_model"](tmp_path/f"{variant}.task", variant=variant, opener=opener)
    assert metadata["variant"] == variant


def test_fault_report_exercises_predictions_and_actual_loss():
    from depthstrike.robustness import build_report
    report = build_report()
    assert report["evidence"] == "synthetic"
    assert report["fusion"]["conservative"]["recovered_holes"] == 0
    assert report["fusion"]["masked"]["recovered_holes"] > 0
    assert all(v["background_rejections"] > 0 for v in report["fusion"].values())
    rows = {r["case"]: r for r in report["sessions"] if r["policy"] == "adaptive"}
    assert rows["left_wrist_loss"]["predicted_frames"] > 0
    assert rows["left_wrist_loss"]["unobserved_frames"] > 0
    assert rows["left_wrist_loss"]["fault_stages"] == ["RUNNING"]
    assert rows["timestamp_regression"]["frames"] == 600


def test_fusion_history_expires_and_cannot_chain_hole_recovery():
    from depthstrike.fusion import fuse_skeleton
    c = AppConfig(fusion_mode="masked")
    points = {"left_wrist": Landmark(10/21, 10/21, .9)}
    old = SkeletonFrame(0, 0., {"left_wrist": Joint3D((0, 0, 2), .9)})
    f = frame(t=.3)
    f.depth_m[10, 10] = 0
    assert not fuse_skeleton(f, points, c, mask=np.ones((21, 21)), previous=old).joints["left_wrist"].is_observed
    old = replace(old, joints={"left_wrist": Joint3D((0, 0, 2), .9, provenance="depth_patch")})
    f = replace(f, timestamp_s=.1)
    assert not fuse_skeleton(f, points, c, mask=np.ones((21, 21)), previous=old).joints["left_wrist"].is_observed


def test_hand_proxy_source_switch_requires_new_guard(skeleton):
    from test_calibration import Driver
    d = Driver(skeleton, AppConfig(partial_tracking=True, fist_mode="hand", fist_offset_m=0, smoothing_tau_s=0))
    d.running()
    def with_hand(t, **pose):
        f = skeleton(t, **pose)
        for hand in ("left", "right"):
            wrist = f.joints[f"{hand}_wrist"].position
            f.joints[f"{hand}_index"] = Joint3D(wrist+(.02, 0, -.04), .95)
            f.joints[f"{hand}_pinky"] = Joint3D(wrist+(-.02, 0, -.04), .95)
        return f
    d.make = with_hand
    assert d.hold(0, left_z=1.4).score == 0


def test_kalman_weights_depth_quality(skeleton):
    from depthstrike.tracking import SkeletonTracker
    trackers = [SkeletonTracker(AppConfig(filter_mode="kalman")) for _ in range(2)]
    outputs = []
    for tracker, quality in zip(trackers, (1., .05)):
        for n in range(10): tracker.update(skeleton(n*.03))
        f = skeleton(.3, left_z=1.5)
        f.joints["left_wrist"] = replace(f.joints["left_wrist"], depth_quality=quality)
        outputs.append(tracker.update(f).joints["left_wrist"].position[2])
    assert outputs[0] < outputs[1]-.1


def test_partial_author_drops_pending_punch_when_its_hand_disappears(tmp_path):
    from depthstrike.motion_authoring import author_recording
    from depthstrike.recording import PoseRecorder
    from depthstrike.sources import DemoPoseSource
    c = AppConfig(partial_tracking=True)
    path = tmp_path/"author.jsonl"
    with DemoPoseSource(c, total_frames=600) as source, PoseRecorder(path, c, source.describe()) as recorder:
        while (f := source.read()) is not None:
            if f.frame_id == 278:
                f.joints["left_wrist"] = Joint3D(None)
            recorder.write(f, ())
    recipe = author_recording(path)
    assert len(recipe.cues) == 8
    assert recipe.cues[0].hand == "right"


def test_evaluation_uses_selected_hand_surface_proxy(skeleton):
    from depthstrike.evaluation import EvaluationManifest, evaluate_frames
    from test_evaluation import manifest_dict
    frames = [skeleton(0), skeleton(.1, left_z=1.7)]
    for f, z in zip(frames, (1.81, 1.54)):
        f.joints.update(left_index=Joint3D((-.18, .04, z), .95), left_pinky=Joint3D((-.22, .04, z), .95))
    report = evaluate_frames(frames, EvaluationManifest.from_dict(manifest_dict()),
                             AppConfig(fist_mode="hand", fist_offset_m=0, smoothing_tau_s=0))
    assert report["methods"]["3d_swept_entry"]["prediction_count"] == 1


def test_punch_tracker_rejects_predicted_point_even_with_high_confidence():
    from depthstrike.boxing import PunchTracker
    p = PunchTracker(AppConfig())
    shoulder = Joint3D((0, 0, 2), 1)
    p.update(0, Joint3D((0, 0, 1.85), 1), shoulder)
    assert not p.update(.1, Joint3D((0, 0, 1.4), 1, provenance="predicted"), shoulder).can_hit


def test_kalman_cannot_bridge_an_absent_joint_key(skeleton):
    from depthstrike.tracking import SkeletonTracker
    tracker = SkeletonTracker(AppConfig(filter_mode="kalman", partial_tracking=True))
    for n in range(10): tracker.update(skeleton(n*.03))
    tracker.update(SkeletonFrame(300, .3, {}))
    assert tracker.display_joints["left_wrist"].provenance == "predicted"
    assert tracker.update(skeleton(.33, left_z=1.4)).joints["left_wrist"].position[2] == 1.4


def test_author_discards_pending_punch_on_hand_proxy_source_change(tmp_path):
    from depthstrike.motion_authoring import author_recording
    from depthstrike.recording import PoseRecorder
    from depthstrike.sources import DemoPoseSource
    c = AppConfig(partial_tracking=True, fist_mode="hand")
    path = tmp_path/"source-switch.jsonl"
    with DemoPoseSource(c, total_frames=600) as source, PoseRecorder(path, c, source.describe()) as recorder:
        while (f := source.read()) is not None:
            if f.frame_id >= 278:
                for hand in ("left", "right"):
                    wrist = f.joints[f"{hand}_wrist"].position
                    f.joints[f"{hand}_index"] = Joint3D(wrist+(.02, 0, -.04), .95)
                    f.joints[f"{hand}_pinky"] = Joint3D(wrist+(-.02, 0, -.04), .95)
            recorder.write(f, ())
    recipe = author_recording(path)
    assert len(recipe.cues) == 8 and recipe.cues[0].hand == "right"
