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
    assert main(["--source", "demo", "--headless", "--frames", "180"]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["frames"] == 180 and summary["hits"] >= 3
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
