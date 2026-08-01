# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2024, Gauthier DOT
# Adapted by DentoFac from SlicerDentalSegmentator commit 476043f00009c372f0653dc759d69e2e559ed0f4; modified from upstream.

import unittest

from ._headless_stubs import install as _install
_install()

from DentoFacSegmentatorLib.ModuleSettings import ModuleSettings
from DentoFacSegmentatorLib.ExportManager import ExportFormat


class FakeQSettings:
    """Dict-backed stand-in for qt.QSettings (value/setValue only)."""
    def __init__(self):
        self._d = {}

    def value(self, key, default=None):
        return self._d.get(key, default)

    def setValue(self, key, value):
        self._d[key] = value


class ModuleSettingsTestCase(unittest.TestCase):
    def setUp(self):
        self.backend = FakeQSettings()
        self.settings = ModuleSettings(backend=self.backend)

    def test_device_roundtrip(self):
        self.settings.setDevice("cpu")
        self.assertEqual(self.settings.getDevice(["cuda", "cpu", "mps"], "cuda"), "cpu")

    def test_device_default_when_unset(self):
        self.assertEqual(self.settings.getDevice(["cuda", "cpu", "mps"], "cuda"), "cuda")

    def test_device_invalid_choice_falls_back(self):
        self.settings.setDevice("invalid_device")
        self.assertEqual(self.settings.getDevice(["cuda", "cpu", "mps"], "cuda"), "cuda")

    def test_surface_smoothing_roundtrip(self):
        self.settings.setSurfaceSmoothing(0.8)
        self.assertAlmostEqual(self.settings.getSurfaceSmoothing(0.5), 0.8)

    def test_surface_smoothing_clamps(self):
        self.settings.setSurfaceSmoothing(1.5)
        self.assertAlmostEqual(self.settings.getSurfaceSmoothing(0.5), 1.0)
        self.settings.setSurfaceSmoothing(-0.2)
        self.assertAlmostEqual(self.settings.getSurfaceSmoothing(0.5), 0.0)

    def test_surface_smoothing_invalid_type_falls_back(self):
        self.backend.setValue(self.settings.KEY_SMOOTHING, "abc")
        self.assertAlmostEqual(self.settings.getSurfaceSmoothing(0.5), 0.5)

    def test_export_formats_roundtrip(self):
        formats = ExportFormat.STL | ExportFormat.GLTF
        self.settings.setExportFormats(formats)
        self.assertEqual(self.settings.getExportFormats(ExportFormat.OBJ), formats)

    def test_export_formats_all_unchecked_persists(self):
        self.settings.setExportFormats(ExportFormat(0))
        self.assertEqual(self.settings.getExportFormats(ExportFormat.OBJ), ExportFormat(0))

    def test_export_formats_corrupt_key_falls_back(self):
        self.backend.setValue(self.settings.KEY_FORMATS, "invalid")
        self.assertEqual(self.settings.getExportFormats(ExportFormat.OBJ), ExportFormat.OBJ)

    def test_reduction_factor_roundtrip(self):
        self.settings.setReductionFactor(0.4)
        self.assertAlmostEqual(self.settings.getReductionFactor(0.9), 0.4)

    def test_last_export_folder_roundtrip(self):
        self.settings.setLastExportFolder("/test/path")
        self.assertEqual(self.settings.getLastExportFolder("/default/path"), "/test/path")

    def test_last_export_folder_default_when_unset(self):
        self.assertEqual(self.settings.getLastExportFolder("/default/path"), "/default/path")


if __name__ == '__main__':
    unittest.main()
