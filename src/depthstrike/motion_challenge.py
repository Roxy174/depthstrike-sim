"""Versioned body-relative straight-punch challenges, independent of scores."""
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from .config import AppConfig
from .recording import COORDINATES
from .types import Target, vector3


def number(value, name, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    if positive and value <= 0:
        raise ValueError(f"{name} must be positive")
    return float(value)


def write_json_exclusive(path, data):
    content = json.dumps(data, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(content)


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True)
class ChallengeCue:
    cue_id: int
    hand: str
    at_s: float
    start_s: float
    end_s: float
    offset: tuple[float, float, float]


@dataclass(frozen=True)
class ChallengeRecipe:
    cues: tuple[ChallengeCue, ...]
    radius_m: float
    raw: dict

    @classmethod
    def from_dict(cls, data):
        try:
            if (not isinstance(data, dict) or data.get("format") != "depthstrike.challenge"
                    or type(data.get("version")) is not int or data["version"] != 1
                    or data.get("unit") != "m" or data.get("timestamp_unit") != "s"
                    or data.get("coordinates") != COORDINATES):
                raise ValueError("Invalid challenge format, version or coordinates")
            source = data["source"]
            if source["evidence"] not in ("synthetic", "recorded", "unverified"):
                raise ValueError("Invalid challenge evidence")
            digest = source["sha256"]
            if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise ValueError("Challenge source requires a SHA-256 digest")
            AppConfig(**data["source_config"])
            scale = data["author_scale"]
            number(scale["shoulder_width_m"], "shoulder width", positive=True)
            for hand in ("left", "right"):
                number(scale["comfortable_extensions_m"][hand], "comfortable reach", positive=True)
            radius = number(data["radius_m"], "target radius", positive=True)
            if radius > .3: raise ValueError("Challenge target radius exceeds 0.3 m")
            rows = data["cues"]
            if not isinstance(rows, list) or not 1 <= len(rows) <= 32:
                raise ValueError("Challenge requires 1 to 32 cues")
            cues, used, last_end = [], set(), 0.
            for row in rows:
                identity = row["cue_id"]
                if type(identity) is not int or identity < 0 or identity in used or row["hand"] not in ("left", "right"):
                    raise ValueError("Invalid or duplicate challenge cue identity")
                start, at, end = (number(row[n], n) for n in ("start_s", "at_s", "end_s"))
                if not 0 <= last_end <= start <= at < end <= 120:
                    raise ValueError("Challenge windows must be ordered, non-overlapping and within 120 s")
                offset = vector3(row["offset"])
                if offset[2] >= 0: raise ValueError("Straight-punch target must be forward of the shoulder")
                cues.append(ChallengeCue(identity, row["hand"], at, start, end, tuple(map(float, offset))))
                used.add(identity)
                last_end = end
            json.dumps(data, allow_nan=False)
            return cls(tuple(cues), radius, deepcopy(data))
        except (KeyError, TypeError, AttributeError, OverflowError) as exc:
            raise ValueError(f"Malformed challenge: {exc}") from exc

    @classmethod
    def load(cls, path):
        path = Path(path)
        if path.stat().st_size > 4 * 1024 * 1024:
            raise ValueError("Challenge file exceeds 4 MiB")
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def to_dict(self):
        return deepcopy(self.raw)

    @property
    def duration_s(self):
        return self.cues[-1].end_s

    def map_targets(self, profile, config, neutral_fists):
        width = float(np.linalg.norm(profile.reference_shoulders["right"] - profile.reference_shoulders["left"]))
        if not math.isfinite(width) or width <= .02:
            raise ValueError("Calibrated shoulders do not define a usable scale")
        targets = []
        for cue in self.cues:
            reach = number(profile.comfortable_extensions[cue.hand], "calibrated reach", positive=True)
            shoulder = profile.reference_shoulders[cue.hand]
            center = shoulder + np.asarray(cue.offset) * (width, width, reach)
            neutral = neutral_fists.get(cue.hand)
            if neutral is None or neutral.position is None:
                raise ValueError("Valid neutral fists required to map a challenge")
            if not config.min_depth_m <= center[2]-self.radius_m < center[2]+self.radius_m <= config.max_depth_m:
                raise ValueError(f"Cue {cue.cue_id} is outside the configured depth range")
            if np.linalg.norm(center-shoulder) > reach + config.hand_radius_m + self.radius_m:
                raise ValueError(f"Cue {cue.cue_id} exceeds the measured comfortable reach")
            if np.linalg.norm(center-neutral.position) <= config.hand_radius_m + self.radius_m + .02:
                raise ValueError(f"Cue {cue.cue_id} overlaps the neutral guard")
            targets.append(Target(cue.cue_id, cue.hand, vector3(center), self.radius_m, False))
        return tuple(targets)
