"""Optional asynchronous system sound. Audio never participates in scoring."""
import os
import sys


class AudioFeedback:
    def __init__(self, enabled=False, *, backend=None):
        self.enabled = enabled
        self.backend = backend
        self._last_event = None
        self._playing = False
        if enabled and backend is None:
            if os.name != "nt":
                self._disable("system sound is only supported on Windows")
            else:
                try:
                    import winsound
                    self.backend = winsound
                except ImportError as exc:
                    self._disable(str(exc))

    def _disable(self, reason):
        if self.enabled:
            print(f"DepthStrike audio disabled: {reason}", file=sys.stderr)
        self.enabled = False

    def notify(self, events):
        if not self.enabled or not events:
            return
        event = events[-1]
        key = (event.timestamp_s, event.hand, event.target_id, event.attack_id)
        if key == self._last_event:
            return
        self._last_event = key
        try:
            b = self.backend
            b.PlaySound("SystemAsterisk", b.SND_ALIAS | b.SND_ASYNC | b.SND_NODEFAULT)
            self._playing = True
        except (OSError, RuntimeError) as exc:
            self._disable(str(exc))

    def close(self):
        if self._playing:
            try:
                self.backend.PlaySound(None, 0)
            except (OSError, RuntimeError) as exc:
                self._disable(str(exc))
            self._playing = False
