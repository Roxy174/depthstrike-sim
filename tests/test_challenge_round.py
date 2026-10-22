from dataclasses import replace

import pytest

from depthstrike.boxing import BoxingSimulation, PunchTracker
from depthstrike.config import AppConfig
from depthstrike.types import Joint3D
from test_motion_challenge import neutral, profile, recipe_data


def setup_round(data=None):
    from depthstrike.challenge_round import ChallengeRound
    from depthstrike.motion_challenge import ChallengeRecipe
    config = AppConfig(fist_offset_m=0, smoothing_tau_s=0)
    return ChallengeRound(ChallengeRecipe.from_dict(data or recipe_data()), config), config


def drive(round_, config, skeleton, rows):
    p = profile()
    trackers = {h: PunchTracker(config) for h in ("left", "right")}
    events = []
    for t, z, x, valid in rows:
        frame = skeleton(t, left_z=z)
        fists = {h: frame.joints[f"{h}_wrist"] for h in trackers}
        fists["left"] = Joint3D(fists["left"].position + (x, 0, 0), .95) if valid else Joint3D(None)
        states = {h: tracker.update(t, fists[h], frame.joints[f"{h}_shoulder"],
                   guard_extension_m=.19, attack_extension_m=.35, min_travel_m=.08)
                  for h, tracker in trackers.items()}
        events.extend(round_.update(frame, fists, states, t, valid, p))
    return events


def test_cue_hit_uses_continuous_contact_and_completes_at_deadline(skeleton):
    round_, config = setup_round()
    events = drive(round_, config, skeleton, [(0, 1.85, 0, True), (.1, 1.85, 0, True), (.25, 1.65, 0, True),
        (.4, 1.45, 0, True), (.55, 1.85, 0, True), (.7, 1.85, 0, True), (.85, 1.85, 0, True), (1., 1.85, 0, True)])
    assert len(events) == 1 and events[0].target_id == 0
    assert events[0].timestamp_s == pytest.approx(.2875)
    report = round_.report()
    assert report["status"] == "complete" and report["score"] == 10
    assert report["trials"][0]["outcome"] == "hit"
    assert report["trials"][0]["counterfactual"] is None
    assert report["player_calibration"]["reference_shoulders_m"]["left"] == [-.2, 0., 2.]
    assert report["player_calibration"]["comfortable_extensions_m"]["left"] == .6


def test_spatial_miss_contains_a_local_contact_suggestion(skeleton):
    round_, config = setup_round()
    drive(round_, config, skeleton, [(0, 1.85, .2, True), (.1, 1.85, .2, True), (.25, 1.65, .2, True),
        (.4, 1.45, .2, True), (.55, 1.85, .2, True), (.7, 1.85, .2, True), (.85, 1.85, .2, True), (1., 1.85, .2, True)])
    trial = round_.report()["trials"][0]
    assert trial["outcome"] == "miss" and trial["reason"] == "spatial_miss"
    assert trial["surface_gap_m"] == pytest.approx(.06)
    assert trial["counterfactual"]["delta_m"] == pytest.approx((-.061, 0, 0))


def test_slow_motion_is_not_given_a_spatial_fix(skeleton):
    round_, config = setup_round()
    drive(round_, config, skeleton, [(0, 1.85, .2, True), (.15, 1.85, .2, True), (.3, 1.8, .2, True),
          (.45, 1.75, .2, True), (.6, 1.7, .2, True), (.75, 1.65, .2, True), (.9, 1.6, .2, True), (1., 1.55, .2, True)])
    trial = round_.report()["trials"][0]
    assert trial["reason"] == "no_valid_attack"
    assert trial["counterfactual"] is None


def test_interrupted_observation_has_no_counterfactual(skeleton):
    round_, config = setup_round()
    drive(round_, config, skeleton, [(0, 1.85, .2, True), (.1, 1.85, .2, True), (.25, 1.65, .2, True),
          (.4, 1.45, .2, False), (.55, 1.45, .2, True), (.7, 1.85, .2, True), (.85, 1.85, .2, True), (1., 1.85, .2, True)])
    trial = round_.report()["trials"][0]
    assert trial["outcome"] == "unobserved" and trial["counterfactual"] is None


def test_same_attack_cannot_score_two_sequential_cues(skeleton):
    data = recipe_data()
    data["cues"] = [
        {"cue_id": 0, "hand": "left", "at_s": .25, "start_s": .1, "end_s": .35, "offset": [0, .1, -.51/.6]},
        {"cue_id": 1, "hand": "left", "at_s": .5, "start_s": .35, "end_s": .7, "offset": [0, .1, -.72/.6]}]
    round_, config = setup_round(data)
    events = drive(round_, config, skeleton, [(0, 1.85, 0, True), (.1, 1.85, 0, True), (.3, 1.46, 0, True),
                            (.5, 1.31, 0, True), (.7, 1.85, 0, True)])
    assert len(events) == 1 and events[0].target_id == 0
    assert round_.report()["trials"][1]["counterfactual"] is None


def test_eof_before_deadline_remains_partial(skeleton):
    round_, config = setup_round()
    drive(round_, config, skeleton, [(0, 1.85, .2, True), (.1, 1.85, .2, True), (.25, 1.65, .2, True)])
    report = round_.report()
    assert report["status"] == "partial"
    assert report["trials"][0]["outcome"] == "incomplete"
    assert report["trials"][0]["counterfactual"] is None


def test_challenge_game_reuses_guided_setup_and_reset(skeleton):
    from depthstrike.motion_challenge import ChallengeRecipe
    from test_calibration import Driver
    d = Driver(skeleton)
    d.sim = BoxingSimulation(d.config, challenge=ChallengeRecipe.from_dict(recipe_data()))
    d.running()
    state = d.hold(.1)
    assert state.challenge["total"] == 1
    assert state.score == 0 and state.remaining_s <= 1.
    state = d.hold(0, left_z=1.4)
    assert state.hits == 1
    d.sim.reset()
    assert not d.sim.challenge.report()["trials"][0]["observed_segments"]


def test_hit_event_keeps_source_timestamp_while_review_uses_round_time(skeleton):
    round_, config = setup_round()
    p = profile()
    trackers = {h: PunchTracker(config) for h in ("left", "right")}
    events = []
    for elapsed, z in ((0, 1.85), (.1, 1.85), (.25, 1.65), (.4, 1.45)):
        frame = skeleton(10+elapsed, left_z=z)
        fists = {h: frame.joints[f"{h}_wrist"] for h in trackers}
        states = {h: tracker.update(frame.timestamp_s, fists[h], frame.joints[f"{h}_shoulder"],
                  guard_extension_m=.19, attack_extension_m=.35, min_travel_m=.08) for h, tracker in trackers.items()}
        events.extend(round_.update(frame, fists, states, elapsed, True, p))
    assert events[0].timestamp_s == pytest.approx(10.2875)
    assert round_.report()["trials"][0]["hit_time_s"] == pytest.approx(.2875)


def test_activation_does_not_invent_an_entry_for_an_already_overlapping_fist(skeleton):
    from depthstrike.boxing import PunchState
    data = recipe_data()
    data["cues"][0]["offset"][2] = -.8
    round_, config = setup_round(data)
    p = profile()
    events = []
    for t, z in ((0, 1.85), (.1, 1.62), (.25, 1.5), (.4, 1.45)):
        frame = skeleton(t, left_z=z)
        fists = {h: frame.joints[f"{h}_wrist"] for h in ("left", "right")}
        states = {h: PunchState("ATTACKING", 1, None, fists[h].position, t > 0,
                               eligible_from_s=0., eligible_until_s=t) for h in fists}
        events.extend(round_.update(frame, fists, states, t, True, p))
    assert not events


def test_missing_interval_cannot_bridge_a_fast_hit(skeleton):
    round_, config = setup_round()
    events = drive(round_, config, skeleton, [(0, 1.85, 0, True), (.1, 1.85, 0, True), (.5, 1.45, 0, True),
                  (.65, 1.85, 0, True), (.8, 1.85, 0, True), (1., 1.85, 0, True)])
    assert not events
    assert round_.report()["trials"][0]["outcome"] == "unobserved"


@pytest.mark.parametrize("lateral", [0., .2])
def test_future_attack_cannot_score_or_correct_an_expired_window(skeleton, lateral):
    data = recipe_data()
    data["cues"][0].update(start_s=.1, at_s=.13, end_s=.16, offset=[0, .1, -.4/.6])
    round_, config = setup_round(data)
    events = drive(round_, config, skeleton, [(0, 1.85, lateral, True), (.1, 1.85, lateral, True), (.3, 1.45, lateral, True)])
    trial = round_.report()["trials"][0]
    assert not events
    assert trial["reason"] == "no_valid_attack"
    assert trial["counterfactual"] is None


@pytest.mark.parametrize("deadline", [1., .98])
def test_final_window_completes_at_the_configured_round_limit(skeleton, deadline):
    from depthstrike.motion_challenge import ChallengeRecipe
    from test_calibration import Driver
    data = recipe_data()
    data["cues"][0]["end_s"] = deadline
    config = AppConfig(fist_offset_m=0, smoothing_tau_s=0, round_duration_s=1.)
    d = Driver(skeleton, config)
    d.sim = BoxingSimulation(config, challenge=ChallengeRecipe.from_dict(data))
    d.running()
    for _ in range(30):
        if d.hold(0).status == "FINISHED": break
    report = d.sim.challenge.report()
    assert d.state.status == "FINISHED"
    assert report["status"] == "complete"
    assert report["trials"][0]["outcome"] != "incomplete"
    assert not report["trials"][0]["interrupted"]


def test_punch_state_exposes_interpolated_eligibility_not_entire_sample(skeleton):
    tracker = PunchTracker(AppConfig(fist_offset_m=0, smoothing_tau_s=0))
    for t, z in ((0, 1.85), (.1, 1.85), (.3, 1.45)):
        frame = skeleton(t, left_z=z)
        state = tracker.update(t, frame.joints["left_wrist"], frame.joints["left_shoulder"],
                               guard_extension_m=.19, attack_extension_m=.35, min_travel_m=.08)
    assert state.eligible_from_s == pytest.approx(.2)
    assert state.eligible_until_s == pytest.approx(.3)


def test_punch_state_preserves_only_the_observed_prefix_before_timeout(skeleton):
    tracker = PunchTracker(AppConfig(fist_offset_m=0, smoothing_tau_s=0, max_attack_duration_s=.1))
    for t, z in ((0, 1.85), (.1, 1.85), (.2, 1.55), (.35, 1.4)):
        frame = skeleton(t, left_z=z)
        state = tracker.update(t, frame.joints["left_wrist"], frame.joints["left_shoulder"])
    assert not state.can_hit
    assert state.eligible_from_s == pytest.approx(.2)
    assert state.eligible_until_s == pytest.approx(.3)
