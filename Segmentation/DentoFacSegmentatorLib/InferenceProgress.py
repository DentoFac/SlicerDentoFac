# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2024, Gauthier DOT
# Adapted by DentoFac from SlicerDentalSegmentator commit 476043f00009c372f0653dc759d69e2e559ed0f4; modified from upstream.

"""Best-effort parsing and formatting for nnU-Net inference progress output.

The nnU-Net command-line output is not a public API and varies slightly between
versions.  Keep its parsing isolated here so the UI can always safely fall back
to a stage-only, indeterminate progress display.
"""

from dataclasses import dataclass
import re
from typing import Optional


@dataclass(frozen=True)
class ProgressUpdate:
    """A coarse inference stage and, when available, its progress fraction."""

    stage: str
    fraction: Optional[float] = None


@dataclass(frozen=True)
class ProgressState:
    """A UI-ready snapshot of the best-effort inference progress state."""

    stage: Optional[str]
    fraction: Optional[float]
    fraction_samples: int
    eta_minutes: Optional[int]

    @property
    def is_determinate(self) -> bool:
        return self.fraction is not None


class ProgressTracker:
    """Pure reducer for coarse stage, progress, and deliberately rough ETA state.

    ETA is calculated from the elapsed time at which the latest fraction was
    observed.  It therefore remains stable between sparse nnU-Net progress
    lines instead of drifting upward on every UI timer tick.
    """

    def __init__(self):
        self.reset()

    def reset(self):
        self._stage = None
        self._fraction = None
        self._fraction_samples = 0
        self._fraction_observed_elapsed = None

    def apply(self, update: ProgressUpdate, elapsed: float) -> ProgressState:
        """Incorporate one parsed update and return the resulting snapshot."""
        if update.stage != self._stage:
            self._stage = update.stage
            self._clear_fraction()

        if update.fraction is None or not 0.0 <= update.fraction <= 1.0:
            # A stage-only update must not leave a stale determinate percentage
            # or ETA visible from previous output.
            self._clear_fraction()
            return self.snapshot(elapsed)

        previous_fraction = self._fraction
        self._fraction = update.fraction
        if previous_fraction is None or update.fraction < previous_fraction:
            self._fraction_samples = 1
        else:
            self._fraction_samples += 1
        self._fraction_observed_elapsed = max(0.0, elapsed)
        return self.snapshot(elapsed)

    def snapshot(self, elapsed: float) -> ProgressState:
        """Return current state at ``elapsed`` seconds without changing it."""
        elapsed = max(0.0, elapsed)
        eta_minutes = None
        if (
            self._fraction is not None
            and 0.0 < self._fraction < 1.0
            and self._fraction_samples >= 2
            and elapsed >= 10.0
            and self._fraction_observed_elapsed is not None
        ):
            # Anchor to the observation time, rather than current elapsed time:
            # no new model progress means no new ETA estimate.
            remaining_seconds = (
                self._fraction_observed_elapsed * (1 - self._fraction) / self._fraction
            )
            eta_minutes = max(1, int(round(remaining_seconds / 60)))
        return ProgressState(
            stage=self._stage,
            fraction=self._fraction,
            fraction_samples=self._fraction_samples,
            eta_minutes=eta_minutes,
        )

    def _clear_fraction(self):
        self._fraction = None
        self._fraction_samples = 0
        self._fraction_observed_elapsed = None


_PERCENT_RE = re.compile(r"(?<![\d.])(\d+(?:\.\d+)?)\s*%")
_PREPROCESSING_RE = re.compile(r"\bpre[- ]?processing\b")
_PREDICTING_RE = re.compile(r"\b(?:predicting|prediction|sliding[- ]window)\b")
_POSTPROCESSING_RE = re.compile(r"\b(?:post[- ]?processing|exporting(?:\s+segmentation)?)\b")


def _fraction_from_percent(log_line: str) -> Optional[float]:
    match = _PERCENT_RE.search(log_line)
    if not match:
        return None

    percent = float(match.group(1))
    # Ignore malformed values instead of clamping them: a value greater than
    # 100 is much more likely unrelated output than useful inference progress.
    return percent / 100.0 if 0.0 <= percent <= 100.0 else None


def parseProgress(logLine: str) -> Optional[ProgressUpdate]:
    """Parse a single nnU-Net log line into a coarse progress update.

    A bare tqdm percentage has no stage text, but during inference it is the
    sliding-window prediction progress emitted by nnU-Net, so it is treated as
    ``Predicting``.  Unknown lines deliberately return ``None``.
    """
    if not isinstance(logLine, str):
        return None

    log_line = logLine.strip()
    if not log_line:
        return None

    lower_line = log_line.lower()
    fraction = _fraction_from_percent(log_line)
    if _PREPROCESSING_RE.search(lower_line):
        return ProgressUpdate("Preprocessing", fraction)
    if _POSTPROCESSING_RE.search(lower_line):
        return ProgressUpdate("Post-processing", fraction)
    if _PREDICTING_RE.search(lower_line):
        return ProgressUpdate("Predicting", fraction)
    if fraction is not None:
        return ProgressUpdate("Predicting", fraction)
    return None


def formatElapsedTime(seconds: float) -> str:
    """Format elapsed seconds as ``mm:ss`` or ``h:mm:ss`` for the UI."""
    total_seconds = max(0, int(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"
