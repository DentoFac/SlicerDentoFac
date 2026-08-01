"""Small, read-only runtime facts used by the initial DentoFac Hub."""

from dataclasses import dataclass
import sys
from typing import Optional


@dataclass(frozen=True)
class RuntimeStatus:
    python_version: str
    slicer_version: Optional[str]


def collect_runtime_status() -> RuntimeStatus:
    slicer_version = None
    try:
        import slicer

        slicer_version = getattr(slicer.app, "applicationVersion", None)
    except (ImportError, AttributeError):
        pass

    return RuntimeStatus(
        python_version=sys.version.split()[0],
        slicer_version=slicer_version,
    )
