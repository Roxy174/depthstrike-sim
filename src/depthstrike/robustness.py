"""Deterministic fault injection. Synthetic software evidence, never camera accuracy."""
import argparse
from dataclasses import replace
import json
from pathlib import Path

import numpy as np

from .boxing import BoxingSimulation
from .config import AppConfig
from .fusion import estimate_joint
from .motion_challenge import write_json_exclusive
from .sources import DemoPoseSource
from .types import Intrinsics, Joint3D, Landmark, RGBDFrame

CASES = ("clean", "left_wrist_loss", "inactive_elbow_loss", "swapped_wrists", "timestamp_regression")


def inject_fault(frame, case):
    if case not in CASES: raise ValueError("Unknown fault case")
    if not 11 <= frame.timestamp_s < 12: return frame
    joints = dict(frame.joints)
    if case in ("left_wrist_loss", "inactive_elbow_loss"):
        name = "left_wrist" if case == "left_wrist_loss" else "right_elbow"
        joints[name] = Joint3D(None, invalid_reason="synthetic_occlusion")
    elif case == "swapped_wrists":
        joints["left_wrist"], joints["right_wrist"] = joints["right_wrist"], joints["left_wrist"]
    elif case == "timestamp_regression" and frame.frame_id == 330:
        return replace(frame, timestamp_s=frame.timestamp_s-.1)
    return replace(frame, joints=joints)


def build_report():
    policies = {"baseline": AppConfig(), "adaptive": AppConfig(partial_tracking=True, filter_mode="one_euro",
                fist_mode="hand", preview_targets=True, fusion_mode="masked")}
    sessions = []
    for policy, config in policies.items():
        for case in CASES:
            sim = BoxingSimulation(config)
            lost = predicted = frames = 0
            fault_stages = set()
            with DemoPoseSource(config=config, total_frames=600) as source:
                while (raw := source.read()) is not None:
                    state = sim.step(inject_fault(raw, case))
                    lost += not all(j.is_observed for j in state.skeleton.joints.values())
                    predicted += bool(state.display_joints)
                    frames += 1
                    if 11 <= raw.timestamp_s < 12 and case != "clean":
                        fault_stages.add(state.guidance.stage)
            sessions.append(dict(policy=policy, case=case, frames=frames, hits=sim.hits,
                                 unobserved_frames=lost, predicted_frames=predicted, fault_stages=sorted(fault_stages)))
    fusion = {}
    i = Intrinsics(21, 21, 50, 50, 10, 10)
    for mode in ("conservative", "masked"):
        config = AppConfig(fusion_mode=mode)
        recovered = rejected = 0
        for n in range(30):
            depth = np.full((21, 21), 2., np.float32)
            depth[10, 10] = 0
            f = RGBDFrame(n, n/30, np.zeros((21, 21, 3), np.uint8), depth, i)
            options = dict(mask=np.ones((21, 21)), previous=Joint3D((0, 0, 2), .95))
            recovered += estimate_joint(Landmark(10/21, 10/21, .95), f, config, **options).is_observed
            options["previous"] = Joint3D((0, 0, 1), .95)
            rejected += not estimate_joint(Landmark(10/21, 10/21, .95), f, config, **options).is_observed
        fusion[mode] = dict(recovered_holes=recovered, background_rejections=rejected, trials=30)
    return dict(evidence="synthetic", sessions=sessions, fusion=fusion,
                limitations=["Hand-picked analytic faults; not real occlusion or localization accuracy.",
                             "Session hit counts are observations, not ground-truth accuracy scores.",
                             "No identity recovery model is claimed for swapped wrists."])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--image", type=Path, help="optional synthetic HUD preview PNG")
    args = parser.parse_args(argv)
    try:
        for path in (args.output, args.image):
            if path is not None and path.exists(): raise FileExistsError(f"Output exists: {path}")
        if args.image is not None and args.image.resolve() == args.output.resolve():
            raise ValueError("Output and image paths must differ")
        report = build_report()
        if args.image:
            import cv2
            from .visualization import render_hud
            config = AppConfig(partial_tracking=True, preview_targets=True, filter_mode="one_euro")
            sim = BoxingSimulation(config)
            with DemoPoseSource(config=config, total_frames=332) as source:
                while (raw := source.read()) is not None:
                    state = sim.step(inject_fault(raw, "left_wrist_loss"))
            image = render_hud(state, None, config, mode="synthetic robustness")
            ok, encoded = cv2.imencode(".png", image)
            if not ok: raise ValueError("PNG encoding failed")
            args.image.parent.mkdir(parents=True, exist_ok=True)
            with args.image.open("xb") as stream: stream.write(encoded.tobytes())
        write_json_exclusive(args.output, report)
        print(json.dumps(report, allow_nan=False))
        return 0
    except (OSError, ValueError, ImportError) as exc:
        parser.exit(1, f"Robustness report failed: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
