"""Extract completed, observed straight punches from a guided pose recording."""
import numpy as np

from .boxing import BoxingSimulation
from .motion_challenge import ChallengeRecipe, file_sha256
from .recording import COORDINATES, PoseReplaySource


def author_recording(input_path):
    completed, pending = [], {}
    profile = None
    last_t = None
    discarded = count = 0
    with PoseReplaySource(input_path) as source:
        config = source.config
        if config.interaction_mode != "guided":
            raise ValueError("Authoring requires a guided recording including reach calibration")
        simulation = BoxingSimulation(config)
        while (frame := source.read()) is not None:
            count += 1
            if count > 200000: raise ValueError("Authoring recording exceeds 200000 frames")
            interrupted = last_t is not None and frame.timestamp_s-last_t > config.max_track_gap_s + 1e-9
            last_t = frame.timestamp_s
            for action in source.actions:
                interrupted = True
                if action == "reset":
                    if profile is not None:
                        raise ValueError("Split a recording at reset before authoring another formal round")
                    simulation.reset()
                elif action == "pause": simulation.set_paused(not simulation.paused)
                elif action == "tracking_lost": simulation.invalidate_tracking()
            if interrupted:
                discarded += len(pending)
                pending.clear()
            state = simulation.step(frame)
            if state.status != "RUNNING" or state.guidance.stage != "RUNNING":
                discarded += len(pending)
                pending.clear()
                continue
            if profile is None:
                profile = state.guidance.profile
            elapsed = config.round_duration_s-state.remaining_s
            for hand in ("left", "right"):
                if state.phases[hand] == "ATTACKING":
                    fist = state.fists[hand].position
                    extension = profile.reference_shoulders[hand][2]-fist[2]
                    if hand not in pending or extension > pending[hand]["extension"]:
                        pending[hand] = {"hand": hand, "at_s": elapsed, "position": fist.copy(), "extension": extension}
                elif state.phases[hand] == "READY" and hand in pending:
                    completed.append(pending.pop(hand))
                    if len(completed) > 32: raise ValueError("Split demonstrations into at most 32 completed punches")
        discarded += len(pending)
        metadata = source.metadata
    if profile is None or not completed:
        raise ValueError("Recording needs calibration and at least one completed formal punch")
    width = float(np.linalg.norm(profile.reference_shoulders["right"]-profile.reference_shoulders["left"]))
    if width <= .02: raise ValueError("Demonstration shoulder width is too small")
    completed.sort(key=lambda row: row["at_s"])
    if any(b["at_s"] <= a["at_s"] for a, b in zip(completed, completed[1:])):
        raise ValueError("Simultaneous punches are not supported by sequential challenges")
    cues = []
    for n, stroke in enumerate(completed):
        at = stroke["at_s"]
        start, end = max(0., at-.4), at+.45
        if n: start = max(start, (completed[n-1]["at_s"]+at)/2)
        if n+1 < len(completed): end = min(end, (at+completed[n+1]["at_s"])/2)
        hand = stroke["hand"]
        offset = (stroke["position"]-profile.reference_shoulders[hand]) / (width, width, profile.comfortable_extensions[hand])
        cues.append({"cue_id": n, "hand": hand, "at_s": at, "start_s": start, "end_s": end,
                     "offset": offset.tolist()})
    return ChallengeRecipe.from_dict({"format": "depthstrike.challenge", "version": 1,
        "unit": "m", "timestamp_unit": "s", "coordinates": COORDINATES,
        "radius_m": config.target_radius_m, "source_config": config.to_dict(),
        "source": {"sha256": file_sha256(input_path), "evidence": metadata.get("evidence", "unverified"),
                   "recording_metadata": metadata},
        "author_scale": {"shoulder_width_m": width,
                         "comfortable_extensions_m": dict(profile.comfortable_extensions)},
        "extraction": {"method": "completed_guided_straight_punch_peak_v1", "frame_count": count,
                       "discarded_incomplete": discarded, "labels": "derived_content_not_independent_truth"},
        "cues": cues})
