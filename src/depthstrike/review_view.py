"""Front/side motion inspection with optional PNG export and no device imports."""
import json
import os
from pathlib import Path
import time

import numpy as np

from .config import AppConfig
from .motion_challenge import ChallengeRecipe, number
from .types import DepthStrikeError, vector3

REASONS = {
    "hit": "Observed contact satisfied the attack and time window.",
    "spatial_miss": "The valid attack passed outside the contact region.",
    "no_valid_attack": "No valid forward attack was observed in this window.",
    "insufficient_observation": "Observation was interrupted; no correction is inferred.",
    "window_not_completed": "The session ended before this window was completed.",
    "entry_outside_window": "Contact entry did not occur inside the active time window.",
}


def load_review(path):
    path = Path(path)
    if path.stat().st_size > 16 * 1024 * 1024: raise ValueError("Review file exceeds 16 MiB")
    def invalid(value): raise ValueError(f"Non-finite review JSON: {value}")
    data = json.loads(path.read_text(encoding="utf-8"), parse_constant=invalid)
    try:
        if (data["format"] != "depthstrike.motion_review" or type(data["version"]) is not int or data["version"] != 1
                or data["status"] not in ("complete", "partial")
                or data["evidence"] not in ("synthetic", "recorded", "unverified")):
            raise ValueError("Unsupported motion review")
        recipe = ChallengeRecipe.from_dict(data["challenge"])
        AppConfig(**data["config"])
        trials = data["trials"]
        if not isinstance(trials, list) or len(trials) != len(recipe.cues): raise ValueError("Invalid review trial count")
        for cue, row in zip(recipe.cues, trials):
            if row["cue_id"] != cue.cue_id or row["hand"] != cue.hand:
                raise ValueError("Review identity disagrees with the challenge")
            if row["outcome"] not in ("hit", "miss", "unobserved", "incomplete"):
                raise ValueError("Invalid review outcome")
            points = [row.get("target_center_m"), row.get("closest_point_m")]
            trajectory = row["trajectory"]
            if not isinstance(trajectory, list) or len(trajectory) > 256: raise ValueError("Invalid review trajectory")
            last_t = -1.
            for sample in trajectory:
                t = number(sample["t_s"], "sample time")
                if t < last_t or t < 0: raise ValueError("Review trajectory is not time ordered")
                last_t = t
                points.append(sample["position_m"])
            if row.get("segment_m"): points.extend(row["segment_m"])
            correction = row.get("counterfactual")
            if correction:
                points.extend(correction["segment_m"])
                points.append(correction["delta_m"])
            for point in points:
                if point is not None:
                    if np.max(np.abs(vector3(point))) > 100: raise ValueError("Review geometry exceeds display bounds")
        return data
    except (KeyError, TypeError, AttributeError, OverflowError) as exc:
        raise ValueError(f"Malformed motion review: {exc}") from exc


def render_review(report, selected=0, progress=1.):
    import cv2
    if not 0 <= selected < len(report["trials"]): raise ValueError("Invalid review selection")
    progress = float(np.clip(number(progress, "playback progress"), 0, 1))
    canvas = np.full((820, 1120, 3), (248, 244, 239), np.uint8)
    ink, muted, blue, violet, green = (72, 54, 38), (132, 116, 99), (195, 100, 39), (162, 79, 137), (94, 138, 43)
    def text(value, at, size=.52, color=ink, weight=1):
        cv2.putText(canvas, str(value), at, cv2.FONT_HERSHEY_SIMPLEX, size, color, weight, cv2.LINE_AA)
    cv2.rectangle(canvas, (0, 0), (1119, 88), ink, -1)
    text("DepthStrike / Motion Studio", (24, 36), .88, (255, 255, 255), 2)
    text(f"Input: {report['evidence']}    Session: {report['status']}    Geometric motion review", (25, 66), .48, (227, 218, 207))
    row = report["trials"][selected]
    text("Challenge sequence", (24, 126), .65, weight=2)
    text(f"{report['hits']} hits / {len(report['trials'])} cues", (24, 156), .55, muted)
    first = max(0, min(selected-5, len(report["trials"])-12))
    for n in range(first, min(first+12, len(report["trials"]))):
        trial, y = report["trials"][n], 199+(n-first)*32
        if n == selected: cv2.rectangle(canvas, (16, y-22), (267, y+7), (231, 219, 201), -1)
        color = green if trial["outcome"] == "hit" else (violet if trial.get("counterfactual") else muted)
        text(f"{n+1:02d}  {trial['hand'].title():5s}  {trial['outcome']}", (25, y), .48, color, 2 if n == selected else 1)
    text("A / D   previous / next", (24, 650), .46, muted)
    text("Space   play / pause", (24, 677), .46, muted)
    text("R   replay motion", (24, 704), .46, muted)
    text("Q / Esc   close", (24, 731), .46, muted)
    text(f"Cue {selected+1} / {len(report['trials'])}  -  {row['hand'].title()}", (300, 126), .73, weight=2)
    text(f"{row['start_s']:.2f} - {row['end_s']:.2f} s    {row['outcome'].replace('_', ' ')}", (300, 155), .52, muted)
    trajectory = row["trajectory"]
    points = [np.array(s["position_m"]) for s in trajectory if s["position_m"] is not None]
    center = row.get("target_center_m")
    correction = row.get("counterfactual")
    extents = points + ([np.asarray(center)] if center is not None else [])
    if correction: extents.extend(np.asarray(correction["segment_m"]))
    first_t, last_t = (trajectory[0]["t_s"], trajectory[-1]["t_s"]) if trajectory else (0., 1.)
    play_t = first_t + progress * (last_t-first_t)
    for box, axes, label in (((300, 194, 680, 540), (0, 1), "Front view / X and Y"),
                             ((716, 194, 1096, 540), (2, 1), "Side view / Z and Y")):
        x0, y0, x1, y1 = box
        cv2.rectangle(canvas, (x0, y0), (x1, y1), (255, 255, 255), -1)
        text(label, (x0+10, y0+24), .5, muted)
        if not extents:
            text("No mapped motion", (x0+70, y0+160), .55, muted)
            continue
        values = np.asarray(extents)[:, axes]
        middle = (values.min(axis=0)+values.max(axis=0))/2
        span = max(float(np.ptp(values, axis=0).max())+.4, .6)
        scale = min(x1-x0-80, y1-y0-80)/span
        def pixel(p):
            offset = (np.asarray(p)[list(axes)]-middle)*scale
            return int((x0+x1)/2+offset[0]), int((y0+y1)/2+offset[1])
        for n in range(1, 5):
            u, v = x0+(x1-x0)*n//5, y0+(y1-y0)*n//5
            cv2.line(canvas, (u, y0+37), (u, y1-28), (240, 233, 225), 1)
            cv2.line(canvas, (x0+12, v), (x1-12, v), (240, 233, 225), 1)
        if center is not None:
            target_pixel = pixel(center)
            target_r = max(2, round(row["target_radius_m"]*scale))
            cv2.circle(canvas, target_pixel, target_r, green, 2, cv2.LINE_AA)
            cv2.circle(canvas, target_pixel, max(2, round((row["target_radius_m"]+report["config"]["hand_radius_m"])*scale)), (200, 213, 193), 1, cv2.LINE_AA)
        latest = None
        for a, b in zip(trajectory, trajectory[1:]):
            if a["position_m"] is None or b["position_m"] is None: continue
            color = blue if b["t_s"] <= play_t else (218, 201, 182)
            cv2.line(canvas, pixel(a["position_m"]), pixel(b["position_m"]), color, 2, cv2.LINE_AA)
            if b["t_s"] <= play_t: latest = b["position_m"]
        if latest is not None: cv2.circle(canvas, pixel(latest), 5, blue, -1, cv2.LINE_AA)
        if row.get("segment_m"):
            cv2.line(canvas, pixel(row["segment_m"][0]), pixel(row["segment_m"][1]), blue, 4, cv2.LINE_AA)
        if row.get("closest_point_m") is not None:
            cv2.circle(canvas, pixel(row["closest_point_m"]), 6, blue, 2, cv2.LINE_AA)
        if correction:
            a, b = correction["segment_m"]
            cv2.line(canvas, pixel(a), pixel(b), violet, 3, cv2.LINE_AA)
            closest = np.asarray(row["closest_point_m"])
            cv2.arrowedLine(canvas, pixel(closest), pixel(closest+correction["delta_m"]), violet, 2, cv2.LINE_AA, tipLength=.25)
        text(f"Scale: {span:.2f} m across plotting area", (x0+12, y1-9), .36, muted)
    cv2.rectangle(canvas, (300, 563), (1096, 569), (224, 214, 202), -1)
    cv2.rectangle(canvas, (300, 563), (300+round(796*progress), 569), blue, -1)
    text(REASONS.get(row["reason"], "No complete observation available."), (300, 610), .49, weight=1)
    if row.get("surface_gap_m") is not None:
        text(f"Closest surface gap: {row['surface_gap_m']:+.3f} m", (300, 642), .59, blue, 2)
    text("Blue: motion   Green: target + contact region   Purple: local correction", (300, 678), .44, muted)
    if correction:
        dx, dy, dz = correction["delta_m"]
        text(f"Local shift  X {dx:+.3f}   Y {dy:+.3f}   Z {dz:+.3f} m", (300, 714), .52, violet, 2)
        text("Contact rechecked. Only the highlighted segment is translated.", (300, 744), .44, muted)
    else:
        text("No local correction proposed for this outcome.", (300, 716), .5, muted)
    text("Camera coordinates: X right, Y down, Z forward. Correction is not a whole-body instruction.", (300, 791), .39, muted)
    return canvas


def export_image(report, selected, path):
    import cv2
    path = Path(path)
    if path.exists(): raise FileExistsError(f"Review image already exists: {path}")
    if path.suffix.lower() != ".png": raise ValueError("Review image must use .png")
    ok, encoded = cv2.imencode(".png", render_review(report, selected))
    if not ok: raise DepthStrikeError("Could not encode review image")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream: stream.write(encoded.tobytes())


def show_review(report, selected=0):
    import cv2
    if os.environ.get("DEPTHSTRIKE_NO_DISPLAY") or (os.name != "nt" and not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY")):
        raise DepthStrikeError("No display available; use review --image PATH.png")
    name = "DepthStrike | motion review"
    progress, playing, last = 1., False, time.monotonic()
    try:
        cv2.namedWindow(name, cv2.WINDOW_AUTOSIZE)
        cv2.moveWindow(name, 50, 40)
        while cv2.getWindowProperty(name, cv2.WND_PROP_VISIBLE) >= 1:
            now = time.monotonic()
            if playing:
                samples = report["trials"][selected]["trajectory"]
                duration = max(.5, samples[-1]["t_s"]-samples[0]["t_s"]) if samples else 1.
                progress = min(1., progress+(now-last)/duration)
                if progress == 1.: playing = False
            last = now
            cv2.imshow(name, render_review(report, selected, progress))
            key = cv2.waitKeyEx(20)
            if key in (ord("q"), 27): break
            if key in (ord("a"), ord("d"), 2424832, 2555904):
                direction = -1 if key in (ord("a"), 2424832) else 1
                selected = (selected+direction) % len(report["trials"])
                progress, playing = 1., False
            elif key in (32, ord("r")):
                if key == ord("r") or progress == 1.: progress = 0.
                playing = True if key == ord("r") else not playing
    finally:
        try: cv2.destroyWindow(name)
        except cv2.error: pass
