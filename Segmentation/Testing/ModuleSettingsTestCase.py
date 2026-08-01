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

    def test_target_prefix_is_stable(self):
        self.assertEqual(ModuleSettings._PREFIX, "DentoFac/Segmentation/")

    def test_fresh_installation_records_schema_without_preferences(self):
        self.assertEqual(self.backend.value(ModuleSettings.KEY_MIGRATION_VERSION), "1")
        self.assertNotIn(ModuleSettings.KEY_DEVICE, self.backend._d)

    def test_migrates_upstream_namespace_without_removing_legacy_values(self):
        backend = FakeQSettings()
        legacy = "DentalSegmentator/"
        backend.setValue(legacy + "device", "cpu")
        backend.setValue(legacy + "surfaceSmoothing", "0.25")
        backend.setValue(legacy + "exportFormats", str(ExportFormat.STL.value))
        backend.setValue(legacy + "gltfReductionFactor", "0.5")
        backend.setValue(legacy + "lastExportFolder", "/legacy/export")

        migrated = ModuleSettings(backend=backend)

        self.assertEqual(migrated.getDevice(["cuda", "cpu"], "cuda"), "cpu")
        self.assertAlmostEqual(migrated.getSurfaceSmoothing(0.0), 0.25)
        self.assertEqual(migrated.getExportFormats(ExportFormat(0)), ExportFormat.STL)
        self.assertAlmostEqual(migrated.getReductionFactor(0.0), 0.5)
        self.assertEqual(migrated.getLastExportFolder(), "/legacy/export")
        self.assertEqual(backend.value(legacy + "device"), "cpu")

    def test_migrates_phase_one_namespace_before_upstream_namespace(self):
        backend = FakeQSettings()
        phaseOne = "DentoFacSegmentator/"
        upstream = "DentalSegmentator/"
        backend.setValue(phaseOne + "device", "cpu")
        backend.setValue(upstream + "device", "cuda")

        migrated = ModuleSettings(backend=backend)

        self.assertEqual(migrated.getDevice(["cuda", "cpu"], "cuda"), "cpu")
        self.assertEqual(backend.value(upstream + "device"), "cuda")

    def test_existing_dentofac_values_win_over_both_legacy_namespaces(self):
        backend = FakeQSettings()
        backend.setValue(ModuleSettings.KEY_DEVICE, "mps")
        backend.setValue("DentoFacSegmentator/device", "cpu")
        backend.setValue("DentalSegmentator/device", "cuda")

        migrated = ModuleSettings(backend=backend)

        self.assertEqual(migrated.getDevice(["cuda", "cpu", "mps"], "cuda"), "mps")

    def test_invalid_legacy_values_are_not_migrated(self):
        backend = FakeQSettings()
        backend.setValue("DentalSegmentator/surfaceSmoothing", "not-a-number")
        backend.setValue("DentalSegmentator/exportFormats", "999")
        backend.setValue("DentalSegmentator/gltfReductionFactor", "2.0")

        migrated = ModuleSettings(backend=backend)

        self.assertAlmostEqual(migrated.getSurfaceSmoothing(0.4), 0.4)
        self.assertEqual(migrated.getExportFormats(ExportFormat.OBJ), ExportFormat.OBJ)
        self.assertAlmostEqual(migrated.getReductionFactor(0.6), 0.6)

    def test_schema_version_makes_migration_one_time(self):
        backend = FakeQSettings()
        backend.setValue("DentalSegmentator/device", "cpu")
        ModuleSettings(backend=backend)
        backend.setValue("DentoFacSegmentator/device", "cuda")

        migrated = ModuleSettings(backend=backend)

        self.assertEqual(migrated.getDevice(["cuda", "cpu"], "cuda"), "cpu")

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
