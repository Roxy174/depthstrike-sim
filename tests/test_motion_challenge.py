from copy import deepcopy
from dataclasses import replace

import numpy as np
import pytest

from depthstrike.calibration import CalibrationProfile
from depthstrike.config import AppConfig
from depthstrike.types import Joint3D


def recipe_data():
    return {"format": "depthstrike.challenge", "version": 1, "unit": "m", "timestamp_unit": "s",
            "coordinates": "camera_x_right_y_down_z_forward", "radius_m": .08,
            "source": {"evidence": "synthetic", "sha256": "a" * 64},
            "source_config": AppConfig(fist_offset_m=0).to_dict(),
            "author_scale": {"shoulder_width_m": .4, "comfortable_extensions_m": {"left": .6, "right": .6}},
            "cues": [{"cue_id": 0, "hand": "left", "at_s": .6, "start_s": .2, "end_s": 1.,
                      "offset": [0., .1, -.8]}]}


def profile(width=.4, reach=.6, z=2.):
    return CalibrationProfile(
        {h: np.array((x, 0., z)) for h, x in (("left", -width/2), ("right", width/2))},
        {h: .15 for h in ("left", "right")}, {h: reach for h in ("left", "right")},
        {h: .19 for h in ("left", "right")}, {h: .35 for h in ("left", "right")},
        {h: .08 for h in ("left", "right")}, {})


def neutral(p):
    return {h: Joint3D(s + (0, .04, -.15), 1) for h, s in p.reference_shoulders.items()}


def test_recipe_mapping_preserves_relative_depth_for_a_different_body():
    from depthstrike.motion_challenge import ChallengeRecipe
    recipe = ChallengeRecipe.from_dict(recipe_data())
    p = profile(width=.5, reach=.4, z=2.2)
    targets = recipe.map_targets(p, AppConfig(), neutral(p))
    assert targets[0].center == pytest.approx((-.25, .05, 1.88))
    assert recipe.to_dict() == recipe_data()


@pytest.mark.parametrize("mutation", ["nan", "overlap", "duplicate", "unknown_hand", "too_many", "version_bool", "bad_hash", "too_far", "bad_scale"])
def test_malformed_challenge_is_rejected(mutation):
    from depthstrike.motion_challenge import ChallengeRecipe
    data = deepcopy(recipe_data())
    if mutation == "nan": data["cues"][0]["offset"][0] = float("nan")
    elif mutation == "overlap": data["cues"].append({**data["cues"][0], "cue_id": 1})
    elif mutation == "duplicate": data["cues"].append({**data["cues"][0], "start_s": 1., "at_s": 1.4, "end_s": 1.8})
    elif mutation == "unknown_hand": data["cues"][0]["hand"] = "foot"
    elif mutation == "too_many": data["cues"] *= 33
    elif mutation == "version_bool": data["version"] = True
    elif mutation == "bad_hash": data["source"]["sha256"] = "not-a-digest"
    elif mutation == "too_far": data["cues"][0]["end_s"] = 121
    elif mutation == "bad_scale": data["author_scale"]["shoulder_width_m"] = 0
    with pytest.raises(ValueError): ChallengeRecipe.from_dict(data)


@pytest.mark.parametrize("offset", [[0, .1, -4], [4, 0, -.8], [0, .1, -.25]])
def test_mapping_rejects_depth_unreachable_and_guard_overlap(offset):
    from depthstrike.motion_challenge import ChallengeRecipe
    data = recipe_data()
    data["cues"][0]["offset"] = offset
    p = profile()
    with pytest.raises(ValueError):
        ChallengeRecipe.from_dict(data).map_targets(p, AppConfig(), neutral(p))


def test_challenge_file_roundtrip_is_exclusive(tmp_path):
    from depthstrike.motion_challenge import ChallengeRecipe, write_json_exclusive
    path = tmp_path / "challenge.json"
    write_json_exclusive(path, recipe_data())
    assert ChallengeRecipe.load(path).to_dict() == recipe_data()
    before = path.read_bytes()
    with pytest.raises(FileExistsError): write_json_exclusive(path, {})
    assert path.read_bytes() == before


def test_local_counterfactual_is_hand_derived_and_rechecked_for_contact():
    from depthstrike.counterfactual import analyze_segment
    from depthstrike.geometry import segment_sphere_intersection
    from depthstrike.types import Target
    target = Target(0, "left", np.array((0., 0., 1.5)), .08, True)
    result = analyze_segment((.3, 0, 2), (.3, 0, 1), target, .06, (0, 0, 2), 1.2, .25, 5.)
    assert result["closest_point_m"] == pytest.approx((.3, 0, 1.5))
    assert result["surface_gap_m"] == pytest.approx(.16)
    suggestion = result["counterfactual"]
    assert suggestion["delta_m"] == pytest.approx((-.161, 0, 0))
    assert suggestion["scope"] == "local_geometry_only"
    assert segment_sphere_intersection(*suggestion["segment_m"], target.center, .14) is not None


def test_counterfactual_does_not_propose_unreachable_or_already_hit_segments():
    from depthstrike.counterfactual import analyze_segment
    from depthstrike.types import Target
    target = Target(0, "left", np.array((0., 0., 1.5)), .08, True)
    assert analyze_segment((0, 0, 2), (0, 0, 1), target, .06, (0, 0, 2), 1.2, .25, 5.)["counterfactual"] is None
    assert analyze_segment((.3, 0, 2), (.3, 0, 1), target, .06, (0, 0, 2), .3, .25, 5.)["counterfactual"] is None
