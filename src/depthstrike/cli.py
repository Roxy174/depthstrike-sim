"""Public command line for demo, live RGB-D, and two distinct replay levels."""
import argparse
from contextlib import ExitStack, redirect_stdout
from dataclasses import asdict, replace
import json
from pathlib import Path
import sys

from . import __version__
from .app import run_session
from .astra_capture import AstraSource
from .boxing import BoxingSimulation
from .camera_selection import AutoCameraSource, discover_cameras
from .config import load_config
from .metrics import StageMetrics
from .motion_challenge import ChallengeRecipe, file_sha256, write_json_exclusive
from .opencv_capture import OpenCVSource
from .recording import PoseRecorder, PoseReplaySource, RGBDRecorder, RGBDReplaySource
from .sources import CameraPoseSource, DemoPoseSource
from .types import DepthStrikeError
from .visualization import NullView, SceneView

LIVE_SOURCES = ("camera", "gemini-camera", "auto-camera", "opencv-camera", "astra-camera")


def _pose_model_config(config, variant):
    return replace(config, model_path=f'models/pose_landmarker_{variant}.task') if variant else config


def _opencv_experience_origin(metadata):
    seen = set()
    while isinstance(metadata, dict) and id(metadata) not in seen:
        if metadata.get("capture_backend") == "opencv_obsensor": return True
        seen.add(id(metadata))
        metadata = metadata.get("recording_metadata")
    return False


def _astra_experience_origin(metadata):
    seen = set()
    while isinstance(metadata, dict) and id(metadata) not in seen:
        if metadata.get("capture_backend") == "openni2_astra_uvc": return True
        seen.add(id(metadata))
        metadata = metadata.get("recording_metadata")
    return False


def _gemini_origin(metadata):
    seen = set()
    while isinstance(metadata, dict) and id(metadata) not in seen:
        if metadata.get("capture_backend") == "orbbec_sdk_gemini2": return True
        seen.add(id(metadata))
        metadata = metadata.get("recording_metadata")
    return False


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="DepthStrike: RGB-D skeleton-guided target boxing")
    parser.add_argument("--source", choices=("demo", *LIVE_SOURCES, "replay", "rgbd-replay"), default="demo")
    parser.add_argument("--list-cameras", action="store_true", help="list supported connected cameras without starting streams")
    parser.add_argument("--openni-dir", type=Path, help="Astra OpenNI2.dll directory; default: .cache/openni2")
    parser.add_argument("--input", type=Path, help="pose JSONL file or RGB-D recording directory")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--view", choices=("overlay", "dual"), default="overlay")
    parser.add_argument("--sound", action="store_true", help="optional asynchronous Windows hit sound")
    parser.add_argument("--frames", type=int, help="positive frame limit; headless default: 600")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--pose-model", choices=('lite', 'full', 'heavy'), help="override the pose model for live or RGB-D input")
    parser.add_argument("--record", type=Path, help="new trajectory JSONL file")
    parser.add_argument("--record-rgbd", type=Path, help="new RGB-D directory; contains identifiable images")
    parser.add_argument("--metrics", type=Path, help="new software-stage timing JSON; never sensor latency")
    parser.add_argument("--challenge", type=Path, help="body-relative Motion Studio challenge JSON")
    parser.add_argument("--review-output", type=Path, help="new per-cue motion review JSON; requires --challenge")
    try:
        args = parser.parse_args(argv)
        if args.list_cameras:
            if (args.source != "demo" or any((args.input, args.config, args.record, args.record_rgbd,
                    args.metrics, args.challenge, args.review_output, args.openni_dir,
                    args.headless, args.sound, args.pose_model)) or args.frames is not None or args.view != "overlay"):
                parser.error("--list-cameras is a standalone command")
            with redirect_stdout(sys.stderr):
                inventory = discover_cameras()
            print(json.dumps(inventory, ensure_ascii=False, allow_nan=False))
            return 0
        if args.headless and args.sound: parser.error("--sound requires a display; remove --headless or --sound")
        if args.pose_model and args.source not in (*LIVE_SOURCES, 'rgbd-replay'):
            parser.error('--pose-model requires a camera or rgbd-replay; pose replay contains no images')
        outputs = [p.resolve() for p in (args.record, args.record_rgbd, args.metrics, args.review_output) if p is not None]
        if len(outputs) != len(set(outputs)): parser.error("Output paths must differ")
        if args.review_output and not args.challenge: parser.error("--review-output requires --challenge")
        if args.challenge and args.challenge.resolve() in outputs: parser.error("Challenge input and output paths must differ")
        if args.frames is not None and args.frames <= 0: parser.error("--frames must be positive")
        if args.source in ("replay", "rgbd-replay") and args.input is None: parser.error("--input required for replay")
        if args.source in (*LIVE_SOURCES, "demo") and args.input is not None: parser.error("--input only applies to replay")
        if args.openni_dir is not None and args.source not in ("astra-camera", "auto-camera"): parser.error("--openni-dir only applies to astra-camera or auto-camera")
        if args.record_rgbd and args.source not in (*LIVE_SOURCES, "rgbd-replay"): parser.error("--record-rgbd requires a camera or rgbd-replay")
    except SystemExit as exc:
        return int(exc.code)
    metrics = None
    summary = None
    simulation = None
    source = None
    source_metadata = {}
    metadata = {"source": args.source, "status": "partial", "evidence": "unverified"}
    code = 0
    try:
        if args.review_output is not None and args.review_output.exists():
            raise FileExistsError(f"Review output already exists: {args.review_output}")
        challenge = ChallengeRecipe.load(args.challenge) if args.challenge else None
        if args.metrics is not None:
            if args.metrics.exists(): raise FileExistsError(f"Metrics output already exists: {args.metrics}")
            metrics = StageMetrics()
        config = _pose_model_config(load_config(args.config), args.pose_model)
        metadata["config"] = config.to_dict()
        with ExitStack() as setup:
            if args.source == "demo": source = setup.enter_context(DemoPoseSource(config=config))
            elif args.source == "replay":
                source = setup.enter_context(PoseReplaySource(args.input))
                if args.config is None: config = source.config
            elif args.source == "rgbd-replay":
                capture = setup.enter_context(RGBDReplaySource(args.input))
                if args.config is None: config = capture.config
                config = _pose_model_config(config, args.pose_model)
                source = setup.enter_context(CameraPoseSource(config, capture=capture, metrics=metrics))
            elif args.source == "opencv-camera":
                capture = setup.enter_context(OpenCVSource(config))
                source = setup.enter_context(CameraPoseSource(config, capture=capture, metrics=metrics))
            elif args.source == "astra-camera":
                capture = setup.enter_context(AstraSource(config, args.openni_dir))
                source = setup.enter_context(CameraPoseSource(config, capture=capture, metrics=metrics))
            elif args.source == "auto-camera":
                with redirect_stdout(sys.stderr):
                    capture = setup.enter_context(AutoCameraSource(config, args.openni_dir))
                    source = setup.enter_context(CameraPoseSource(config, capture=capture, metrics=metrics))
            else:
                with redirect_stdout(sys.stderr):
                    source = setup.enter_context(CameraPoseSource(config, metrics=metrics))
            simulation = BoxingSimulation(config, challenge=challenge)
            source_metadata = source.describe() if hasattr(source, "describe") else getattr(source, "metadata", {"source": args.source})
            view_mode = source_metadata.get("selected_camera_source", args.source)
            if _opencv_experience_origin(source_metadata):
                view_mode = "opencv-experience"
                print("OpenCV EXPERIENCE: host read time; RGB-D synchronization unverified; approximate pinhole geometry. Not a precision or latency evaluation.", file=sys.stderr)
            elif _astra_experience_origin(source_metadata):
                view_mode = "astra-experience"
                print("ASTRA EXPERIENCE: independent OpenNI depth and UVC color; host read time; exposure synchronization and spatial accuracy unverified.", file=sys.stderr)
            elif _gemini_origin(source_metadata):
                view_mode = "gemini-camera"
                print("CAMERA: Gemini 2; SDK frame synchronization, software depth-to-color alignment and device timestamps.", file=sys.stderr)
            view = setup.enter_context(SceneView(config, view_mode, layout=args.view, sound=args.sound)) if not args.headless else NullView()
            metadata.update({"config": config.to_dict(), "source_metadata": source_metadata,
                             "evidence": source_metadata.get("evidence", "unverified"),
                             "program_version": __version__})
            recorder = setup.enter_context(PoseRecorder(args.record, config, source_metadata)) if args.record else None
            rgbd_recorder = setup.enter_context(RGBDRecorder(args.record_rgbd, config, source_metadata)) if args.record_rgbd else None
            # From here run_session owns resources, including every failure path.
            setup.pop_all()
            summary = run_session(source, simulation, view, recorder,
                args.frames if args.frames is not None else (600 if args.headless and args.source in ("demo", *LIVE_SOURCES) else None),
                rgbd_recorder=rgbd_recorder, realtime=not args.headless and args.source not in LIVE_SOURCES, metrics=metrics)
        metadata.update(status="ok", summary=asdict(summary))
    except KeyboardInterrupt:
        print("DepthStrike interrupted; resources closed.", file=sys.stderr)
        code = 130
    except (DepthStrikeError, OSError, ValueError, RuntimeError) as exc:
        print(f"DepthStrike: {exc}", file=sys.stderr)
        code = 1
        metadata["error"] = str(exc)
    finally:
        if args.review_output is not None and simulation is not None and simulation.challenge is not None:
            try:
                report = simulation.challenge.report(source_metadata)
                report.update(termination=summary.termination if summary else "error",
                              execution_status="ok" if code == 0 else "partial")
                if args.input is not None: report["input_sha256"] = file_sha256(args.input/"frames.jsonl" if args.source == "rgbd-replay" else args.input)
                if "error" in metadata: report["error"] = metadata["error"]
                write_json_exclusive(args.review_output, report)
            except (OSError, ValueError, RuntimeError) as exc:
                print(f"DepthStrike review: {exc}", file=sys.stderr)
                if code == 0: code = 1
        if metrics is not None:
            try:
                if callable(getattr(source, 'quality_summary', None)):
                    metadata['tracking_quality'] = source.quality_summary()
                if simulation is not None:
                    metadata['tracked_hand_quality'] = simulation.tracker.quality_summary()
                metrics.write_exclusive(args.metrics, metadata)
            except (OSError, ValueError, RuntimeError) as exc:
                print(f"DepthStrike metrics: {exc}", file=sys.stderr)
                if code == 0: code = 1
    if code == 0:
        print(json.dumps({"source": args.source, **asdict(summary)}, allow_nan=False))
    return code
