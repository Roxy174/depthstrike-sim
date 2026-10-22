"""Fixed-time challenge scoring and bounded, observation-aware motion reviews."""
from copy import deepcopy
from dataclasses import replace

import numpy as np

from . import __version__
from .counterfactual import analyze_segment
from .geometry import segment_sphere_intersection
from .types import HitEvent


class ChallengeRound:
    def __init__(self, recipe, config):
        if config.interaction_mode != "guided":
            raise ValueError("Motion challenges require guided calibration")
        if recipe.duration_s > config.round_duration_s:
            raise ValueError("Challenge is longer than round_duration_s; select a suitable configuration")
        self.recipe, self.config = recipe, config
        self.reset()

    def reset(self):
        self.elapsed = 0.
        self.hits = self.score = 0
        self.targets = ()
        self.profile = None
        self._previous = None
        self._broken = False
        self._settled = set()
        self._last_result = None
        self._rows = [{"cue_id": c.cue_id, "hand": c.hand, "start_s": c.start_s, "end_s": c.end_s,
            "at_s": c.at_s, "outcome": "pending", "reason": None, "observed_segments": 0,
            "interrupted": False, "eligible_segments": 0, "hit_time_s": None,
            "trajectory": [], "trajectory_truncated": False, "best_any": None, "best_eligible": None}
            for c in self.recipe.cues]

    @property
    def complete(self):
        return self.elapsed >= self.recipe.duration_s

    def invalidate(self):
        if self.targets:
            self._broken = True
            for row in self._rows:
                if row["start_s"] <= self.elapsed < row["end_s"]:
                    row["interrupted"] = True
                    self._append(row, self.elapsed, None)
        self._previous = None

    @staticmethod
    def _append(row, t, position):
        row["trajectory"].append({"t_s": float(t), "position_m": position.tolist() if position is not None else None})
        if len(row["trajectory"]) > 256:
            del row["trajectory"][0]
            row["trajectory_truncated"] = True

    def update(self, frame, fists, states, elapsed, valid, profile):
        old_elapsed = self.elapsed
        self.elapsed = float(elapsed)
        if not self.targets and valid:
            self.targets = self.recipe.map_targets(profile, self.config, fists)
            self.profile = profile
            for row, target in zip(self._rows, self.targets):
                row.update(target_center_m=target.center.tolist(), target_radius_m=target.radius)
        if not self.targets: return ()
        if not valid:
            self.invalidate()
            return ()
        previous = self._previous
        connected = previous is not None and 0 < frame.timestamp_s-previous[0] <= self.config.max_track_gap_s + 1e-9
        if self._broken or previous is not None and not connected:
            for row in self._rows:
                if old_elapsed < row["end_s"] and row["start_s"] <= self.elapsed:
                    row["interrupted"] = True
        self._broken = False
        events = []
        for cue, target, row in zip(self.recipe.cues, self.targets, self._rows):
            if row["outcome"] != "pending": continue
            point = fists[cue.hand].position
            state = states[cue.hand]
            key = (cue.hand, state.attack_id)
            if connected and self.elapsed > previous[1]:
                t0, p0 = previous[1], previous[2][cue.hand]
                span = self.elapsed-t0
                source_span = frame.timestamp_s-previous[0]
                eligible_lo = eligible_hi = None
                if (key not in self._settled and state.eligible_from_s is not None
                        and state.eligible_until_s is not None):
                    eligible_lo = max(t0, t0+span*(state.eligible_from_s-previous[0])/source_span)
                    eligible_hi = min(self.elapsed, t0+span*(state.eligible_until_s-previous[0])/source_span)
                lo, hi = max(t0, cue.start_s), min(self.elapsed, np.nextafter(cue.end_s, cue.start_s))
                if hi > lo:
                    a = p0 + (point-p0) * ((lo-t0)/span)
                    b = p0 + (point-p0) * ((hi-t0)/span)
                    if not row["trajectory"]: self._append(row, lo, a)
                    self._append(row, hi, b)
                    row["observed_segments"] += 1
                    analysis = analyze_segment(a, b, target, self.config.hand_radius_m,
                        profile.reference_shoulders[cue.hand], profile.comfortable_extensions[cue.hand],
                        self.config.min_depth_m, self.config.max_depth_m)
                    analysis["closest_time_s"] = float(lo+analysis["fraction"]*(hi-lo))
                    if row["best_any"] is None or analysis["surface_gap_m"] < row["best_any"]["surface_gap_m"]:
                        row["best_any"] = analysis
                    if eligible_lo is not None:
                        e0, e1 = max(lo, eligible_lo), min(hi, eligible_hi)
                        if e1 > e0:
                            ea = p0 + (point-p0)*((e0-t0)/span)
                            eb = p0 + (point-p0)*((e1-t0)/span)
                            eligible_analysis = analyze_segment(ea, eb, target, self.config.hand_radius_m,
                                profile.reference_shoulders[cue.hand], profile.comfortable_extensions[cue.hand],
                                self.config.min_depth_m, self.config.max_depth_m)
                            eligible_analysis["closest_time_s"] = float(e0+eligible_analysis["fraction"]*(e1-e0))
                            if (row["best_eligible"] is None or eligible_analysis["surface_gap_m"]
                                    < row["best_eligible"]["surface_gap_m"]):
                                row["best_eligible"] = eligible_analysis
                            row["eligible_segments"] += 1
                if eligible_lo is not None and row["hit_time_s"] is None:
                    radius = self.config.hand_radius_m+target.radius
                    # History is continuous even while the target is inactive;
                    # activating an already-overlapping target cannot create entry.
                    if np.linalg.norm(p0-target.center) > radius:
                        fraction = segment_sphere_intersection(p0, point, target.center, radius)
                        if fraction is not None:
                            hit_t = t0+fraction*(self.elapsed-t0)
                            if (cue.start_s <= hit_t < cue.end_s
                                    and eligible_lo-1e-9 <= hit_t <= eligible_hi+1e-9):
                                self._settled.add(key)
                                row["hit_time_s"] = float(hit_t)
                                row["attack_id"] = state.attack_id
                                self.hits += 1
                                self.score += 10
                                source_hit_t = frame.timestamp_s-(self.elapsed-hit_t)
                                events.append(HitEvent(float(source_hit_t), cue.hand, cue.cue_id, state.attack_id, 10))
            elif cue.start_s < self.elapsed < cue.end_s:
                row["interrupted"] = True
            if self.elapsed >= cue.end_s:
                self._finalize(row)
        self._previous = (frame.timestamp_s, self.elapsed, {h: j.position.copy() for h, j in fists.items()})
        return tuple(events)

    def _finalize(self, row):
        if row["hit_time_s"] is not None:
            outcome, reason = "hit", "hit"
        elif row["interrupted"] or not row["observed_segments"]:
            outcome, reason = "unobserved", "insufficient_observation"
        elif not row["eligible_segments"]:
            outcome, reason = "miss", "no_valid_attack"
        else:
            outcome, reason = "miss", "spatial_miss"
        row.update(outcome=outcome, reason=reason)
        self._last_result = self._public(row)

    @staticmethod
    def _public(row):
        result = deepcopy({k: v for k, v in row.items() if not k.startswith("best_")})
        if result["outcome"] == "pending":
            result.update(outcome="incomplete", reason="window_not_completed")
        best = row["best_eligible"] if row["eligible_segments"] else row["best_any"]
        result.update(closest_point_m=None, surface_gap_m=None, segment_m=None, closest_time_s=None, counterfactual=None)
        if best:
            result.update({k: best[k] for k in ("closest_point_m", "surface_gap_m", "segment_m", "closest_time_s")})
            if result["reason"] == "spatial_miss":
                result["counterfactual"] = deepcopy(best["counterfactual"])
                if best["surface_gap_m"] <= 0:
                    result["reason"] = "entry_outside_window"
                    result["counterfactual"] = None
        return result

    def visible_targets(self):
        index = next((n for n, c in enumerate(self.recipe.cues) if self.elapsed < c.end_s), None)
        if index is None:
            return tuple(replace(t, active=False) for t in self.targets[-1:])
        return tuple(replace(self.targets[n], active=self.recipe.cues[n].start_s <= self.elapsed < self.recipe.cues[n].end_s,
                             flash=self._rows[n]["hit_time_s"] is not None)
                     for n in range(index, min(index+2, len(self.targets))))

    def display(self):
        index = next((n for n, c in enumerate(self.recipe.cues) if self.elapsed < c.end_s), len(self.recipe.cues)-1)
        cue = self.recipe.cues[index]
        return {"cue_index": index+1, "total": len(self.recipe.cues), "hand": cue.hand,
                "until_window_s": max(0., cue.start_s-self.elapsed),
                "last_result": self._last_result, "content_evidence": self.recipe.raw["source"]["evidence"]}

    def report(self, metadata=None):
        return {"format": "depthstrike.motion_review", "version": 1, "program_version": __version__,
            "status": "complete" if self.complete else "partial", "evidence": (metadata or {}).get("evidence", "unverified"),
            "source_metadata": metadata or {}, "challenge": self.recipe.to_dict(), "config": self.config.to_dict(),
            "scope": "derived_challenge_and_local_geometry_not_independent_accuracy_or_professional_coaching",
            "player_calibration": None if self.profile is None else {
                "reference_shoulders_m": {h: p.tolist() for h, p in self.profile.reference_shoulders.items()},
                "comfortable_extensions_m": dict(self.profile.comfortable_extensions),
                "guard_thresholds_m": dict(self.profile.guard_thresholds),
                "attack_thresholds_m": dict(self.profile.attack_thresholds)},
            "elapsed_s": self.elapsed, "score": self.score, "hits": self.hits,
            "trials": [self._public(row) for row in self._rows]}
