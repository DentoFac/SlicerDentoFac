# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2024, Gauthier DOT
# Adapted by DentoFac from SlicerDentalSegmentator commit 476043f00009c372f0653dc759d69e2e559ed0f4; modified from upstream.

import qt

from .ExportManager import ExportFormat


class ModuleSettings:
    """Typed, validated persistence for DentoFacSegmentator user preferences.

    Backed by a QSettings-like object (``value(key, default)`` / ``setValue(key, value)``).
    Production uses ``qt.QSettings()``; tests inject a fake so no real settings file is touched.
    All keys are namespaced under ``DentoFacSegmentator/`` to avoid collisions with other modules.
    """

    _PREFIX = "DentoFacSegmentator/"
    KEY_DEVICE = _PREFIX + "device"
    KEY_SMOOTHING = _PREFIX + "surfaceSmoothing"
    KEY_FORMATS = _PREFIX + "exportFormats"
    KEY_REDUCTION = _PREFIX + "gltfReductionFactor"
    KEY_EXPORT_FOLDER = _PREFIX + "lastExportFolder"

    def __init__(self, backend=None):
        self._backend = backend if backend is not None else qt.QSettings()

    # --- device ---------------------------------------------------------
    def getDevice(self, validChoices, default):
        value = self._readStr(self.KEY_DEVICE, default)
        return value if value in validChoices else default

    def setDevice(self, value):
        self._backend.setValue(self.KEY_DEVICE, str(value))

    # --- surface smoothing ---------------------------------------------
    def getSurfaceSmoothing(self, default):
        return self._readFloat(self.KEY_SMOOTHING, default, 0.0, 1.0)

    def setSurfaceSmoothing(self, value):
        self._backend.setValue(self.KEY_SMOOTHING, str(float(value)))

    # --- export formats (stored as the ExportFormat flag's int) ---------
    def getExportFormats(self, default):
        raw = self._backend.value(self.KEY_FORMATS, None)
        if raw is None:
            return default
        try:
            return ExportFormat(int(raw))
        except (ValueError, TypeError):
            return default

    def setExportFormats(self, formats):
        self._backend.setValue(self.KEY_FORMATS, str(int(formats.value)))

    # --- glTF reduction factor -----------------------------------------
    def getReductionFactor(self, default):
        return self._readFloat(self.KEY_REDUCTION, default, 0.0, 1.0)

    def setReductionFactor(self, value):
        self._backend.setValue(self.KEY_REDUCTION, str(float(value)))

    # --- last export folder --------------------------------------------
    def getLastExportFolder(self, default=""):
        return self._readStr(self.KEY_EXPORT_FOLDER, default)

    def setLastExportFolder(self, value):
        self._backend.setValue(self.KEY_EXPORT_FOLDER, str(value))

    # --- helpers --------------------------------------------------------
    def _readStr(self, key, default):
        raw = self._backend.value(key, default)
        return str(raw) if raw is not None else default

    def _readFloat(self, key, default, lo, hi):
        raw = self._backend.value(key, None)
        if raw is None:
            return default
        try:
            value = float(raw)
        except (ValueError, TypeError):
            return default
        return min(max(value, lo), hi)
