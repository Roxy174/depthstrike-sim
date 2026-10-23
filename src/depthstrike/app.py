"""Single-thread orchestration with independent input and profiling clocks."""
from contextlib import ExitStack, nullcontext
from dataclasses import dataclass, replace
import time

from .types import DepthStrikeError, FrameTimeout, SceneState


@dataclass(frozen=True)
class SessionSummary:
    frames: int
    score: int
    hits: int
    remaining_s: float
    timeouts: int
    processing_s: float
    termination: str = "eof"


def run_session(source, simulation, view, recorder=None, max_frames=None, *,
                rgbd_recorder=None, realtime=False, clock=time.monotonic, metrics=None) -> SessionSummary:
    started = last_success = clock()
    count = timeouts = 0
    state = SceneState(None, (), 0, 0, simulation.config.round_duration_s, (), "CALIBRATING")
    pending = []
    first_t = first_wall = None
    termination = "frame_limit"

    def span(name):
        return metrics.measure(name) if metrics else nullcontext()

    def apply(actions):
        for action in actions:
            if action == "pause": simulation.set_paused(not simulation.paused)
            elif action == "reset": simulation.reset()
            elif action == "tracking_lost": simulation.invalidate_tracking()
            if hasattr(source, "handle_action"):
                source.handle_action(action, paused=simulation.paused)

    with ExitStack() as resources:
        for resource in (source, view, recorder, rgbd_recorder):
            if resource is not None: resources.callback(resource.close)
        while max_frames is None or count < max_frames:
            actions = view.poll_actions()
            if "quit" in actions:
                termination = "quit"
                break
            apply(actions)
            pending.extend(actions)
            frame_started = metrics.clock() if metrics else 0.
            wait_s = 0.
            include_total = True
            try:
                try:
                    with span("read"):
                        frame = source.read()
                except FrameTimeout:
                    timeouts += 1
                    if metrics: metrics.session["timeouts"] = timeouts
                    simulation.invalidate_tracking()
                    if not pending or pending[-1] != "tracking_lost": pending.append("tracking_lost")
                    state = replace(state, skeleton=None, events=(), status="WAITING FOR CAMERA", phases={},
                                    fists={}, feedback={}, diagnostics={}, display_joints={})
                    with span("render"):
                        view.render(state, None)
                    if clock()-last_success >= simulation.config.stream_timeout_s:
                        raise DepthStrikeError(f"No valid RGB-D frames for {simulation.config.stream_timeout_s:g} s. Check USB/synchronization and reconnect the camera.")
                    continue
                if frame is None:
                    include_total = False
                    termination = "eof"
                    break
                last_success = clock()
                if realtime:
                    if first_t is None: first_t, first_wall = frame.timestamp_s, clock()
                    deadline = first_wall+frame.timestamp_s-first_t
                    quit_requested = False
                    wait_started = metrics.clock() if metrics else 0.
                    while deadline-clock() > 0:
                        wait_actions = view.poll_actions()
                        if "quit" in wait_actions:
                            quit_requested = True
                            break
                        apply(wait_actions)
                        pending.extend(wait_actions)
                        time.sleep(min(.05, max(0., deadline-clock())))
                    if metrics: wait_s = max(0., metrics.clock()-wait_started)
                    if quit_requested:
                        termination = "quit"
                        break
                replay_actions = list(getattr(source, "actions", ()))
                apply(replay_actions)
                pending.extend(replay_actions)
                rgbd = getattr(source, "last_rgbd", None)
                if simulation.config.spatial_layout and rgbd is not None:
                    from .spatial import DepthWorkspace
                    simulation.set_workspace(DepthWorkspace(rgbd))
                with span("simulation"):
                    state = simulation.step(frame)
                rgbd = getattr(source, "last_rgbd", None)
                with span("record"):
                    if recorder is not None: recorder.write(frame, state.events, actions=pending)
                    if rgbd_recorder is not None:
                        if rgbd is None: raise DepthStrikeError("RGB-D recording requires a paired RGB-D source")
                        rgbd_recorder.write(rgbd, actions=pending)
                pending = []
                with span("render"):
                    view.render(state, rgbd)
                count += 1
                if metrics: metrics.session["frames"] = count
                if state.status == "FINISHED":
                    termination = "round_finished"
                    break
            finally:
                if metrics and include_total:
                    metrics.record("frame_total", max(0., metrics.clock()-frame_started-wait_s))
    return SessionSummary(count, state.score, state.hits, state.remaining_s,
                          timeouts, max(0., clock()-started), termination)
