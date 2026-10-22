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
    assert events[0].timestamp_s == pytest.approx(.2425)
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
        {"cue_id": 0, "hand": "left", "at_s": .25, "start_s": .1, "end_s": .35, "offset": [0, .1, -.38/.6]},
        {"cue_id": 1, "hand": "left", "at_s": .5, "start_s": .35, "end_s": .7, "offset": [0, .1, -.58/.6]}]
    round_, config = setup_round(data)
    events = drive(round_, config, skeleton, [(0, 1.85, 0, True), (.1, 1.85, 0, True), (.3, 1.62, 0, True),
                            (.5, 1.42, 0, True), (.7, 1.85, 0, True)])
    assert len(events) == 1
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
    assert events[0].timestamp_s == pytest.approx(10.2425)
    assert round_.report()["trials"][0]["hit_time_s"] == pytest.approx(.2425)


def test_activation_does_not_invent_an_entry_for_an_already_overlapping_fist(skeleton):
    from depthstrike.boxing import PunchState
    round_, config = setup_round()
    p = profile()
    events = []
    for t, z in ((0, 1.85), (.1, 1.62), (.25, 1.5), (.4, 1.45)):
        frame = skeleton(t, left_z=z)
        fists = {h: frame.joints[f"{h}_wrist"] for h in ("left", "right")}
        states = {h: PunchState("ATTACKING", 1, None, fists[h].position, t > 0) for h in fists}
        events.extend(round_.update(frame, fists, states, t, True, p))
    assert not events


def test_missing_interval_cannot_bridge_a_fast_hit(skeleton):
    round_, config = setup_round()
    events = drive(round_, config, skeleton, [(0, 1.85, 0, True), (.1, 1.85, 0, True), (.5, 1.45, 0, True),
                  (.65, 1.85, 0, True), (.8, 1.85, 0, True), (1., 1.85, 0, True)])
    assert not events
    assert round_.report()["trials"][0]["outcome"] == "unobserved"
