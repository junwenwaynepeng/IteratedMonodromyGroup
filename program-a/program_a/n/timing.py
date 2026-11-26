"""Observed per-invocation phase clocks. Parent wall includes phases; never sum it again."""

from contextlib import contextmanager
import time, copy


class Clocks:
    def __init__(self):
        self.started = time.monotonic()
        self.cpu = time.process_time()
        self.phases = {}
        self.native = []
        self.first_certified_bound_wall_seconds = None

    @contextmanager
    def phase(self, name):
        w = time.monotonic()
        c = time.process_time()
        try:
            yield
        finally:
            z = self.phases.setdefault(
                name, {"wall_seconds": 0.0, "Python_CPU_seconds": 0.0, "calls": 0}
            )
            z["wall_seconds"] += time.monotonic() - w
            z["Python_CPU_seconds"] += time.process_time() - c
            z["calls"] += 1

    def record(self):
        return {
            "engine_invocation_wall_seconds": time.monotonic() - self.started,
            "Python_process_CPU_seconds": time.process_time() - self.cpu,
            "phases": copy.deepcopy(self.phases),
            "native_children": copy.deepcopy(self.native),
            "first_bound_wall_seconds": self.first_certified_bound_wall_seconds,
            "cumulative_from_zero_discovery_wall_seconds": None,
            "cumulative_total_CPU_seconds": None,
            "semantics": "Observed invocation and disjoint named phase wall. Python CPU excludes children. Raw/checker are included in engine wall. First bound clock means first fully whole-tree+raw accepted certificate. Historical and human time unknown. Outer wrapper measured separately.",
        }
