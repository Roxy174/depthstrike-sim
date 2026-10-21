import json
from types import SimpleNamespace

import pytest

from depthstrike.config import AppConfig


class Clock:
    def __init__(self): self.now = 0.
    def __call__(self): return self.now
    def advance(self, duration): self.now += duration


def test_software_stage_duration_uses_injected_monotonic_clock():
    from depthstrike.metrics import StageMetrics
    clock = Clock()
    metrics = StageMetrics(clock=clock)
    with metrics.measure("read"):
        clock.advance(.012)
    stage = metrics.snapshot()["stages"]["read"]
    assert stage["p50_s"] == pytest.approx(.012)
    assert stage["p95_s"] == pytest.approx(.012)
    assert stage["total_count"] == stage["retained_count"] == 1


def test_nested_read_metrics_are_not_summed_twice():
    from depthstrike.metrics import StageMetrics
    clock, metrics = Clock(), None
    metrics = StageMetrics(clock=clock)
    with metrics.measure("read"):
        with metrics.measure("capture"): clock.advance(.004)
        with metrics.measure("pose"): clock.advance(.007)
        with metrics.measure("fusion"): clock.advance(.001)
    stages = metrics.snapshot()["stages"]
    assert stages["read"]["max_s"] == pytest.approx(.012)
    assert stages["pose"]["max_s"] == pytest.approx(.007)
    assert "total_s" not in metrics.snapshot()


def test_metric_samples_are_bounded_and_tail_quantiles_are_labeled():
    from depthstrike.metrics import StageMetrics
    clock = Clock()
    metrics = StageMetrics(clock=clock)
    for _ in range(5000):
        with metrics.measure("read"): clock.advance(.001)
    snap = metrics.snapshot()
    assert snap["sampling"] == "last_n_per_stage"
    assert snap["stages"]["read"]["total_count"] == 5000
    assert snap["stages"]["read"]["retained_count"] == 4096


def test_failed_stage_is_recorded_and_output_is_never_overwritten(tmp_path):
    from depthstrike.metrics import StageMetrics
    clock = Clock()
    metrics = StageMetrics(clock=clock)
    with pytest.raises(RuntimeError):
        with metrics.measure("pose"):
            clock.advance(.003)
            raise RuntimeError("failed inference")
    path = tmp_path/"metrics.json"
    metrics.write_exclusive(path, {"status": "partial"})
    data = json.loads(path.read_text())
    assert data["metadata"]["status"] == "partial"
    assert data["stages"]["pose"]["failed_count"] == 1
    original = path.read_bytes()
    with pytest.raises(FileExistsError): metrics.write_exclusive(path, {})
    assert path.read_bytes() == original


def test_session_reports_frame_time_without_device_clock_subtraction(skeleton):
    from depthstrike.metrics import StageMetrics
    from depthstrike.app import run_session
    from test_app import Input, View, sim
    clock = Clock()
    metrics = StageMetrics(clock=clock)
    class Source(Input):
        def read(self): clock.advance(.01); return super().read()
    class Display(View):
        def render(self, *args): clock.advance(.002); super().render(*args)
    simulation = sim()
    original_step = simulation.step
    def step(frame): clock.advance(.004); return original_step(frame)
    simulation.step = step
    result = run_session(Source([skeleton(10**6)]), simulation, Display(), metrics=metrics)
    assert result.frames == 1
    stages = metrics.snapshot()["stages"]
    assert stages["frame_total"]["max_s"] == pytest.approx(.016)
    assert stages["read"]["total_count"] == 2  # Includes terminal EOF read.


def test_replay_wait_is_not_counted_as_software_frame_time(monkeypatch):
    from depthstrike import app
    from depthstrike.metrics import StageMetrics
    from depthstrike.sources import DemoPoseSource
    from test_app import View, sim
    clock = Clock()
    monkeypatch.setattr(app.time, "sleep", clock.advance)
    metrics = StageMetrics(clock=clock)
    app.run_session(DemoPoseSource(config=sim().config, fps=5, total_frames=3), sim(), View(),
                    realtime=True, clock=clock, metrics=metrics)
    assert clock.now == pytest.approx(.4)
    assert metrics.snapshot()["stages"]["frame_total"]["max_s"] == pytest.approx(0)


def test_cli_writes_partial_metrics_when_source_setup_fails(monkeypatch, tmp_path, capsys):
    from depthstrike import cli
    from depthstrike.types import DepthStrikeError
    def unavailable(*args, **kwargs): raise DepthStrikeError("capture unavailable")
    monkeypatch.setattr(cli, "CameraPoseSource", unavailable)
    path = tmp_path/"partial.json"
    assert cli.main(["--source", "camera", "--headless", "--metrics", str(path)]) == 1
    assert "capture unavailable" in capsys.readouterr().err
    assert json.loads(path.read_text())["metadata"]["status"] == "partial"


def test_existing_metrics_rejected_before_opening_source(monkeypatch, tmp_path, capsys):
    from depthstrike import cli
    path = tmp_path/"existing.json"
    path.write_text("important")
    def forbidden(*args, **kwargs): pytest.fail("Source opened before output validation")
    monkeypatch.setattr(cli, "DemoPoseSource", forbidden)
    assert cli.main(["--headless", "--metrics", str(path)]) == 1
    assert path.read_text() == "important"


def test_metrics_failure_does_not_replace_original_runtime_error(monkeypatch, tmp_path, capsys):
    from depthstrike import cli
    from depthstrike.metrics import StageMetrics
    def unavailable(*args, **kwargs): raise RuntimeError("original capture error")
    def disk_failure(*args, **kwargs): raise OSError("metrics disk error")
    monkeypatch.setattr(cli, "CameraPoseSource", unavailable)
    monkeypatch.setattr(StageMetrics, "write_exclusive", disk_failure)
    assert cli.main(["--source", "camera", "--headless", "--metrics", str(tmp_path/"x.json")]) == 1
    assert "original capture error" in capsys.readouterr().err


def test_metrics_and_record_paths_must_not_alias(tmp_path, capsys):
    from depthstrike.cli import main
    path = tmp_path/"shared.json"
    assert main(["--headless", "--frames", "1", "--metrics", str(path), "--record", str(path)]) != 0
    assert "must differ" in capsys.readouterr().err
    assert not path.exists()


def test_demo_metrics_are_labeled_synthetic(tmp_path, capsys):
    from depthstrike.cli import main
    path = tmp_path/"metrics.json"
    assert main(["--headless", "--frames", "10", "--metrics", str(path)]) == 0
    data = json.loads(path.read_text())
    assert data["metadata"]["evidence"] == "synthetic"
    assert data["metadata"]["summary"]["frames"] == 10
    assert "frame_total" in data["stages"]


def test_camera_source_times_capture_pose_and_fusion(skeleton):
    from depthstrike.metrics import StageMetrics
    from depthstrike.sources import CameraPoseSource
    from test_fusion import rgbd
    clock = Clock()
    metrics = StageMetrics(clock=clock)
    def read(): clock.advance(.004); return rgbd()
    def detect(frame): clock.advance(.009); return {}
    capture = SimpleNamespace(read=read, close=lambda: None)
    pose = SimpleNamespace(detect=detect, close=lambda: None)
    with CameraPoseSource(AppConfig(), capture=capture, estimator=pose, metrics=metrics) as source:
        assert source.read().joints == {}
    stages = metrics.snapshot()["stages"]
    assert stages["capture"]["max_s"] == pytest.approx(.004)
    assert stages["pose"]["max_s"] == pytest.approx(.009)
    assert stages["fusion"]["max_s"] == pytest.approx(0)


def test_partial_session_counts_survive_timeouts_and_runtime_error(skeleton):
    from depthstrike.metrics import StageMetrics
    from depthstrike.app import run_session
    from depthstrike.types import FrameTimeout
    from test_app import Input, View, sim
    metrics = StageMetrics()
    source = Input([skeleton(0), FrameTimeout("late"), RuntimeError("read failed")])
    with pytest.raises(RuntimeError, match="read failed"):
        run_session(source, sim(), View(), metrics=metrics)
    assert metrics.snapshot()["session"] == {"frames": 1, "timeouts": 1}
    assert source.closed


def test_early_quit_keeps_last_completed_frame_counts(skeleton):
    from depthstrike.metrics import StageMetrics
    from depthstrike.app import run_session
    from test_app import Input, View, sim
    metrics = StageMetrics()
    result = run_session(Input([skeleton(0), skeleton(.1)]), sim(),
                         View([[], ["quit"]]), metrics=metrics)
    assert result.termination == "quit"
    assert metrics.snapshot()["session"] == {"frames": 1, "timeouts": 0}
