import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


def test_invalid_arguments_return_nonzero(capsys):
    from depthstrike.cli import main
    assert main(["--source", "replay"]) != 0
    assert "input" in capsys.readouterr().err.lower()
    assert main(["--frames", "0"]) != 0


def test_finite_headless_demo_has_hits(capsys):
    from depthstrike.cli import main
    assert main(["--source", "demo", "--headless", "--frames", "600"]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["frames"] == 600 and summary["hits"] >= 3
    assert summary["source"] == "demo"


def test_headless_does_not_import_sdk_or_graphics():
    code = "from depthstrike.cli import main; import sys; code=main(['--source','demo','--headless','--frames','30']); assert 'pyorbbecsdk' not in sys.modules; assert 'mediapipe' not in sys.modules; assert 'open3d' not in sys.modules; raise SystemExit(code)"
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr


def test_missing_display_has_headless_guidance(monkeypatch, capsys):
    from depthstrike.cli import main
    monkeypatch.setenv("DEPTHSTRIKE_NO_DISPLAY", "1")
    assert main(["--frames", "1"]) != 0
    assert "headless" in capsys.readouterr().err


def command(*args):
    return subprocess.run([sys.executable, "-m", "depthstrike", *map(str, args)],
                          capture_output=True, text=True, timeout=30)


def test_subprocess_demo_record_and_replay(tmp_path):
    original, reproduced = tmp_path/"original.jsonl", tmp_path/"reproduced.jsonl"
    config = tmp_path/"legacy.json"
    config.write_text(json.dumps({"interaction_mode": "legacy"}))
    result = command("--source", "demo", "--headless", "--frames", 240, "--record", original, "--config", config)
    assert result.returncode == 0, result.stderr
    replay = command("--source", "replay", "--input", original, "--headless", "--record", reproduced)
    assert replay.returncode == 0, replay.stderr
    a, b = json.loads(result.stdout), json.loads(replay.stdout)
    assert (a["frames"], a["hits"], a["score"]) == (240, 6, 60)
    assert (b["frames"], b["hits"], b["score"]) == (240, 6, 60)
    event_rows = lambda p: [json.loads(x)["events"] for x in p.read_text().splitlines()[1:]]
    assert event_rows(original) == event_rows(reproduced)


def test_supplied_fixture_has_hand_checked_result():
    result = command("--source", "replay", "--input", "tests/fixtures/straight_punches.jsonl", "--headless")
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["frames"] == 4 and summary["score"] == 20 and summary["hits"] == 2


def test_malformed_header_configuration_reports_error_without_traceback(tmp_path):
    path = tmp_path/"bad.jsonl"
    header = json.loads(Path("tests/fixtures/straight_punches.jsonl").read_text().splitlines()[0])
    header["config"] = []
    path.write_text(json.dumps(header)+"\n")
    result = command("--source", "replay", "--input", path, "--headless")
    assert result.returncode != 0
    assert "Traceback" not in result.stderr
    assert "config" in result.stderr.lower()


def test_camera_unavailable_never_reports_demo_success(monkeypatch, capsys):
    from depthstrike import cli
    from depthstrike.types import DepthStrikeError
    def unavailable(*args): raise DepthStrikeError("No Gemini camera: connect USB 3")
    monkeypatch.setattr(cli, "CameraPoseSource", unavailable)
    assert cli.main(["--source", "camera", "--headless", "--frames", "1"]) != 0
    output = capsys.readouterr()
    assert not output.out and "USB" in output.err


def test_replay_runs_to_eof_unless_explicitly_limited(tmp_path):
    path = tmp_path/"long.jsonl"
    result = command("--source", "demo", "--headless", "--frames", 650, "--record", path)
    assert result.returncode == 0, result.stderr
    replay = command("--source", "replay", "--input", path, "--headless")
    assert replay.returncode == 0, replay.stderr
    assert json.loads(replay.stdout)["frames"] == 650
