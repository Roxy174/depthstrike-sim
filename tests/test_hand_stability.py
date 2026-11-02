"""Measured hand surfaces, soft segmentation boundaries and model selection."""
from dataclasses import replace
from types import SimpleNamespace
from pathlib import Path
import json

import numpy as np
import pytest

from depthstrike.config import AppConfig, load_config
from depthstrike.fusion import estimate_joint, fuse_skeleton
from depthstrike.sources import CameraPoseSource
from depthstrike.types import Joint3D, Landmark, SkeletonFrame
from test_adaptive import frame


POINT = Landmark(10/21, 10/21, .95)


def improved(**values):
    base = AppConfig(interaction_mode='direct', fist_mode='wrist', partial_tracking=True,
        fusion_mode='masked', segmentation_threshold=.35, depth_surface_mode='center_cluster', depth_recovery_s=.2)
    return replace(base, **values)


def test_soft_person_boundary_is_separate_from_joint_confidence():
    f, mask = frame(), np.full((21, 21), .45)
    assert estimate_joint(POINT, f, AppConfig(fusion_mode='masked'), mask=mask).invalid_reason == 'outside_person'
    assert estimate_joint(POINT, f, improved(), mask=mask).is_observed
    assert estimate_joint(replace(POINT, confidence=.5), f, improved(), mask=mask).invalid_reason == 'low_confidence'
    assert estimate_joint(POINT, f, improved(), mask=np.zeros_like(mask)).invalid_reason == 'outside_person'


def test_measured_hand_majority_survives_a_minority_of_background_pixels():
    f = frame()
    f.depth_m[8:13, 8:10] = 3.  # 15 measured hand pixels, 10 background pixels.
    mask = np.ones((21, 21))
    assert not estimate_joint(POINT, f, AppConfig(fusion_mode='masked'), mask=mask).is_observed
    joint = estimate_joint(POINT, f, improved(), mask=mask)
    assert joint.position == pytest.approx((0, 0, 2.))
    assert joint.provenance == 'observed' and joint.depth_quality <= .6+1e-6


@pytest.mark.parametrize('center', [0., 1.5])
def test_background_majority_cannot_replace_a_hand_surface(center):
    f = frame(depth=2.5)
    f.depth_m[10, 10] = center
    assert not estimate_joint(POINT, f, improved(), mask=np.ones((21, 21)),
                             previous=Joint3D((0, 0, 1.5), .95)).is_observed


def test_ambiguous_depth_without_a_majority_is_rejected():
    f = frame(depth=3.)
    f.depth_m[8:13, 9:11] = 2.
    assert estimate_joint(POINT, f, improved(), mask=np.ones((21, 21))).position is None


def test_repeated_holes_use_recent_direct_measurement_without_refreshing_its_time():
    config = improved()
    anchors = {'left_wrist': (0., Joint3D((0, 0, 2), .95))}
    previous = None
    for t in (.05, .1, .15, .2):
        f = frame(t=t)
        f.depth_m[10, 10] = 0
        previous = fuse_skeleton(f, {'left_wrist': POINT}, config, mask=np.ones((21, 21)),
                                 previous=previous, depth_anchors=anchors)
        assert previous.joints['left_wrist'].provenance == 'depth_patch'
    f = frame(t=.21)
    f.depth_m[10, 10] = 0
    result = fuse_skeleton(f, {'left_wrist': POINT}, config, mask=np.ones((21, 21)),
                           previous=previous, depth_anchors=anchors)
    assert not result.joints['left_wrist'].is_observed


def test_low_confidence_direct_anchor_cannot_enable_hole_recovery():
    f = frame(t=.1)
    f.depth_m[10, 10] = 0
    result = fuse_skeleton(f, {'left_wrist': POINT}, improved(), mask=np.ones((21, 21)),
        depth_anchors={'left_wrist': (0., Joint3D((0, 0, 2), .2))})
    assert not result.joints['left_wrist'].is_observed


@pytest.mark.parametrize('timestamp, provenance, depth', [(1., 'observed', 2.), (0., 'depth_patch', 2.), (0., 'observed', 2.5)])
def test_recovery_rejects_future_or_recovered_anchors_and_changed_depth(timestamp, provenance, depth):
    f = frame(t=.1)
    f.depth_m[10, 10] = 0
    result = fuse_skeleton(f, {'left_wrist': POINT}, improved(), mask=np.ones((21, 21)),
        depth_anchors={'left_wrist': (timestamp, Joint3D((0, 0, depth), .95, provenance=provenance))})
    assert not result.joints['left_wrist'].is_observed


class Capture:
    def __init__(self, frames): self.frames = iter(frames); self.closed = False
    def read(self): return next(self.frames, None)
    def describe(self): return {'evidence': 'synthetic', 'source': 'analytic depth fixture'}
    def close(self): self.closed = True


def source_frames():
    result = []
    for t in (0., .05, .1, .15, .21):
        f = frame(t=t)
        if t: f.depth_m[10, 10] = 0
        result.append(f)
    return result


def estimator():
    return SimpleNamespace(detect=lambda f: {'left_wrist': POINT}, last_mask=np.full((21, 21), .45), close=lambda: None)


def test_camera_source_recovers_fresh_depth_patches_and_reports_where_points_are_lost():
    with CameraPoseSource(improved(), capture=Capture(source_frames()), estimator=estimator()) as source:
        rows = [source.read() for _ in range(5)]
        assert [r.joints['left_wrist'].is_observed for r in rows] == [True]*4+[False]
        quality = source.quality_summary()
        assert quality['frames'] == 5
        assert quality['hands']['left'] == {'pose_confident': 5, 'measured_3d': 4, 'depth_patch': 3, 'fusion_invalid_depth': 1}
        assert quality['hands']['right'] == {'pose_missing': 5}
        assert source._depth_anchors == {}
        quality['hands']['left'].clear()
        assert source.quality_summary()['hands']['left']['measured_3d'] == 4


@pytest.mark.parametrize('t', [0., .31])
def test_camera_source_does_not_recover_across_reversed_time_or_a_long_gap(t):
    f = frame(t=t)
    f.depth_m[10, 10] = 0
    with CameraPoseSource(improved(), capture=Capture([frame(t=.1), f]), estimator=estimator()) as source:
        assert source.read().joints['left_wrist'].is_observed
        assert not source.read().joints['left_wrist'].is_observed


def test_a_cached_depth_does_not_create_a_missing_pose_landmark():
    pose = estimator()
    with CameraPoseSource(improved(), capture=Capture(source_frames()), estimator=pose) as source:
        source.read()
        pose.detect = lambda f: {}
        assert not source.read().joints
        assert source.quality_summary()['hands']['left']['pose_missing'] == 1


def test_metrics_record_pose_and_depth_availability_without_recording_images(monkeypatch, tmp_path, capsys):
    from depthstrike import cli
    capture = Capture(source_frames())
    monkeypatch.setattr(cli, 'CameraPoseSource', lambda c, **kw: CameraPoseSource(c, capture=capture, estimator=estimator(), **kw))
    config_path, report = tmp_path/'config.json', tmp_path/'quality.json'
    config_path.write_text(json.dumps(improved().to_dict()))
    assert cli.main(['--source', 'camera', '--headless', '--frames', '5', '--config', str(config_path), '--metrics', str(report)]) == 0
    capsys.readouterr()
    data = json.loads(report.read_text())['metadata']['tracking_quality']
    assert data['frames'] == 5 and data['hands']['left']['measured_3d'] == 4
    assert 'not_accuracy' in data['scope'] and capture.closed
    tracked = json.loads(report.read_text())['metadata']['tracked_hand_quality']
    assert tracked['frames'] == 5 and tracked['hands']['left']['measured_3d'] == 4


def test_quality_report_distinguishes_a_motion_rejection_from_a_valid_raw_point():
    from depthstrike.tracking import SkeletonTracker
    tracker = SkeletonTracker(improved(reject_tracking_outliers=True))
    for t, z in ((0., 2.), (.03, 3.), (.06, 2.)):
        tracker.update(SkeletonFrame(round(t*1000), t, {'left_wrist': Joint3D((0, 0, z), .95)}))
    assert tracker.quality_summary()['hands']['left'] == {'measured_3d': 2, 'motion_outlier': 1}
    tracker.reset()
    assert tracker.quality_summary()['frames'] == 3  # Diagnostics span the session, including resets.


@pytest.mark.parametrize('variant', ['lite', 'full', 'heavy'])
def test_live_model_override_selects_requested_weights(monkeypatch, capsys, variant):
    from depthstrike import cli
    configs = []
    class Source:
        def __init__(self, config, **kwargs): configs.append(config); self.remaining = True
        def read(self):
            if not self.remaining: return None
            self.remaining = False
            return SkeletonFrame(0, 0., {})
        def describe(self): return {'evidence': 'synthetic'}
        def close(self): pass
        def __enter__(self): return self
        def __exit__(self, *a): self.close()
    monkeypatch.setattr(cli, 'CameraPoseSource', Source)
    assert cli.main(['--source', 'camera', '--headless', '--frames', '1', '--pose-model', variant]) == 0
    capsys.readouterr()
    assert configs[0].model_path == f'models/pose_landmarker_{variant}.task'


def test_pose_model_override_cannot_change_a_pose_only_recording(capsys):
    from depthstrike.cli import main
    assert main(['--source', 'replay', '--input', 'unused.jsonl', '--pose-model', 'full']) != 0
    assert 'no images' in capsys.readouterr().err


def test_rgbd_replay_model_override_is_applied_after_loading_recorded_config(monkeypatch, tmp_path, capsys):
    from depthstrike import cli
    from depthstrike.recording import RGBDRecorder
    directory = tmp_path/'rgbd'
    with RGBDRecorder(directory, AppConfig(), {'evidence': 'synthetic'}) as recorder:
        recorder.write(frame())
    configs = []
    def create(config):
        configs.append(config)
        return SimpleNamespace(detect=lambda f: {}, close=lambda: None)
    monkeypatch.setattr('depthstrike.sources.PoseEstimator', create)
    assert cli.main(['--source', 'rgbd-replay', '--input', str(directory), '--headless', '--pose-model', 'heavy']) == 0
    capsys.readouterr()
    assert configs[0].model_path == 'models/pose_landmarker_heavy.task'


def test_live_defaults_use_full_and_historical_configs_retain_lite():
    assert load_config().model_path == 'models/pose_landmarker_full.task'
    assert load_config('configs/adaptive.json').model_path == 'models/pose_landmarker_full.task'
    assert AppConfig().model_path == 'models/pose_landmarker_lite.task'
    assert AppConfig().depth_surface_mode == 'strict'


@pytest.mark.parametrize('values', [{'pose_confidence_threshold': 2}, {'segmentation_threshold': 2},
    {'depth_surface_mode': 'unknown'}, {'depth_recovery_s': -1}])
def test_invalid_stability_parameters_are_rejected(values):
    with pytest.raises(ValueError): AppConfig(**values)


@pytest.mark.parametrize('variant', ['lite', 'full', 'heavy'])
def test_real_model_variant_initializes_and_processes_a_frame(variant):
    pytest.importorskip('mediapipe')
    from depthstrike.pose import PoseEstimator
    model = Path(f'models/pose_landmarker_{variant}.task')
    if not model.is_file(): pytest.skip('Optional model not downloaded')
    with PoseEstimator(AppConfig(model_path=str(model), pose_confidence_threshold=.5)) as pose:
        assert isinstance(pose.detect(frame()), dict)
        assert pose.metadata['filename'] == model.name
        assert pose.metadata['pose_confidence_threshold'] == .5
