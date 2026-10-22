"""Local motion authoring, an analytic challenge example, and review browsing."""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys

from .boxing import BoxingSimulation
from .cli import main as play_main
from .config import AppConfig
from .motion_authoring import author_recording
from .motion_challenge import file_sha256, write_json_exclusive
from .recording import PoseRecorder, PoseReplaySource
from .sources import DemoPoseSource
from .types import DepthStrikeError, Joint3D


def create_demo(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    config = AppConfig()
    author = directory/"author.jsonl"
    with DemoPoseSource(config=config, total_frames=600) as source, PoseRecorder(author, config, source.describe()) as recorder:
        while (frame := source.read()) is not None:
            recorder.write(frame, ())
    recipe = author_recording(author)
    write_json_exclusive(directory/"challenge.json", recipe.to_dict())
    probe = BoxingSimulation(config)
    metadata = {"source": "synthetic challenge player", "evidence": "synthetic", "author_sha256": file_sha256(author),
                "perturbation": "wrist/elbow displacement (0.22, 0, 0.04) m on cues 2, 5 and 8; analytic demonstration only"}
    with PoseReplaySource(author) as source, PoseRecorder(directory/"player.jsonl", config, metadata) as recorder:
        while (frame := source.read()) is not None:
            state = probe.step(frame)
            if state.guidance.stage == "RUNNING":
                elapsed = config.round_duration_s-state.remaining_s
                cue = next((c for c in recipe.cues if c.start_s <= elapsed < c.end_s), None)
                if cue is not None and cue.cue_id % 3 == 1:
                    joints = dict(frame.joints)
                    for part in ("wrist", "elbow"):
                        name = f"{cue.hand}_{part}"
                        joint = joints[name]
                        joints[name] = Joint3D(joint.position + (.22, 0, .04), joint.confidence)
                    frame = replace(frame, joints=joints)
            recorder.write(frame, ())
    return recipe


def main(argv=None):
    parser = argparse.ArgumentParser(description="DepthStrike Motion Studio local prototype")
    commands = parser.add_subparsers(dest="command", required=True)
    author = commands.add_parser("author", help="derive a challenge from a guided pose recording")
    author.add_argument("--input", type=Path, required=True)
    author.add_argument("--output", type=Path, required=True)
    demo = commands.add_parser("demo", help="create and play a new synthetic example directory")
    demo.add_argument("--output", type=Path, required=True)
    demo.add_argument("--headless", action="store_true")
    demo.add_argument("--view", choices=("overlay", "dual"), default="overlay")
    review = commands.add_parser("review", help="browse a saved motion review or export one image")
    review.add_argument("--input", type=Path, required=True)
    review.add_argument("--trial", type=int, default=1, help="1-based cue number")
    review.add_argument("--image", type=Path, help="new PNG; no window is opened")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)
    try:
        if args.command == "author":
            if args.output.exists(): raise FileExistsError(f"Challenge output already exists: {args.output}")
            recipe = author_recording(args.input)
            write_json_exclusive(args.output, recipe.to_dict())
            print(json.dumps({"challenge": str(args.output), "cues": len(recipe.cues), "evidence": recipe.raw["source"]["evidence"]}))
            return 0
        if args.command == "review":
            from .review_view import load_review, export_image, show_review
            report = load_review(args.input)
            if not 1 <= args.trial <= len(report["trials"]): raise ValueError("--trial is outside the report's cue range")
            if args.image:
                export_image(report, args.trial-1, args.image)
            else:
                show_review(report, args.trial-1)
            return 0
        create_demo(args.output)
        report_path = args.output/"review.json"
        options = ["--source", "replay", "--input", str(args.output/"player.jsonl"),
                   "--challenge", str(args.output/"challenge.json"), "--review-output", str(report_path), "--view", args.view]
        if args.headless: options.append("--headless")
        result = play_main(options)
        if result == 0 and not args.headless:
            from .review_view import load_review, show_review
            report = load_review(report_path)
            selected = next((n for n, row in enumerate(report["trials"]) if row["counterfactual"]), 0)
            show_review(report, selected)
        return result
    except (OSError, ValueError, RuntimeError, TypeError, DepthStrikeError) as exc:
        print(f"DepthStrike studio: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
