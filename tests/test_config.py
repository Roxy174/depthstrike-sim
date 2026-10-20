import json

import pytest


def test_defaults_and_explicit_override(tmp_path):
    from depthstrike.config import load_config
    assert load_config().hand_radius_m == .06
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"round_duration_s": 10}), encoding="utf-8")
    assert load_config(path).round_duration_s == 10


@pytest.mark.parametrize("values", [
    {"hand_radius_m": -1}, {"round_duration_s": float("nan")},
    {"confidence_threshold": 2}, {"unknown": 10}, {"depth_window_px": 2.5},
    {"min_depth_m": 4, "max_depth_m": 1}, {"smoothing_tau_s": -1},
])
def test_invalid_configuration_rejected(tmp_path, values):
    from depthstrike.config import load_config
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(values), encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(path)


def test_missing_configuration_not_silently_defaulted(tmp_path):
    from depthstrike.config import load_config
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "missing.json")
