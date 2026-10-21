"""Single-thread session orchestration; rendering never owns acquisition."""
from contextlib import ExitStack
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


def run_session(source, simulation, view, recorder=None, max_frames=None, *,
                rgbd_recorder=None, realtime=False, clock=time.monotonic) -> SessionSummary:
    started = last_success = clock()
    count = timeouts = 0
    state = SceneState(None, (), 0, 0, simulation.config.round_duration_s, (), "CALIBRATING")
    pending = []
    first_t = first_wall = None

    def apply(actions):
        for action in actions:
            if action == "pause": simulation.set_paused(not simulation.paused)
            elif action == "reset": simulation.reset()
            elif action == "tracking_lost": simulation.invalidate_tracking()

    with ExitStack() as resources:
        # Register immediately so any downstream read/render/write error still closes all.
        for resource in (source, view, recorder, rgbd_recorder):
            if resource is not None: resources.callback(resource.close)
        while max_frames is None or count < max_frames:
            actions = view.poll_actions()
            if "quit" in actions: break
            apply(actions)
            pending.extend(actions)
            try:
                frame = source.read()
            except FrameTimeout:
                timeouts += 1
                simulation.invalidate_tracking()
                if not pending or pending[-1] != "tracking_lost": pending.append("tracking_lost")
                state = replace(state, skeleton=None, events=(), status="WAITING FOR CAMERA", phases={})
                view.render(state, None)
                if clock()-last_success >= simulation.config.stream_timeout_s:
                    raise DepthStrikeError(f"No valid RGB-D frames for {simulation.config.stream_timeout_s:g} s. Check USB/synchronization and reconnect the camera.")
                continue
            if frame is None: break
            last_success = clock()
            if realtime:
                if first_t is None: first_t, first_wall = frame.timestamp_s, clock()
                deadline = first_wall+frame.timestamp_s-first_t
                quit_requested = False
                while deadline-clock() > 0:
                    wait_actions = view.poll_actions()
                    if "quit" in wait_actions:
                        quit_requested = True
                        break
                    apply(wait_actions)
                    pending.extend(wait_actions)
                    # poll_actions pumps both windows; keep the last presented
                    # image until this frame is due, without duplicate trails.
                    time.sleep(min(.05, max(0., deadline-clock())))
                if quit_requested: break
            replay_actions = list(getattr(source, "actions", ()))
            apply(replay_actions)
            pending.extend(replay_actions)
            state = simulation.step(frame)
            rgbd = getattr(source, "last_rgbd", None)
            if recorder is not None: recorder.write(frame, state.events, actions=pending)
            if rgbd_recorder is not None:
                if rgbd is None: raise DepthStrikeError("RGB-D recording requires a paired RGB-D source")
                rgbd_recorder.write(rgbd, actions=pending)
            pending = []
            view.render(state, rgbd)
            count += 1
            if state.status == "FINISHED": break
    return SessionSummary(count, state.score, state.hits, state.remaining_s,
                          timeouts, max(0., clock()-started))
