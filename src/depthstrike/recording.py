"""Versioned, streaming replay formats. No pickle and no silent overwrites."""
from dataclasses import asdict
import json
from pathlib import Path

import numpy as np

from . import __version__
from .config import AppConfig
from .types import HitEvent, Intrinsics, Joint3D, RGBDFrame, SkeletonFrame

COORDINATES = "camera_x_right_y_down_z_forward"
ACTIONS = {"pause", "reset", "tracking_lost"}


def _dump(value):
    return json.dumps(value, allow_nan=False, separators=(",", ":"))+"\n"


def _header(kind, config, metadata):
    return {"format": kind, "version": 1, "unit": "m", "timestamp_unit": "s",
            "coordinates": COORDINATES, "program_version": __version__,
            "config": config.to_dict(), "metadata": metadata or {}}


class _Resource:
    def __enter__(self): return self
    def __exit__(self, *args): self.close()


class _Reader(_Resource):
    def __init__(self, path, kind):
        self.stream = Path(path).open("r", encoding="utf-8")
        self.last_t = -1.
        self.last_id = -1
        self.actions = []
        try:
            header = self._row()
            if (not header or header.get("format") != kind or header.get("version") != 1
                    or header.get("unit") != "m" or header.get("timestamp_unit") != "s"
                    or header.get("coordinates") != COORDINATES):
                raise ValueError("Unsupported recording header, units or format version")
            self.metadata = header.get("metadata", {})
            try:
                if not isinstance(header.get("config"), dict):
                    raise ValueError("Recording config must be a JSON object")
                self.config = AppConfig(**header["config"])
            except TypeError as exc:
                raise ValueError(f"Invalid recording config: {exc}") from exc
        except BaseException:
            self.close()
            raise

    def _row(self):
        line = self.stream.readline(2*1024*1024+1)
        if not line:
            return None
        if len(line) > 2*1024*1024:
            raise ValueError("Recording line too large")
        def invalid(value): raise ValueError(f"Non-finite JSON value {value}")
        try:
            row = json.loads(line, parse_constant=invalid)
            if not isinstance(row, dict): raise ValueError("Expected JSON object")
            return row
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("Corrupt recording JSON line") from exc

    def _identity(self, row):
        try:
            timestamp, frame_id = row["timestamp_s"], row["frame_id"]
            if (isinstance(timestamp, bool) or not isinstance(timestamp, (int, float))
                    or not np.isfinite(timestamp) or timestamp <= self.last_t
                    or type(frame_id) is not int or frame_id <= self.last_id):
                raise ValueError("Recording timestamps and frame ids must increase strictly")
            actions = row.get("actions", [])
            if not isinstance(actions, list) or any(a not in ACTIONS for a in actions):
                raise ValueError("Unsupported replay action")
        except (KeyError, TypeError) as exc:
            raise ValueError("Recording frame identity missing or malformed") from exc
        self.last_t, self.last_id, self.actions = timestamp, frame_id, actions

    def close(self): self.stream.close()


class PoseRecorder(_Resource):
    def __init__(self, path, config, metadata=None):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = path.open("x", encoding="utf-8")
        self.stream.write(_dump(_header("depthstrike.pose", config, metadata)))

    def write(self, frame, events, actions=()):
        self.stream.write(_dump({"frame_id": frame.frame_id, "timestamp_s": frame.timestamp_s,
            "joints": {name: {"position": j.position.tolist() if j.position is not None else None,
                               "confidence": j.confidence} for name, j in frame.joints.items()},
            "events": [asdict(e) for e in events], "actions": list(actions)}))

    def close(self): self.stream.close()


class PoseReplaySource(_Reader):
    def __init__(self, path):
        super().__init__(path, "depthstrike.pose")
        self.last_rgbd = None

    def read(self):
        row = self._row()
        if row is None: return None
        self._identity(row)
        try:
            if not isinstance(row["joints"], dict) or len(row["joints"]) > 100:
                raise ValueError("Invalid joint map")
            joints = {name: Joint3D(j["position"], j["confidence"]) for name, j in row["joints"].items()}
            self.recorded_events = tuple(HitEvent(**e) for e in row.get("events", []))
            return SkeletonFrame(row["frame_id"], row["timestamp_s"], joints)
        except (KeyError, TypeError) as exc:
            raise ValueError("Malformed pose frame") from exc


class RGBDRecorder(_Resource):
    def __init__(self, directory, config, metadata=None):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=False)
        self.stream = (self.directory/"frames.jsonl").open("x", encoding="utf-8")
        self.stream.write(_dump(_header("depthstrike.rgbd", config, metadata)))
        self.index = 0

    def write(self, frame, actions=()):
        if frame.deproject is not None:
            raise ValueError("Custom deprojection cannot be serialized; retain explicit supported calibration")
        if not np.isfinite(frame.depth_m).all():
            raise ValueError("Recording depth contains non-finite values; encode invalid depth as zero")
        prefix = f"{self.index:06d}"
        color, depth = prefix+"_rgb.npy", prefix+"_depth.npy"
        # Fresh exclusive directory, unique indices; never overwrite user files.
        for name, array in ((color, frame.color_rgb), (depth, frame.depth_m)):
            with (self.directory/name).open("xb") as stream:
                np.save(stream, array, allow_pickle=False)
        self.stream.write(_dump({"frame_id": frame.frame_id, "timestamp_s": frame.timestamp_s,
            "intrinsics": asdict(frame.intrinsics), "color": color, "depth": depth,
            "actions": list(actions)}))
        self.index += 1

    def close(self): self.stream.close()


class RGBDReplaySource(_Reader):
    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        super().__init__(self.directory/"frames.jsonl", "depthstrike.rgbd")

    def _array(self, name):
        if not isinstance(name, str): raise ValueError("Invalid array filename")
        candidate = (self.directory/name).resolve()
        if not candidate.is_relative_to(self.directory) or candidate.suffix != ".npy":
            raise ValueError("Array path escapes recording directory")
        try:
            # Limit allocations before loading headers/data from untrusted recordings.
            if candidate.stat().st_size > 128*1024*1024:
                raise ValueError("Recording array too large")
            return np.load(candidate, allow_pickle=False)
        except (OSError, TypeError) as exc:
            raise ValueError(f"Cannot load recording array: {name}") from exc

    def read(self):
        row = self._row()
        if row is None: return None
        self._identity(row)
        try:
            values = dict(row["intrinsics"])
            values["distortion"] = tuple(values.get("distortion", ()))
            intrinsics = Intrinsics(**values)
            color, depth = self._array(row["color"]), self._array(row["depth"])
            if not np.isfinite(depth).all():
                raise ValueError("Recording depth contains non-finite values")
            return RGBDFrame(row["frame_id"], row["timestamp_s"], color, depth, intrinsics)
        except (KeyError, TypeError) as exc:
            raise ValueError("Malformed RGB-D frame") from exc
