from dataclasses import replace

import numpy as np
import pytest

from depthstrike.boxing import BoxingSimulation
from depthstrike.config import AppConfig
from depthstrike.types import Joint3D


class Driver:
    def __init__(self, skeleton, config=None):
        self.make = skeleton
        self.config = config or AppConfig(fist_offset_m=0, smoothing_tau_s=0)
        self.sim = BoxingSimulation(self.config)
        self.t = -.05
        self.state = None

    def hold(self, duration, **pose):
        for _ in range(round(duration/.05)+1):
            self.t += .05
            self.state = self.sim.step(self.make(self.t, **pose))
        return self.state

    def calibrate(self, left_z=1.4, right_z=1.4):
        self.hold(.7)
        self.hold(.5, left_z=left_z)
        self.hold(.3)
        self.hold(.5, right_z=right_z)
        return self.hold(.3)

    def practice(self):
        self.hold(.1)
        self.hold(0, left_z=1.4)
        self.hold(.15)
        return self.hold(0, right_z=1.4)

    def running(self):
        self.calibrate()
        self.practice()
        return self.hold(2.3)


def test_guidance_runs_all_stages_before_official_round(skeleton):
    d = Driver(skeleton)
    assert d.hold(.2).guidance.stage == "HOLD_GUARD"
    assert d.hold(.5).guidance.stage == "REACH_LEFT"
    assert d.hold(.5, left_z=1.4).guidance.stage == "RETURN_LEFT"
    assert d.hold(.3).guidance.stage == "REACH_RIGHT"
    assert d.hold(.5, right_z=1.4).guidance.stage == "RETURN_RIGHT"
    assert d.hold(.3).guidance.stage == "PRACTICE_LEFT"
    assert d.practice().guidance.stage == "COUNTDOWN"
    assert d.hold(1).guidance.stage == "COUNTDOWN"
    assert d.hold(1.2).guidance.stage == "RUNNING"


def test_different_reaches_generate_personalized_fixed_targets(skeleton):
    a, b = Driver(skeleton), Driver(skeleton)
    state_a = a.calibrate(left_z=1.4)
    state_b = b.calibrate(left_z=1.3)
    assert state_a.targets[0].center == pytest.approx((-.2, .04, 1.49))
    assert state_b.targets[0].center == pytest.approx((-.2, .04, 1.405))
    shifted = a.hold(.1, shift=.2)
    assert shifted.targets[0].center == pytest.approx((-.2, .04, 1.49))


def test_pause_and_tracking_gap_do_not_complete_hold(skeleton):
    d = Driver(skeleton)
    d.hold(.4)
    d.sim.set_paused(True)
    d.hold(1)
    d.sim.set_paused(False)
    assert d.hold(.2).guidance.stage == "HOLD_GUARD"
    assert d.hold(.5).guidance.stage == "REACH_LEFT"
    d.t += .4
    assert d.hold(.1, left_z=1.4).guidance.stage == "REACH_LEFT"


def test_shoulder_drift_resets_current_reach_sample(skeleton):
    d = Driver(skeleton)
    d.hold(.7)
    assert d.hold(.5, left_z=1.4, shift=.1).guidance.stage == "REACH_LEFT"
    assert d.state.guidance.message_code == "restore_position"
    assert d.hold(.2, left_z=1.4).guidance.stage == "REACH_LEFT"
    assert d.hold(.2, left_z=1.4).guidance.stage == "RETURN_LEFT"


@pytest.mark.parametrize("config", [
    AppConfig(fist_offset_m=0, smoothing_tau_s=0, target_reach_ratio=.3),
    AppConfig(fist_offset_m=0, smoothing_tau_s=0, min_depth_m=1.7),
])
def test_guard_overlap_and_out_of_depth_targets_are_rejected(skeleton, config):
    d = Driver(skeleton, config)
    if config.min_depth_m >= 1.7:
        d.hold(.7)
        state = d.hold(.5, left_z=1.4)
    else:
        state = d.calibrate()
    assert not state.targets
    assert state.guidance.message_code in ("reach_too_small", "adjust_distance")


def test_target_outside_measured_comfortable_path_is_rejected(skeleton):
    d = Driver(skeleton, AppConfig(fist_offset_m=0, smoothing_tau_s=0, target_height_m=1.))
    state = d.calibrate()
    assert state.guidance.stage == "REACH_LEFT"
    assert state.guidance.message_code == "target_unreachable"
    assert state.guidance.profile is None
    assert not state.targets
    assert d.hold(.1).guidance.message_code == "target_unreachable"


def test_lateral_reach_cannot_calibrate_an_unmeasured_straight_target(skeleton):
    def angled(t, **pose):
        frame = skeleton(t, **pose)
        for hand in ("left", "right"):
            name = f"{hand}_wrist"
            joint = frame.joints[name]
            if joint.position is not None and joint.position[2] < 1.6:
                frame.joints[name] = Joint3D(joint.position + (0.5, 0, 0), joint.confidence)
        return frame
    state = Driver(angled).calibrate()
    assert state.guidance.stage == "REACH_LEFT"
    assert state.guidance.message_code == "target_unreachable"
    assert not state.targets


def test_practice_hits_never_increment_official_score(skeleton):
    d = Driver(skeleton)
    d.calibrate()
    state = d.practice()
    assert (state.score, state.hits, state.remaining_s) == (0, 0, 60)
    assert not state.events
    assert state.guidance.stage == "COUNTDOWN"


@pytest.mark.parametrize("missing", ["left_shoulder", "right_elbow"])
def test_missing_shoulder_cannot_score_or_consume_guided_round_time(skeleton, missing):
    d = Driver(skeleton)
    d.running()
    before = d.state.remaining_s
    state = d.hold(.3, left_z=1.4, invalid=missing)
    assert state.score == 0 and state.remaining_s == pytest.approx(before)
    assert state.status == "TRACKING LOST"
    assert d.hold(.1, left_z=1.4).score == 0
    d.hold(.1)
    assert d.hold(0, left_z=1.4).score == 10


def test_missing_inactive_elbow_suppresses_scoring_and_time(skeleton):
    d = Driver(skeleton)
    d.running()
    state = d.hold(0, left_z=1.4, invalid="right_elbow")
    assert state.score == 0 and state.status == "TRACKING LOST"


def test_resume_requires_guard_not_extended_fist(skeleton):
    d = Driver(skeleton)
    d.running()
    d.sim.set_paused(True)
    d.hold(.2, left_z=1.4)
    d.sim.set_paused(False)
    assert d.hold(.1, left_z=1.4).score == 0
    d.hold(.1)
    assert d.hold(0, left_z=1.4).score == 10


def test_interrupted_countdown_restarts_after_guard(skeleton):
    d = Driver(skeleton)
    d.calibrate()
    d.practice()
    d.hold(1)
    d.sim.set_paused(True)
    d.hold(2)
    d.sim.set_paused(False)
    assert d.hold(1.2).guidance.stage == "COUNTDOWN"
    assert d.hold(1).guidance.stage == "RUNNING"


def test_guided_targets_and_fists_are_the_same_collision_proxies(skeleton):
    d = Driver(skeleton)
    d.running()
    hit = d.hold(0, left_z=1.4)
    assert hit.fists["left"].position == pytest.approx((-.2, .04, 1.4))
    assert (hit.hits, hit.score) == (1, 10)


def test_guided_demo_and_v2_replay_are_deterministic(tmp_path):
    from depthstrike.recording import PoseRecorder, PoseReplaySource
    from depthstrike.sources import DemoPoseSource
    config = AppConfig()
    path = tmp_path/"guided.jsonl"
    sim = BoxingSimulation(config)
    actual, stages = [], set()
    with DemoPoseSource(config=config, total_frames=600) as source, PoseRecorder(path, config) as recorder:
        while (frame := source.read()) is not None:
            state = sim.step(frame)
            stages.add(state.guidance.stage)
            actual.extend(state.events)
            recorder.write(frame, state.events)
    assert {"PRACTICE_LEFT", "PRACTICE_RIGHT", "COUNTDOWN", "RUNNING"} <= stages
    assert sim.hits >= 3
    replayed = []
    with PoseReplaySource(path) as source:
        replay = BoxingSimulation(source.config)
        while (frame := source.read()) is not None:
            replayed.extend(replay.step(frame).events)
    assert replayed == actual
