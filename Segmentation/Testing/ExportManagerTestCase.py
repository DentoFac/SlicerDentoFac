# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2024, Gauthier DOT
# Adapted by DentoFac from SlicerDentalSegmentator commit 476043f00009c372f0653dc759d69e2e559ed0f4; modified from upstream.

import os
import pathlib
import sys
import tempfile
import types
import unittest
from unittest import mock

import pytest

# Register the headless qt/slicer/SegmentationWidget stubs before importing the package.
# See Testing/_headless_stubs.py — a no-op under a real Slicer, order-independent across the
# pure suites.
from ._headless_stubs import install as _install_headless_stubs
_install_headless_stubs()

from DentoFacSegmentatorLib.ExportManager import ExportManager, ExportFormat

class ExportManagerTestCase(unittest.TestCase):
    def test_export_format_identity_and_math(self):
        self.assertFalse(ExportFormat(0))
        combined = ExportFormat.STL | ExportFormat.OBJ
        self.assertIn(ExportFormat.STL, combined)
        self.assertIn(ExportFormat.OBJ, combined)
        self.assertNotIn(ExportFormat.GLTF, combined)

    def test_gltf_no_internet_aborts_install(self):
        manager = ExportManager(hasInternetConnectionF=lambda: False)

        error_calls = []
        def fake_errorDisplay(*args):
            error_calls.append(args)

        with mock.patch("slicer.util.errorDisplay", fake_errorDisplay):
            with mock.patch.dict(sys.modules, {'OpenAnatomyExport': None}):
                manager.exportSegmentation("node", "path", ExportFormat.GLTF)

        self.assertEqual(len(error_calls), 1)
        self.assertIn("SlicerOpenAnatomy extension", error_calls[0][0])

    @pytest.mark.baseline_slicer_runtime_quarantine
    def test_gltf_install_retry_path(self):
        manager = ExportManager(hasInternetConnectionF=lambda: True)

        install_called = []
        @classmethod
        def fake_install(cls):
            install_called.append(True)

        call_count = [0]
        class FakeLogic:
            def exportModel(self, *args):
                pass

        class FakeModule(types.ModuleType):
            def __getattr__(self, name):
                if name == "OpenAnatomyExportLogic":
                    call_count[0] += 1
                    if call_count[0] == 1:
                        raise ImportError("First time fails")
                    return FakeLogic
                raise AttributeError(name)

        sys.modules['OpenAnatomyExport'] = FakeModule("OpenAnatomyExport")

        with mock.patch.object(ExportManager, "_installOpenAnatomyExtension", fake_install):
            manager.exportSegmentation("node", "path", ExportFormat.GLTF)

        self.assertEqual(len(install_called), 1)
        self.assertEqual(call_count[0], 2)

        del sys.modules['OpenAnatomyExport']

    @pytest.mark.baseline_slicer_runtime_quarantine
    def test_format_dispatch(self):
        manager = ExportManager()

        closed_surface_calls = []
        labelmap_calls = []

        def fake_closed(*args):
            closed_surface_calls.append(args[3])

        def fake_labelmap(*args):
            labelmap_calls.append(args[3])

        import slicer
        with mock.patch.object(slicer.vtkSlicerSegmentationsModuleLogic, "ExportSegmentsClosedSurfaceRepresentationToFiles", fake_closed), \
             mock.patch.object(slicer.vtkSlicerSegmentationsModuleLogic, "ExportSegmentsBinaryLabelmapRepresentationToFiles", fake_labelmap), \
             mock.patch.object(manager, "_exportToGLTF") as mock_gltf:

             formats = ExportFormat.STL | ExportFormat.OBJ | ExportFormat.NIFTI | ExportFormat.GLTF
             manager.exportSegmentation("node", "path", formats)

             self.assertEqual(closed_surface_calls, ["STL", "OBJ"])
             self.assertEqual(labelmap_calls, ["nii.gz"])
             mock_gltf.assert_called_once_with("node", "path", 0.0)

    @pytest.mark.baseline_slicer_runtime_quarantine
    def test_export_returns_written_files(self):
        manager = ExportManager()
        with tempfile.TemporaryDirectory() as tmp:
            import slicer

            def fake_closed(*args):
                (pathlib.Path(tmp) / f"Segment_1.{args[3].lower()}").touch()

            def fake_labelmap(*args):
                (pathlib.Path(tmp) / "seg.nii.gz").touch()

            def fake_gltf(*args):
                (pathlib.Path(tmp) / "model.gltf").touch()
                (pathlib.Path(tmp) / "model.bin").touch()

            with mock.patch.object(slicer.vtkSlicerSegmentationsModuleLogic, "ExportSegmentsClosedSurfaceRepresentationToFiles", fake_closed), \
                 mock.patch.object(slicer.vtkSlicerSegmentationsModuleLogic, "ExportSegmentsBinaryLabelmapRepresentationToFiles", fake_labelmap), \
                 mock.patch.object(manager, "_exportToGLTF", fake_gltf):

                 formats = ExportFormat.STL | ExportFormat.OBJ | ExportFormat.NIFTI | ExportFormat.GLTF
                 written = manager.exportSegmentation("node", tmp, formats)
                 self.assertEqual(written, sorted(["Segment_1.stl", "Segment_1.obj", "seg.nii.gz", "model.gltf", "model.bin"]))

    @pytest.mark.baseline_slicer_runtime_quarantine
    def test_export_overwrite_is_detected(self):
        manager = ExportManager()
        with tempfile.TemporaryDirectory() as tmp:
            import slicer

            p = pathlib.Path(tmp) / "Segment_1.stl"
            p.write_text("old")

            def fake_closed(*args):
                p.write_text("new content")

            with mock.patch.object(slicer.vtkSlicerSegmentationsModuleLogic, "ExportSegmentsClosedSurfaceRepresentationToFiles", fake_closed):
                 written = manager.exportSegmentation("node", tmp, ExportFormat.STL)
                 self.assertEqual(written, ["Segment_1.stl"])

    @pytest.mark.baseline_slicer_runtime_quarantine
    def test_export_no_op_returns_empty(self):
        manager = ExportManager()
        with tempfile.TemporaryDirectory() as tmp:
            import slicer

            def fake_closed(*args):
                pass

            with mock.patch.object(slicer.vtkSlicerSegmentationsModuleLogic, "ExportSegmentsClosedSurfaceRepresentationToFiles", fake_closed):
                 written = manager.exportSegmentation("node", tmp, ExportFormat.STL)
                 self.assertEqual(written, [])

    @pytest.mark.baseline_slicer_runtime_quarantine
    def test_is_open_anatomy_available(self):
        with mock.patch.dict(sys.modules, {'OpenAnatomyExport': types.ModuleType('OpenAnatomyExport')}):
            self.assertTrue(ExportManager.isOpenAnatomyAvailable())

        import slicer
        mock_mgr = mock.MagicMock()
        mock_mgr.isExtensionInstalled.return_value = True
        # Patch (don't assign) so the shared module-level slicer stub is restored
        # afterwards and this test can't leak state into others in the same process.
        with mock.patch.object(slicer.app, "extensionsManagerModel", return_value=mock_mgr, create=True):
            # Extension installed but module is not loaded yet (import raises ImportError).
            with mock.patch.dict(sys.modules, {'OpenAnatomyExport': None}):
                self.assertTrue(ExportManager.isOpenAnatomyAvailable())

            mock_mgr.isExtensionInstalled.return_value = False
            with mock.patch.dict(sys.modules, {'OpenAnatomyExport': None}):
                self.assertFalse(ExportManager.isOpenAnatomyAvailable())
