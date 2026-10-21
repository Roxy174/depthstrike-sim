"""Bounded, software-clock diagnostics; never a sensor-to-display latency claim."""
from collections import deque
from contextlib import contextmanager
import json
import math
from pathlib import Path
import time

import numpy as np


class StageMetrics:
    def __init__(self, clock=time.perf_counter, capacity=4096):
        if type(capacity) is not int or capacity <= 0:
            raise ValueError("metrics capacity must be a positive integer")
        self.clock, self.capacity = clock, capacity
        self._samples, self._counts, self._failed = {}, {}, {}
        self.session = {"frames": 0, "timeouts": 0}

    def record(self, name: str, duration_s: float, *, failed=False):
        if not isinstance(name, str) or not name or not math.isfinite(duration_s) or duration_s < 0:
            raise ValueError("Metric name and duration must be valid")
        self._samples.setdefault(name, deque(maxlen=self.capacity)).append(duration_s)
        self._counts[name] = self._counts.get(name, 0) + 1
        self._failed[name] = self._failed.get(name, 0) + int(failed)

    @contextmanager
    def measure(self, name):
        started = self.clock()
        failed = True
        try:
            yield
            failed = False
        finally:
            self.record(name, max(0., self.clock() - started), failed=failed)

    def snapshot(self):
        return {"sampling": "last_n_per_stage", "capacity": self.capacity, "session": dict(self.session),
                "clock": "software_monotonic", "unit": "s",
                "nested_stages": {"read": ["capture", "pose", "fusion"]},
                "frame_total_excludes": ["replay_wait", "event_poll_before_read"],
                "read_includes_timeouts_and_eof": True,
                "stages": {name: {"total_count": self._counts[name], "retained_count": len(values),
                    "failed_count": self._failed[name],
                    "p50_s": float(np.quantile(values, .5)), "p95_s": float(np.quantile(values, .95)),
                    "max_s": float(max(values))} for name, values in self._samples.items()}}

    def write_exclusive(self, path, metadata):
        content = json.dumps({"format": "depthstrike.metrics", "version": 1,
                              "metadata": metadata, **self.snapshot()}, allow_nan=False, indent=2) + "\n"
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as stream:
            stream.write(content)
