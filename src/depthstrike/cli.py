"""Public command line for demo, live RGB-D, and two distinct replay levels."""
import argparse
from contextlib import ExitStack, redirect_stdout
from dataclasses import asdict
import json
from pathlib import Path
import sys

from . import __version__
from .app import run_session
from .boxing import BoxingSimulation
from .config import load_config
from .metrics import StageMetrics
from .recording import PoseRecorder, PoseReplaySource, RGBDRecorder, RGBDReplaySource
from .sources import CameraPoseSource, DemoPoseSource
from .types import DepthStrikeError
from .visualization import NullView, SceneView


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="DepthStrike: RGB-D skeleton-guided target boxing")
    parser.add_argument("--source", choices=("demo", "camera", "replay", "rgbd-replay"), default="demo")
    parser.add_argument("--input", type=Path, help="pose JSONL file or RGB-D recording directory")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--view", choices=("overlay", "dual"), default="overlay")
    parser.add_argument("--sound", action="store_true", help="optional asynchronous Windows hit sound")
    parser.add_argument("--frames", type=int, help="positive frame limit; headless default: 600")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--record", type=Path, help="new trajectory JSONL file")
    parser.add_argument("--record-rgbd", type=Path, help="new RGB-D directory; contains identifiable images")
    parser.add_argument("--metrics", type=Path, help="new software-stage timing JSON; never sensor latency")
    try:
        args = parser.parse_args(argv)
        if args.headless and args.sound: parser.error("--sound requires a display; remove --headless or --sound")
        outputs = [p.resolve() for p in (args.record, args.record_rgbd, args.metrics) if p is not None]
        if len(outputs) != len(set(outputs)): parser.error("Output paths must differ")
        if args.frames is not None and args.frames <= 0: parser.error("--frames must be positive")
        if args.source in ("replay", "rgbd-replay") and args.input is None: parser.error("--input required for replay")
        if args.source in ("camera", "demo") and args.input is not None: parser.error("--input only applies to replay")
        if args.record_rgbd and args.source not in ("camera", "rgbd-replay"): parser.error("--record-rgbd requires camera or rgbd-replay")
    except SystemExit as exc:
        return int(exc.code)
    metrics = None
    summary = None
    metadata = {"source": args.source, "status": "partial", "evidence": "unverified"}
    code = 0
    try:
        if args.metrics is not None:
            if args.metrics.exists(): raise FileExistsError(f"Metrics output already exists: {args.metrics}")
            metrics = StageMetrics()
        config = load_config(args.config)
        metadata["config"] = config.to_dict()
        with ExitStack() as setup:
            if args.source == "demo": source = setup.enter_context(DemoPoseSource(config=config))
            elif args.source == "replay":
                source = setup.enter_context(PoseReplaySource(args.input))
                if args.config is None: config = source.config
            elif args.source == "rgbd-replay":
                capture = setup.enter_context(RGBDReplaySource(args.input))
                if args.config is None: config = capture.config
                source = setup.enter_context(CameraPoseSource(config, capture=capture, metrics=metrics))
            else:
                with redirect_stdout(sys.stderr):
                    source = setup.enter_context(CameraPoseSource(config, metrics=metrics))
            view = setup.enter_context(SceneView(config, args.source, layout=args.view, sound=args.sound)) if not args.headless else NullView()
            source_metadata = source.describe() if hasattr(source, "describe") else getattr(source, "metadata", {"source": args.source})
            metadata.update({"config": config.to_dict(), "source_metadata": source_metadata,
                             "evidence": source_metadata.get("evidence", "unverified"),
                             "program_version": __version__})
            recorder = setup.enter_context(PoseRecorder(args.record, config, source_metadata)) if args.record else None
            rgbd_recorder = setup.enter_context(RGBDRecorder(args.record_rgbd, config, source_metadata)) if args.record_rgbd else None
            # From here run_session owns resources, including every failure path.
            setup.pop_all()
            summary = run_session(source, BoxingSimulation(config), view, recorder,
                args.frames if args.frames is not None else (600 if args.headless and args.source in ("demo", "camera") else None),
                rgbd_recorder=rgbd_recorder, realtime=not args.headless and args.source != "camera", metrics=metrics)
        metadata.update(status="ok", summary=asdict(summary))
    except KeyboardInterrupt:
        print("DepthStrike interrupted; resources closed.", file=sys.stderr)
        code = 130
    except (DepthStrikeError, OSError, ValueError, RuntimeError) as exc:
        print(f"DepthStrike: {exc}", file=sys.stderr)
        code = 1
        metadata["error"] = str(exc)
    finally:
        if metrics is not None:
            try:
                metrics.write_exclusive(args.metrics, metadata)
            except (OSError, ValueError, RuntimeError) as exc:
                print(f"DepthStrike metrics: {exc}", file=sys.stderr)
                if code == 0: code = 1
    if code == 0:
        print(json.dumps({"source": args.source, **asdict(summary)}, allow_nan=False))
    return code
