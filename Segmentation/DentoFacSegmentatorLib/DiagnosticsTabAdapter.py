"""Compatibility adapter for Slicer's optional shared Help/Acknowledgement tabs.

Slicer does not expose this tab widget through a public API.  Keeping the object
name and lookup here makes that private integration explicit and gives the module
host one safe fallback: show diagnostics inline when the widget is unavailable.
"""

from __future__ import annotations

from typing import Optional

import qt
import slicer


class DiagnosticsTabAdapter:
    """Locate the optional shared diagnostics host without making it required."""

    _HELP_ACKNOWLEDGEMENT_TABS_OBJECT_NAME = "HelpAcknowledgementTabWidget"

    @classmethod
    def find_shared_tabs(cls) -> Optional[qt.QTabWidget]:
        try:
            main_window = slicer.util.mainWindow()
            if main_window is None:
                return None
            return main_window.findChild(
                qt.QTabWidget, cls._HELP_ACKNOWLEDGEMENT_TABS_OBJECT_NAME
            )
        except (AttributeError, RuntimeError):
            return None
