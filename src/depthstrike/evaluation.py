"""Controlled interaction comparisons with independent, explicit event labels."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np

from . import __version__
from .boxing import PunchTracker
from .calibration import valid_body
from .config import AppConfig
from .geometry import segment_sphere_intersection
from .interaction import estimate_hand
from .recording import COORDINATES, PoseReplaySource
from .tracking import SkeletonTracker
from .types import Intrinsics, SkeletonFrame, Target, vector3

METHODS = ("2d_entry", "3d_discrete_entry", "3d_swept_entry", "3d_swept_punch")


def _number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be finite and numeric")
    return float(value)


def _interval(row):
    if not isinstance(row, dict): raise ValueError("Interval must be an object")
    start, end = _number(row.get("start_s"), "start_s"), _number(row.get("end_s"), "end_s")
    if not 0 <= start < end: raise ValueError("Interval times require 0 <= start_s < end_s")
    return start, end


def _inside(t, windows):
    return any(w["start_s"] <= t <= w["end_s"] for w in windows)


def _filtered_labels(labels, ignore):
    for row in ignore: _interval(row)
    result = []
    for row in labels:
        start, end = _interval(row)
        contained = any(w["start_s"] <= start and end <= w["end_s"] for w in ignore)
        intersects = any(start <= w["end_s"] and w["start_s"] <= end for w in ignore)
        if intersects and not contained: raise ValueError("Label partially overlaps an ignore interval")
        if not contained: result.append(row)
    return result


def match_events(predictions, labels, ignore_windows):
    labels = _filtered_labels(labels, ignore_windows)
    used = set()
    tp = fp = duplicates = prediction_count = 0
    for prediction in sorted(predictions, key=lambda p: (p["timestamp_s"], p["hand"], p["target_id"])):
        t = _number(prediction["timestamp_s"], "prediction timestamp")
        if _inside(t, ignore_windows): continue
        prediction_count += 1
        candidates = [n for n, label in enumerate(labels)
                      if label["hand"] == prediction["hand"] and label["target_id"] == prediction["target_id"]
                      and label["start_s"] <= t <= label["end_s"]]
        unmatched = next((n for n in candidates if n not in used), None)
        if unmatched is not None:
            used.add(unmatched)
            tp += 1
        else:
            fp += 1
            duplicates += int(bool(candidates))
    return {"tp": tp, "fp": fp, "fn": len(labels)-tp, "duplicates": duplicates,
            "prediction_count": prediction_count, "label_count": len(labels),
            "precision": tp/(tp+fp) if tp+fp else None,
            "recall": tp/len(labels) if labels else None}


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


@dataclass(frozen=True)
class EvaluationManifest:
    evidence: str
    label_basis: str
    intrinsics: Intrinsics
    targets: tuple[Target, ...]
    active_schedule: tuple[dict, ...]
    expected_windows: tuple[dict, ...]
    ignore_windows: tuple[dict, ...]
    punch_thresholds: dict
    raw: dict

    @classmethod
    def from_dict(cls, data):
        try:
            if (not isinstance(data, dict) or type(data.get("schema_version")) is not int
                    or data["schema_version"] != 1 or data.get("unit") != "m"
                    or data.get("timestamp_unit") != "s" or data.get("coordinates") != COORDINATES):
                raise ValueError("Invalid label schema, coordinates or units")
            if data.get("evidence") not in ("synthetic", "recorded"):
                raise ValueError("Label evidence must be synthetic or recorded")
            if not isinstance(data.get("label_basis"), str) or not data["label_basis"].strip():
                raise ValueError("Independent label_basis is required")
            i_values = dict(data["intrinsics"])
            if any(type(i_values.get(n)) is not int for n in ("width", "height")):
                raise ValueError("Image dimensions must be integers")
            for n in ("fx", "fy", "cx", "cy"): _number(i_values.get(n), n)
            i_values["distortion"] = tuple(i_values.get("distortion", ()))
            intrinsics = Intrinsics(**i_values)
            if (intrinsics.distortion_model not in ("none", "brown_conrady")
                    or intrinsics.distortion_model == "none" and any(abs(c) > 1e-12 for c in intrinsics.distortion)
                    or intrinsics.distortion_model == "brown_conrady" and len(intrinsics.distortion) not in (4, 5, 8)):
                raise ValueError("Unsupported evaluation distortion model")
            if not isinstance(data.get("targets"), list) or not 0 < len(data["targets"]) <= 128:
                raise ValueError("Labels require 1..128 fixed targets")
            targets = []
            for row in data["targets"]:
                if (not isinstance(row, dict) or type(row.get("target_id")) is not int
                        or row["target_id"] < 0 or row.get("hand") not in ("left", "right")):
                    raise ValueError("Invalid target identity")
                center, radius = vector3(row["center"]), _number(row["radius"], "radius")
                if radius <= 0 or center[2] <= radius: raise ValueError("Invalid target position/radius")
                targets.append(Target(row["target_id"], row["hand"], center, radius, True))
            by_id = {t.target_id: t for t in targets}
            if len(by_id) != len(targets): raise ValueError("Target ids must be unique")
            schedules, labels, ignore = [], [], []
            for field, dest in (("active_schedule", schedules), ("expected_windows", labels), ("ignore_windows", ignore)):
                rows = data.get(field)
                if not isinstance(rows, list) or len(rows) > 100000: raise ValueError(f"Invalid {field}")
                for row in rows:
                    start, end = _interval(row)
                    normalized = {"start_s": start, "end_s": end}
                    if field != "ignore_windows":
                        target_id, hand = row.get("target_id"), row.get("hand")
                        if (type(target_id) is not int or target_id not in by_id or by_id[target_id].hand != hand):
                            raise ValueError("Interval references an unknown target or wrong hand")
                        normalized.update(hand=hand, target_id=target_id)
                    dest.append(normalized)
            schedules.sort(key=lambda r: r["start_s"])
            if not schedules: raise ValueError("An active target schedule is required")
            if any(b["start_s"] < a["end_s"] for a, b in zip(schedules, schedules[1:])):
                raise ValueError("Active schedule must not overlap")
            for n, a in enumerate(labels):
                if any(a["hand"] == b["hand"] and a["target_id"] == b["target_id"]
                       and a["start_s"] <= b["end_s"] and b["start_s"] <= a["end_s"] for b in labels[n+1:]):
                    raise ValueError("Same-hand target label windows overlap or share an endpoint")
                if not any(s["hand"] == a["hand"] and s["target_id"] == a["target_id"]
                           and s["start_s"] <= a["start_s"] and a["end_s"] < s["end_s"] for s in schedules):
                    raise ValueError("Expected label window is not inside its active schedule")
            _filtered_labels(labels, ignore)
            thresholds = data.get("punch_thresholds", {})
            if not isinstance(thresholds, dict) or set(thresholds) - {"left", "right"}:
                raise ValueError("Invalid punch_thresholds")
            for values in thresholds.values():
                if not isinstance(values, dict) or set(values) != {"guard_extension_m", "attack_extension_m", "min_travel_m"}:
                    raise ValueError("Each hand threshold requires guard, attack and min_travel_m")
                guard = _number(values["guard_extension_m"], "guard_extension_m")
                attack = _number(values["attack_extension_m"], "attack_extension_m")
                travel = _number(values["min_travel_m"], "min_travel_m")
                if not 0 <= guard < attack or travel <= 0: raise ValueError("Invalid hand thresholds")
            # Normalize through JSON to avoid mutable aliases and reject non-JSON/nonfinite extras.
            raw = json.loads(_canonical(data))
            return cls(data["evidence"], data["label_basis"], intrinsics, tuple(targets), tuple(schedules),
                       tuple(labels), tuple(ignore), thresholds, raw)
        except (KeyError, TypeError, AttributeError, OverflowError) as exc:
            raise ValueError(f"Malformed evaluation manifest: {exc}") from exc

    def active(self, timestamp):
        return next(((s["hand"], s["target_id"]) for s in self.active_schedule
                     if s["start_s"] <= timestamp < s["end_s"]), None)


def _project(position, i):
    x, y, z = position
    if z <= 0: return None
    if i.distortion_model == "none":
        return np.array((i.fx*x/z+i.cx, i.fy*y/z+i.cy))
    try:
        import cv2
    except ImportError as exc:
        raise ValueError("Brown-Conrady evaluation requires the pinned OpenCV dependency") from exc
    matrix = np.array([[i.fx, 0, i.cx], [0, i.fy, i.cy], [0, 0, 1.]])
    points, _ = cv2.projectPoints(np.asarray(position, dtype=float).reshape(1, 3), np.zeros(3), np.zeros(3), matrix, np.asarray(i.distortion))
    return points.reshape(2)


def _inside_2d(fist, target, config, intrinsics):
    a, b = _project(fist, intrinsics), _project(target.center, intrinsics)
    if a is None or b is None or not np.isfinite((a, b)).all(): return False
    distance = np.linalg.norm((a-b) / np.array((intrinsics.fx, intrinsics.fy)))
    return bool(distance <= config.hand_radius_m / fist[2] + target.radius / target.center[2])


def evaluate_frames(frames, manifest: EvaluationManifest, config: AppConfig) -> dict:
    for target in manifest.targets:
        if not config.min_depth_m <= target.center[2] - target.radius < target.center[2] + target.radius <= config.max_depth_m:
            raise ValueError("Evaluation target is outside configured depth range")
    tracker = SkeletonTracker(config)
    punches = {h: PunchTracker(config) for h in ("left", "right")}
    predictions = {name: [] for name in METHODS}
    history = {}
    previous_points = {}
    proxy_sources = {}
    previous_t = None
    settled = set()
    total_frames = evaluated_frames = invalid_frames = 0
    last_t, last_id = -1., -1
    paused = False
    input_hash = hashlib.sha256()
    schedule_hash = hashlib.sha256(_canonical(list(manifest.active_schedule))).hexdigest()

    def invalidate():
        nonlocal previous_t
        tracker.reset()
        for punch in punches.values(): punch.reset()
        history.clear()
        previous_points.clear()
        proxy_sources.clear()
        previous_t = None

    for item in frames:
        frame, actions = (item, ()) if isinstance(item, SkeletonFrame) else item
        if frame.timestamp_s <= last_t or frame.frame_id <= last_id:
            raise ValueError("Evaluation frame ids and timestamps must increase strictly")
        last_t, last_id = frame.timestamp_s, frame.frame_id
        total_frames += 1
        input_hash.update(_canonical({"frame_id": frame.frame_id, "timestamp_s": frame.timestamp_s,
            "joints": {n: {"position": j.position.tolist() if j.position is not None else None,
                            "confidence": j.confidence, "invalid_reason": j.invalid_reason,
                            "provenance": j.provenance, "depth_quality": j.depth_quality, "age_s": j.age_s}
                       for n, j in frame.joints.items()},
            "actions": list(actions)}))
        for action in actions:
            if action == "pause": paused = not paused
            elif action == "reset": paused = False
            elif action != "tracking_lost": raise ValueError("Unsupported evaluation control action")
            invalidate()
        t = frame.timestamp_s
        if paused or _inside(t, manifest.ignore_windows):
            invalidate()
            continue
        evaluated_frames += 1
        if previous_t is not None and (t - previous_t > config.max_track_gap_s + 1e-9 or
                any(previous_t <= w["end_s"] and w["start_s"] <= t for w in manifest.ignore_windows)):
            invalidate()
        filtered = tracker.update(frame)
        fists = {h: estimate_hand(filtered.joints, h, config) for h in punches}
        current_sources = {h: j.provenance for h, j in fists.items()}
        if proxy_sources and current_sources != proxy_sources:
            invalidate()
        proxy_sources.update(current_sources)
        if not valid_body(filtered, fists, config) or any(not config.min_depth_m <= j.position[2] <= config.max_depth_m
                for j in fists.values() if j.position is not None):
            invalid_frames += 1
            invalidate()
            continue
        states = {h: punch.update(t, fists[h], filtered.joints.get(f"{h}_shoulder"),
                                  **manifest.punch_thresholds.get(h, {})) for h, punch in punches.items()}
        for target in manifest.targets:
            hand = target.hand
            point = fists[hand].position
            inside3 = bool(np.linalg.norm(point - target.center) <= config.hand_radius_m + target.radius + 1e-12)
            inside2 = _inside_2d(point, target, config, manifest.intrinsics)
            pair = (hand, target.target_id)
            old3, old2 = history.get(("3d", pair)), history.get(("2d", pair))
            fraction = None
            if old3 is False and previous_t is not None:
                fraction = segment_sphere_intersection(previous_points[hand], point, target.center,
                                                      config.hand_radius_m + target.radius)
            candidates = {
                "2d_entry": t if old2 is False and inside2 else None,
                "3d_discrete_entry": t if old3 is False and inside3 else None,
                "3d_swept_entry": previous_t + fraction*(t-previous_t) if fraction is not None else None,
            }
            punch = states[hand]
            if punch.can_hit and (hand, punch.attack_id) not in settled:
                candidates["3d_swept_punch"] = candidates["3d_swept_entry"]
            for method, hit_t in candidates.items():
                # Every target retains geometry history even while inactive. Its
                # candidate time, not the surrounding samples, decides activity.
                if hit_t is not None and manifest.active(hit_t) == pair:
                    predictions[method].append({"timestamp_s": float(hit_t), "hand": hand,
                        "target_id": target.target_id, "frame_id": frame.frame_id})
                    if method == "3d_swept_punch": settled.add((hand, punch.attack_id))
            history[("3d", pair)], history[("2d", pair)] = inside3, inside2
        previous_t = t
        previous_points = {h: j.position.copy() for h, j in fists.items()}
    if not total_frames: raise ValueError("Cannot evaluate an empty recording: no frames")
    methods = {name: {**match_events(events, manifest.expected_windows, manifest.ignore_windows),
                     "predictions": events, "schedule_sha256": schedule_hash,
                     "parameters": {**config.to_dict(), "punch_thresholds": manifest.punch_thresholds,
                                    "contact_baseline": "entry_not_per_frame"}}
               for name, events in predictions.items()}
    return {"evidence": manifest.evidence, "label_basis": manifest.label_basis,
            "input_sha256": input_hash.hexdigest(), "labels_sha256": hashlib.sha256(_canonical(manifest.raw)).hexdigest(),
            "sample_count": total_frames, "evaluated_frame_count": evaluated_frames,
            "tracking_invalid_count": invalid_frames,
            "tracking_invalid_ratio": invalid_frames/evaluated_frames if evaluated_frames else None,
            "label_count": len(_filtered_labels(manifest.expected_windows, manifest.ignore_windows)),
            "methods": methods}


def _load_manifest(path):
    if Path(path).stat().st_size > 4*1024*1024: raise ValueError("Label manifest is too large")
    return EvaluationManifest.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def _file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b""): digest.update(chunk)
    return digest.hexdigest()


def evaluate_recording(input_path: Path, manifest_path: Path) -> dict:
    manifest = _load_manifest(manifest_path)
    with PoseReplaySource(input_path) as source:
        if source.metadata.get("evidence") == "synthetic" and manifest.evidence != "synthetic":
            raise ValueError("Synthetic recording cannot be relabeled as recorded evidence")
        def samples():
            while (frame := source.read()) is not None:
                yield frame, tuple(source.actions)
        result = evaluate_frames(samples(), manifest, source.config)
    result["input_sha256"] = _file_hash(input_path)
    return {"format": "depthstrike.evaluation", "version": 1, "program_version": __version__,
            "scope": "pose interaction comparison, not RGB-D perception accuracy", **result}


def evaluate_synthetic_suite() -> dict:
    from .evaluation_scenarios import build_scenarios
    scenarios = [{"name": name, **evaluate_frames(frames, EvaluationManifest.from_dict(labels), config)}
                 for name, frames, labels, config in build_scenarios()]
    aggregate = {}
    for name in METHODS:
        counts = {key: sum(s["methods"][name][key] for s in scenarios)
                  for key in ("tp", "fp", "fn", "duplicates", "prediction_count", "label_count")}
        tp, fp, fn = counts["tp"], counts["fp"], counts["fn"]
        aggregate[name] = {**counts, "precision": tp/(tp+fp) if tp+fp else None, "recall": tp/(tp+fn) if tp+fn else None}
    return {"format": "depthstrike.evaluation", "version": 1, "program_version": __version__,
            "evidence": "synthetic", "scope": "analytic cases, not human accuracy or camera latency",
            "scenarios": scenarios, "aggregate": aggregate}


def main(argv=None):
    parser = argparse.ArgumentParser(description="DepthStrike controlled interaction comparison")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--suite", choices=("synthetic",))
    group.add_argument("--input", type=Path)
    parser.add_argument("--labels", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    try:
        args = parser.parse_args(argv)
        if bool(args.labels) != bool(args.input): parser.error("--input and --labels are required together")
    except SystemExit as exc:
        return int(exc.code)
    try:
        if args.output.exists(): raise FileExistsError(f"Evaluation output already exists: {args.output}")
        result = evaluate_synthetic_suite() if args.suite else evaluate_recording(args.input, args.labels)
        content = json.dumps(result, allow_nan=False, indent=2) + "\n"
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream: stream.write(content)
        print(json.dumps({"output": str(args.output), "evidence": result["evidence"]}))
        return 0
    except (OSError, ValueError, RuntimeError, TypeError) as exc:
        print(f"DepthStrike evaluation: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
