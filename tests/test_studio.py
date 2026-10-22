import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

from test_motion_authoring import record_demo


def test_challenge_cli_exports_complete_review_with_source_provenance(tmp_path, capsys):
    from depthstrike.cli import main
    from depthstrike.motion_authoring import author_recording
    from depthstrike.motion_challenge import write_json_exclusive
    source, recipe, report = tmp_path/"author.jsonl", tmp_path/"challenge.json", tmp_path/"review.json"
    record_demo(source)
    write_json_exclusive(recipe, author_recording(source).to_dict())
    assert main(["--source", "replay", "--input", str(source), "--challenge", str(recipe),
                 "--review-output", str(report), "--headless"]) == 0
    result = json.loads(report.read_text(encoding="utf-8"))
    assert result["status"] == "complete"
    assert result["evidence"] == "synthetic"
    assert result["hits"] == 9 and len(result["trials"]) == 9
    assert all(row["outcome"] == "hit" for row in result["trials"])
    assert len(result["input_sha256"]) == 64
    assert result["termination"] == "round_finished"


def test_review_output_is_rejected_before_input_setup(tmp_path, capsys):
    from depthstrike.cli import main
    output = tmp_path/"existing.json"
    output.write_bytes(b"preserved report")
    assert main(["--challenge", str(tmp_path/"missing.json"), "--review-output", str(output), "--headless"]) != 0
    assert output.read_bytes() == b"preserved report"
    assert "already exists" in capsys.readouterr().err


def test_partial_session_does_not_grade_future_windows_as_misses(tmp_path, capsys):
    from depthstrike.cli import main
    from depthstrike.motion_authoring import author_recording
    from depthstrike.motion_challenge import write_json_exclusive
    source, recipe, report = tmp_path/"source.jsonl", tmp_path/"recipe.json", tmp_path/"report.json"
    record_demo(source)
    write_json_exclusive(recipe, author_recording(source).to_dict())
    assert main(["--source", "replay", "--input", str(source), "--challenge", str(recipe),
                 "--review-output", str(report), "--headless", "--frames", "275"]) == 0
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["status"] == "partial"
    assert all(row["outcome"] == "incomplete" for row in data["trials"])
    assert all(row["counterfactual"] is None for row in data["trials"])


def test_studio_demo_has_hits_misses_and_verified_local_corrections(tmp_path, capsys):
    from depthstrike.studio import main
    directory = tmp_path/"studio"
    assert main(["demo", "--output", str(directory), "--headless"]) == 0
    report = json.loads((directory/"review.json").read_text(encoding="utf-8"))
    outcomes = [row["outcome"] for row in report["trials"]]
    assert report["status"] == "complete"
    assert outcomes.count("hit") == 6 and outcomes.count("miss") == 3
    corrections = [row["counterfactual"] for row in report["trials"] if row["outcome"] == "miss"]
    assert all(c and c["verified_contact"] for c in corrections)
    for row in report["trials"]:
        if row["counterfactual"]:
            hand = row["hand"]
            shoulder = np.array(report["player_calibration"]["reference_shoulders_m"][hand])
            reach = report["player_calibration"]["comfortable_extensions_m"][hand]
            assert all(np.linalg.norm(np.array(p)-shoulder) <= reach+1e-9
                       for p in row["counterfactual"]["segment_m"])
    assert report["evidence"] == "synthetic"
    assert main(["demo", "--output", str(directory), "--headless"]) != 0
    assert json.loads((directory/"review.json").read_text(encoding="utf-8")) == report


def test_author_cli_and_review_image_are_explicit_and_non_overwriting(tmp_path, capsys):
    from depthstrike.studio import main
    directory = tmp_path/"example"
    assert main(["demo", "--output", str(directory), "--headless"]) == 0
    authored = tmp_path/"authored.json"
    assert main(["author", "--input", str(directory/"author.jsonl"), "--output", str(authored)]) == 0
    assert len(json.loads(authored.read_text(encoding="utf-8"))["cues"]) == 9
    image = tmp_path/"review.png"
    assert main(["review", "--input", str(directory/"review.json"), "--trial", "2", "--image", str(image)]) == 0
    assert image.read_bytes().startswith(b"\x89PNG")
    before = image.read_bytes()
    assert main(["review", "--input", str(directory/"review.json"), "--image", str(image)]) != 0
    assert image.read_bytes() == before


def test_headless_studio_does_not_import_devices_or_graphics(tmp_path):
    code = """import sys
from depthstrike.studio import main
assert main(['demo', '--output', sys.argv[1], '--headless']) == 0
assert not any(n in sys.modules for n in ('cv2','open3d','mediapipe','pyorbbecsdk'))
"""
    result = subprocess.run([sys.executable, "-c", code, str(tmp_path/"demo")], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
