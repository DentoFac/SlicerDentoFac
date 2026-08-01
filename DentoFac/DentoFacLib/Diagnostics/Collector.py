"""Framework-neutral diagnostics envelope with workflow-provided sections."""

from __future__ import annotations

import datetime
import json
import platform
from typing import Any, Callable, Dict, List, Optional


def tail_logs(logs: List[str], max_lines: int = 100, max_bytes: int = 16384) -> List[str]:
    tailed = list(logs[-max_lines:])
    while sum(len(line) for line in tailed) > max_bytes and len(tailed) > 1:
        tailed.pop(0)
    return tailed


class DiagnosticsCollector:
    """Collect common environment facts and an optional workflow diagnostics provider."""

    def __init__(self, workflow_provider: Optional[Callable[[], Dict[str, Any]]] = None):
        self._workflow_provider = workflow_provider

    def collect(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "platform": platform.platform(), "python": __import__("sys").version.split()[0],
            "slicer_version": None, "workflow": {},
        }
        try:
            import slicer
            data["slicer_version"] = getattr(slicer.app, "applicationVersion", None)
        except (ImportError, AttributeError):
            pass
        if self._workflow_provider is not None:
            try:
                data["workflow"] = self._workflow_provider() or {}
            except Exception:
                data["workflow"] = {"collection_error": "Workflow diagnostics were unavailable."}
        return data

    @staticmethod
    def serialize_json(data: Dict[str, Any]) -> str:
        return json.dumps(data, indent=2)
