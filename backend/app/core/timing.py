"""
Processing-time measurement helpers for verification runs.

Architectural responsibility: honest wall-clock timing for PERFORMANCE.md targets.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field


@dataclass
class TimingResult:
    """Elapsed wall-clock time for a timed section."""

    label: str
    elapsed_ms: float


@dataclass
class PipelineTimer:
    """Accumulates overall and optional stage timings for one verification."""

    stages: list[TimingResult] = field(default_factory=list)
    _start_ns: int | None = field(default=None, repr=False)

    def start(self) -> None:
        """Begin overall timing."""
        self._start_ns = time.perf_counter_ns()

    def stop_overall_ms(self) -> float:
        """Return milliseconds since `start()`. Raises if not started."""
        if self._start_ns is None:
            raise RuntimeError("PipelineTimer.start() was not called")
        elapsed_ns = time.perf_counter_ns() - self._start_ns
        return elapsed_ns / 1_000_000

    @contextmanager
    def stage(self, label: str) -> Iterator[None]:
        """Time a named pipeline stage and record it."""
        start_ns = time.perf_counter_ns()
        try:
            yield
        finally:
            elapsed_ms = (time.perf_counter_ns() - start_ns) / 1_000_000
            self.stages.append(TimingResult(label=label, elapsed_ms=elapsed_ms))
