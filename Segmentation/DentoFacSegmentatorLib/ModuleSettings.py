# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2024, Gauthier DOT
# Adapted by DentoFac from SlicerDentalSegmentator commit 476043f00009c372f0653dc759d69e2e559ed0f4; modified from upstream.

import math

import qt

from .ExportManager import ExportFormat


class ModuleSettings:
    """Typed, validated persistence for DentoFac Segmentator user preferences.

    Backed by a QSettings-like object (``value(key, default)`` / ``setValue(key, value)``).
    Production uses ``qt.QSettings()``; tests inject a fake so no real settings file is touched.
    All current keys are namespaced under ``DentoFac/Segmentation/``.  Version 1
    performs a one-time, non-destructive migration from both previous namespaces;
    legacy keys are intentionally retained so the standalone extension can still
    be used after DentoFac has read its preferences.
    """

    _PREFIX = "DentoFac/Segmentation/"
    _LEGACY_PREFIXES = ("DentoFacSegmentator/", "DentalSegmentator/")
    _MIGRATION_VERSION = 1
    KEY_MIGRATION_VERSION = _PREFIX + "migrationVersion"
    KEY_DEVICE = _PREFIX + "device"
    KEY_SMOOTHING = _PREFIX + "surfaceSmoothing"
    KEY_FORMATS = _PREFIX + "exportFormats"
    KEY_REDUCTION = _PREFIX + "gltfReductionFactor"
    KEY_EXPORT_FOLDER = _PREFIX + "lastExportFolder"

    def __init__(self, backend=None):
        self._backend = backend if backend is not None else qt.QSettings()
        self._migrateLegacySettings()

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

    # --- compatibility migration --------------------------------------
    def _migrateLegacySettings(self):
        """Copy valid legacy values once, never removing or overwriting data.

        The Phase 1 namespace is consulted before the original standalone
        namespace because it is the closer predecessor.  Current DentoFac keys
        always win, including when more than one legacy namespace is populated.
        """
        if self._migrationVersion() >= self._MIGRATION_VERSION:
            return

        for key in self._settingKeys():
            if self._hasValue(key):
                continue
            suffix = key[len(self._PREFIX):]
            for legacyPrefix in self._LEGACY_PREFIXES:
                raw = self._backend.value(legacyPrefix + suffix, None)
                value = self._validMigrationValue(key, raw)
                if value is None:
                    continue
                self._setMigratedValue(key, value)
                break

        self._backend.setValue(self.KEY_MIGRATION_VERSION, str(self._MIGRATION_VERSION))

    def _migrationVersion(self):
        try:
            return int(self._backend.value(self.KEY_MIGRATION_VERSION, 0))
        except (TypeError, ValueError):
            return 0

    def _hasValue(self, key):
        contains = getattr(self._backend, "contains", None)
        if callable(contains):
            return bool(contains(key))
        missing = object()
        return self._backend.value(key, missing) is not missing

    @classmethod
    def _settingKeys(cls):
        return (
            cls.KEY_DEVICE,
            cls.KEY_SMOOTHING,
            cls.KEY_FORMATS,
            cls.KEY_REDUCTION,
            cls.KEY_EXPORT_FOLDER,
        )

    @classmethod
    def _validMigrationValue(cls, key, raw):
        if key == cls.KEY_DEVICE:
            return raw if isinstance(raw, str) and raw else None
        if key in (cls.KEY_SMOOTHING, cls.KEY_REDUCTION):
            try:
                value = float(raw)
            except (TypeError, ValueError):
                return None
            return value if math.isfinite(value) and 0.0 <= value <= 1.0 else None
        if key == cls.KEY_FORMATS:
            if isinstance(raw, bool):
                return None
            try:
                value = int(raw)
            except (TypeError, ValueError):
                return None
            validMask = 0
            for exportFormat in ExportFormat:
                validMask |= exportFormat.value
            return value if value >= 0 and not (value & ~validMask) else None
        if key == cls.KEY_EXPORT_FOLDER:
            return raw if isinstance(raw, str) else None
        return None

    def _setMigratedValue(self, key, value):
        if key == self.KEY_DEVICE:
            self.setDevice(value)
        elif key == self.KEY_SMOOTHING:
            self.setSurfaceSmoothing(value)
        elif key == self.KEY_FORMATS:
            self.setExportFormats(ExportFormat(value))
        elif key == self.KEY_REDUCTION:
            self.setReductionFactor(value)
        elif key == self.KEY_EXPORT_FOLDER:
            self.setLastExportFolder(value)

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
