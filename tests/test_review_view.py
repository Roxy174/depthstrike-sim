from copy import deepcopy
import json

import numpy as np
import pytest

from test_challenge_round import setup_round, drive


def make_report(skeleton):
    round_, config = setup_round()
    drive(round_, config, skeleton, [(0, 1.85, .2, True), (.1, 1.85, .2, True), (.25, 1.65, .2, True),
          (.4, 1.45, .2, True), (.55, 1.85, .2, True), (.7, 1.85, .2, True), (.85, 1.85, .2, True), (1., 1.85, .2, True)])
    return round_.report({"evidence": "synthetic"})


def test_review_renders_original_motion_and_corrected_segment(skeleton):
    from depthstrike.review_view import render_review
    pytest.importorskip("cv2")
    report = make_report(skeleton)
    first, last = render_review(report, 0, 0.), render_review(report, 0, 1.)
    assert first.shape == (820, 1120, 3) and first.dtype == np.uint8
    assert np.count_nonzero(first != last) > 100
    no_correction = deepcopy(report)
    no_correction["trials"][0]["counterfactual"] = None
    assert np.count_nonzero(last != render_review(no_correction, 0, 1.)) > 100


def test_review_loader_rejects_nonfinite_motion_and_invalid_identity(tmp_path, skeleton):
    from depthstrike.review_view import load_review
    report = make_report(skeleton)
    path = tmp_path/"review.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    assert load_review(path)["hits"] == 0
    report["trials"][0]["trajectory"][0]["position_m"][0] = float("nan")
    path.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(ValueError): load_review(path)
    report = make_report(skeleton)
    report["trials"][0]["cue_id"] = 999
    path.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(ValueError): load_review(path)


def test_unmapped_partial_review_is_visible_without_fabricated_geometry(skeleton):
    from depthstrike.review_view import render_review
    round_, _ = setup_round()
    assert render_review(round_.report(), 0).shape == (820, 1120, 3)
