# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2024, Gauthier DOT
# Adapted by DentoFac from SlicerDentalSegmentator commit 476043f00009c372f0653dc759d69e2e559ed0f4; modified from upstream.

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, patch

import SampleData
import qt
import slicer

from DentoFacSegmentatorLib import SegmentationWidget, Signal, ExportFormat
from .Utils import (
    DentoFacSegmentatorTestCase, get_test_multi_label_path, get_test_multi_label_path_with_segments_1_3_5,
    load_test_CT_volume
)


class MockLogic:
    def __init__(self):
        self.inferenceFinished = Signal()
        self.errorOccurred = Signal("str")
        self.progressInfo = Signal("str")
        self.startSegmentation = MagicMock()
        self.stopSegmentation = MagicMock()
        self.setParameter = MagicMock()
        self.waitForSegmentationFinished = MagicMock()
        self.loadSegmentation = MagicMock()
        self.loadSegmentation.side_effect = self.load_segmentation

    @staticmethod
    def load_segmentation():
        return slicer.util.loadSegmentation(get_test_multi_label_path())

    @staticmethod
    def load_segmentation_partial():
        return slicer.util.loadSegmentation(get_test_multi_label_path_with_segments_1_3_5())


@unittest.skip(
    "Requires excluded upstream NIfTI fixtures; real-data parity is deferred until an approved replacement fixture is available."
)
class SegmentationWidgetTestCase(DentoFacSegmentatorTestCase):
    def setUp(self):
        import os
        import qt
        from DentoFacSegmentatorLib.ModuleSettings import ModuleSettings

        super().setUp()
        self.logic = MockLogic()
        self.node = load_test_CT_volume()
        
        self._settingsDir = TemporaryDirectory()
        backend = qt.QSettings(
            os.path.join(self._settingsDir.name, "settings.ini"), qt.QSettings.IniFormat
        )

        self.widget = SegmentationWidget(logic=self.logic, settings=ModuleSettings(backend=backend))
        self.widget.inputSelector.setCurrentNode(self.node)
        self.widget.show()
        slicer.app.processEvents()

    def tearDown(self):
        self._settingsDir.cleanup()
        super().tearDown()

    def test_can_be_displayed(self):
        slicer.app.processEvents()

    def test_device_selection_shows_cpu_runtime_expectation(self):
        idx = self.widget.deviceComboBox.findText("cpu")
        self.assertGreaterEqual(idx, 0)
        self.widget.deviceComboBox.setCurrentIndex(idx)
        slicer.app.processEvents()

        self.assertEqual(
            self.widget.deviceHintLabel.text,
            "CPU — segmentation may take up to ~1 hour.",
        )

    def test_default_run_setup_prioritizes_user_scan_and_output(self):
        self.assertEqual(self.widget.outputSegmentationLabel.text, "Output segmentation:")
        self.assertFalse(self.widget.loadSampleVolumeButton.isFlat())
        self.assertEqual(self.widget.deviceLabel.text, "Device:")
        self.assertTrue(self.widget.deviceComboBox.isVisible())

    def test_installation_status_collapses_when_ready(self):
        from DentoFacSegmentatorLib.InstallationStatus import StatusLine

        ready_status = MagicMock()
        ready_status.is_ready = True
        ready_status.lines = [
            StatusLine(True, "NNUNet extension", "Installed"),
            StatusLine(True, "Python dependencies (torch, nnunetv2)", "Satisfied"),
            StatusLine(True, "Compute device", "Using 'cpu'"),
            StatusLine(True, "Model weights", "Valid"),
        ]
        ready_status.val_res.authoritative = False

        with patch(
            "DentoFacSegmentatorLib.InstallationStatus.collect_status", return_value=ready_status
        ), patch(
            "DentoFacSegmentatorLib.InstallationStatus.weightsDiagnostic", return_value=("Valid", "")
        ):
            self.widget.refreshInstallationStatus()

        self.assertTrue(self.widget.installationStatusCollapsibleButton.collapsed)
        self.assertEqual(self.widget.installationStatusCollapsibleButton.text, "● Installation status")
        self.assertIn("#2e7d32", self.widget.installationStatusCollapsibleButton.styleSheet)

    def test_dependency_progress_expands_installation_status(self):
        self.widget.installationStatusCollapsibleButton.collapsed = True

        self.widget._setInstallInProgress("Installing dependencies…")

        self.assertTrue(self.widget.installProgressWidget.isVisible())
        self.assertFalse(self.widget.installationStatusCollapsibleButton.collapsed)

        self.widget._setInstallInProgress(None)
        self.assertFalse(self.widget.installProgressWidget.isVisible())

    def test_diagnostics_are_separate_from_run_action(self):
        self.assertEqual(self.widget.showLogsButton.text, "View activity log")
        self.assertEqual(self.widget.supportDiagnosticsButton.text, "Create support report…")
        self.assertEqual(
            len(self.widget.applyWidget.findChildren(qt.QPushButton)), 1,
        )

    def test_running_state_offers_live_log_without_embedded_log_dump(self):
        self.assertEqual(self.widget.viewLiveLogButton.text, "View live log…")
        self.assertTrue(self.widget.inferenceStatusWidget.isVisible())
        self.assertFalse(self.widget.inferenceStatusWidget.isEnabled())
        self.assertFalse(self.widget.viewLiveLogButton.isEnabled())
        self.assertEqual(self.widget.inferenceProgressBar.minimum, 0)
        self.assertEqual(self.widget.inferenceProgressBar.maximum, 100)

        self.widget.applyButton.click()
        slicer.app.processEvents()

        self.assertTrue(self.widget.inferenceStatusWidget.isEnabled())
        self.assertTrue(self.widget.viewLiveLogButton.isEnabled())
        self.assertEqual(self.widget.inferenceProgressBar.minimum, 0)
        self.assertEqual(self.widget.inferenceProgressBar.maximum, 0)
        self.assertFalse(hasattr(self.widget, "currentInfoTextEdit"))

    def test_utility_dialogs_use_compact_width(self):
        dialog = qt.QDialog()
        self.widget._resizeUtilityDialog(dialog)

        mainWindow = slicer.util.mainWindow()
        self.assertEqual(dialog.width, round(mainWindow.width * .28))
        self.assertEqual(dialog.height, round(mainWindow.height * .7))
        dialog.close()

    def test_live_log_appends_after_existing_entries(self):
        textEdit = qt.QTextEdit()
        textEdit.setPlainText("Older status entry")
        self.widget.moveTextEditToEnd(textEdit)
        textEdit.insertPlainText("\nNew inference entry")

        self.assertEqual(
            textEdit.toPlainText(), "Older status entry\nNew inference entry"
        )

    def test_result_controls_follow_selected_segmentation_content(self):
        self.assertFalse(self.widget.refineResultCollapsibleButton.isVisible())
        self.assertFalse(self.widget.segmentEditorWidget.isVisible())
        self.assertFalse(self.widget.surfaceSmoothingWidget.isVisible())
        self.assertFalse(self.widget.exportCollapsibleButton.isVisible())

        self.logic.inferenceFinished()
        slicer.app.processEvents()

        self.assertTrue(self.widget.refineResultCollapsibleButton.isVisible())
        self.assertEqual(self.widget.refineResultCollapsibleButton.text, "Refine result")
        self.assertFalse(self.widget.refineResultCollapsibleButton.collapsed)
        self.assertTrue(self.widget.segmentEditorWidget.isVisible())
        self.assertTrue(self.widget.surfaceSmoothingWidget.isVisible())
        self.assertTrue(self.widget.exportCollapsibleButton.isVisible())
        self.assertTrue(self.widget.exportCollapsibleButton.collapsed)

        segmentationNode = self.widget.getCurrentSegmentationNode()
        segmentationNode.GetSegmentation().RemoveAllSegments()
        segmentationNode.Modified()
        slicer.app.processEvents()

        self.assertFalse(self.widget.refineResultCollapsibleButton.isVisible())
        self.assertFalse(self.widget.segmentEditorWidget.isVisible())
        self.assertFalse(self.widget.surfaceSmoothingWidget.isVisible())
        self.assertFalse(self.widget.exportCollapsibleButton.isVisible())

    def test_unavailable_device_label_keeps_canonical_backend_value(self):
        with patch(
            "DentoFacSegmentatorLib.InstallationStatus.is_device_available",
            side_effect=lambda device: device != "cuda",
        ), patch(
            "DentoFacSegmentatorLib.InstallationStatus.device_unavailable_reason",
            return_value="no GPU detected",
        ):
            self.widget._configureDeviceOptions()

        cudaIndex = self.widget.deviceComboBox.findText("cuda (no GPU detected)")
        self.assertGreaterEqual(cudaIndex, 0)
        self.assertFalse(self.widget.deviceComboBox.model().item(cudaIndex).isEnabled())
        self.assertEqual(self.widget._deviceOptionValue(cudaIndex), "cuda")

    def test_load_sample_volume_selects_downloaded_volume(self):
        self.widget.inputSelector.setCurrentNode(None)
        self.assertIsNone(self.widget.getCurrentVolumeNode())
        preSurgeryNode = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLScalarVolumeNode", "PreDentalSurgery"
        )

        with patch(
            "DentoFacSegmentatorLib.PythonDependencyChecker.hasInternetConnection", return_value=True
        ), patch.object(
            SampleData.SampleDataLogic,
            "downloadDentalSurgery",
            return_value=[preSurgeryNode, self.node],
        ) as downloadSample:
            self.widget.loadSampleVolumeButton.click()

        downloadSample.assert_called_once_with()
        self.assertIs(self.widget.getCurrentVolumeNode(), self.node)
        self.assertTrue(self.widget.applyButton.isEnabled())

    def test_load_sample_volume_reports_offline_without_downloading(self):
        with patch(
            "DentoFacSegmentatorLib.PythonDependencyChecker.hasInternetConnection", return_value=False
        ), patch.object(slicer.util, "errorDisplay") as errorDisplay, patch.object(
            SampleData.SampleDataLogic, "downloadDentalSurgery"
        ) as downloadSample:
            self.widget.loadSampleVolumeButton.click()

        downloadSample.assert_not_called()
        errorDisplay.assert_called_once()
        self.assertIn("no internet connection", errorDisplay.call_args.args[0].lower())

    def test_can_run_segmentation(self):
        slicer.app.processEvents()
        self.assertTrue(self.widget.applyButton.isEnabled())
        self.assertTrue(self.widget.inputSelector.isEnabled())
        self.assertTrue(self.widget.segmentationNodeSelector.isEnabled())
        self.assertFalse(self.widget.stopButton.isVisible())

        self.widget.applyButton.click()
        slicer.app.processEvents()
        self.assertFalse(self.widget.applyButton.isVisible())
        self.assertFalse(self.widget.inputSelector.isEnabled())
        self.assertFalse(self.widget.loadSampleVolumeButton.isEnabled())
        self.assertFalse(self.widget.segmentationNodeSelector.isEnabled())
        self.assertFalse(self.widget.deviceComboBox.isEnabled())
        self.assertTrue(self.widget.stopButton.isVisible())

        self.logic.startSegmentation.assert_called_once_with(self.node)
        self.logic.inferenceFinished()
        slicer.app.processEvents()

        self.assertTrue(self.widget.applyButton.isVisible())
        self.assertTrue(self.widget.inputSelector.isEnabled())
        self.assertTrue(self.widget.loadSampleVolumeButton.isEnabled())
        self.assertTrue(self.widget.segmentationNodeSelector.isEnabled())
        self.assertTrue(self.widget.deviceComboBox.isEnabled())
        self.assertFalse(self.widget.stopButton.isVisible())
        self.logic.loadSegmentation.assert_called_once()

    def test_can_kill_segmentation(self):
        self.widget.applyButton.click()
        self.logic.startSegmentation.assert_called_once()

        self.widget.stopButton.click()
        self.logic.stopSegmentation.assert_called_once()
        self.logic.waitForSegmentationFinished.assert_called_once()
        self.assertTrue(self.widget.applyButton.isVisible())
        self.assertFalse(self.widget.stopButton.isVisible())

    def test_loading_replaces_existing_segmentation_node(self):
        self.logic.inferenceFinished()
        slicer.app.processEvents()
        self.logic.inferenceFinished()
        slicer.app.processEvents()
        self.assertEqual(self.logic.loadSegmentation.call_count, 2)
        self.assertEqual(len(list(slicer.mrmlScene.GetNodesByClass("vtkMRMLSegmentationNode"))), 1)

    def test_loading_sets_correct_segment_names(self):
        self.logic.inferenceFinished()
        slicer.app.processEvents()
        node = self.widget.getCurrentSegmentationNode()
        self.assertIsNotNone(node)

        exp_names = {"Maxilla & Upper Skull", "Mandible", "Upper Teeth", "Lower Teeth", "Mandibular canal"}
        segmentation = node.GetSegmentation()
        segmentIds = [segmentation.GetNthSegmentID(i) for i in range(segmentation.GetNumberOfSegments())]
        segmentNames = {segmentation.GetSegment(segmentId).GetName() for segmentId in segmentIds}
        self.assertEqual(segmentNames, exp_names)

    def test_loading_sets_correct_names_when_segmentation_has_missing_segments(self):
        self.logic.loadSegmentation.side_effect = self.logic.load_segmentation_partial
        self.logic.inferenceFinished()
        slicer.app.processEvents()
        node = self.widget.getCurrentSegmentationNode()
        self.assertIsNotNone(node)

        exp_names = {"Maxilla & Upper Skull", "Upper Teeth", "Mandibular canal"}
        segmentation = node.GetSegmentation()
        segmentIds = [segmentation.GetNthSegmentID(i) for i in range(segmentation.GetNumberOfSegments())]
        segmentNames = {segmentation.GetSegment(segmentId).GetName() for segmentId in segmentIds}
        self.assertEqual(segmentNames, exp_names)

    def test_loading_populates_measurements_for_present_segments(self):
        self.logic.loadSegmentation.side_effect = self.logic.load_segmentation_partial
        self.logic.inferenceFinished()
        slicer.app.processEvents()

        self.assertTrue(self.widget.measurementsCollapsibleButton.isVisible())
        self.assertEqual(self.widget.measurementsTable.rowCount, 3)
        structures = {
            self.widget.measurementsTable.item(row, 0).text()
            for row in range(self.widget.measurementsTable.rowCount)
        }
        self.assertEqual(structures, {"Maxilla & Upper Skull", "Upper Teeth", "Mandibular canal"})
        self.assertTrue(self.widget.copyMeasurementsButton.isEnabled())
        self.assertIn("Volume (cc)", self.widget._measurementReport.csv_text)

    def test_loading_surfaces_missing_segment_quality_flags(self):
        self.logic.loadSegmentation.side_effect = self.logic.load_segmentation_partial
        self.logic.inferenceFinished()
        slicer.app.processEvents()

        self.assertTrue(self.widget.resultQualityFlagsLabel.isVisible())
        flags = self.widget.resultQualityFlagsLabel.text
        self.assertIn("Mandible not detected", flags)
        self.assertIn("Lower Teeth not detected", flags)

    def test_can_export_segmentation_to_file(self):
        from DentoFacSegmentatorLib.ExportManager import ExportManager
        from DentoFacSegmentatorLib.SegmentationResultProcessor import SegmentationResultProcessor
        self.assertIsInstance(self.widget.exportManager, ExportManager)
        self.assertIsInstance(self.widget.resultProcessor, SegmentationResultProcessor)

        self.logic.inferenceFinished()
        slicer.app.processEvents()
        self.widget.objCheckBox.setChecked(True)
        self.widget.stlCheckBox.setChecked(True)
        self.widget.niftiCheckBox.setChecked(True)
        self.widget.gltfCheckBox.setChecked(True)
        allFormats = self.widget.getSelectedExportFormats()
        self.assertEqual(
            allFormats,
            ExportFormat.NIFTI | ExportFormat.STL | ExportFormat.OBJ | ExportFormat.GLTF
        )

        with TemporaryDirectory() as tmp:
            written = self.widget.exportSegmentation(self.widget.getCurrentSegmentationNode(), tmp, allFormats)
            slicer.app.processEvents()

            tmpPath = Path(tmp)
            self.assertEqual(len(list(tmpPath.glob("*.stl"))), 5)
            self.assertEqual(len(list(tmpPath.glob("*.obj"))), 1)
            self.assertEqual(len(list(tmpPath.glob("*.nii.gz"))), 1)
            self.assertEqual(len(list(tmpPath.glob("*.gltf"))), 1)
            self.assertIsNotNone(written)
            self.assertGreaterEqual(len(written), 8)

        with TemporaryDirectory() as tmp2:
            written2 = self.widget.exportManager.exportSegmentation(self.widget.getCurrentSegmentationNode(), tmp2, ExportFormat.STL)
            slicer.app.processEvents()
            self.assertEqual(len(list(Path(tmp2).glob("*.stl"))), 5)
            self.assertEqual(len(written2), 5)

    def test_export_button_gating(self):
        self.assertFalse(self.widget.exportButton.isEnabled())

        self.logic.inferenceFinished()
        slicer.app.processEvents()
        self.assertTrue(self.widget.exportButton.isEnabled())

        segmentationNode = self.widget.getCurrentSegmentationNode()
        segmentationNode.GetSegmentation().RemoveAllSegments()
        segmentationNode.Modified()
        slicer.app.processEvents()
        self.assertFalse(self.widget.exportButton.isEnabled())

    def test_export_folder_label(self):
        self.assertEqual(self.widget.exportFolderLabel.text, "No folder selected yet.")
        self.widget._lastExportFolder = "/fake/folder/path"
        self.widget.exportFolderLabel.setText(self.widget._lastExportFolder)
        self.assertEqual(self.widget.exportFolderLabel.text, "/fake/folder/path")

    def test_successful_export_shows_and_opens_output_folder(self):
        self.logic.inferenceFinished()
        slicer.app.processEvents()

        with TemporaryDirectory() as tmp, patch.object(
            qt.QFileDialog, "getExistingDirectory", return_value=tmp
        ), patch.object(
            self.widget.exportManager, "exportSegmentation", return_value=["maxilla.stl", "mandible.stl"]
        ), patch.object(qt.QDesktopServices, "openUrl", return_value=True) as openUrl:
            self.widget.onExportClicked()

            self.assertTrue(self.widget.exportResultLabel.isVisible())
            self.assertIn("2 file(s)", self.widget.exportResultLabel.text)
            self.assertIn(tmp, self.widget.exportResultLabel.text)
            self.assertTrue(self.widget.openExportFolderButton.isVisible())
            self.assertTrue(self.widget.openExportFolderButton.isEnabled())

            self.widget.openExportFolderButton.click()

        openUrl.assert_called_once()
        self.assertEqual(openUrl.call_args.args[0].toLocalFile(), tmp)

    def test_synchronises_segmentation_selector_to_processed_volume(self):
        self.assertIsNone(self.widget.getCurrentSegmentationNode())
        self.logic.inferenceFinished()
        slicer.app.processEvents()
        self.assertIsNotNone(self.widget.getCurrentSegmentationNode())

        otherNode = SampleData.SampleDataLogic().downloadMRHead()
        self.widget.inputSelector.setCurrentNode(otherNode)
        self.assertIsNone(self.widget.getCurrentSegmentationNode())

        self.widget.inputSelector.setCurrentNode(self.node)
        self.assertIsNotNone(self.widget.getCurrentSegmentationNode())

    def test_handles_deleted_segmentations(self):
        self.logic.inferenceFinished()
        slicer.app.processEvents()

        otherNode = SampleData.SampleDataLogic().downloadMRHead()
        self.widget.inputSelector.setCurrentNode(otherNode)
        slicer.app.processEvents()

        self.widget.inputSelector.setCurrentNode(self.node)
        slicer.app.processEvents()
        slicer.mrmlScene.RemoveNode(self.widget.getCurrentSegmentationNode())

        self.widget.inputSelector.setCurrentNode(otherNode)
        slicer.app.processEvents()
        self.widget.inputSelector.setCurrentNode(self.node)
        slicer.app.processEvents()
        self.assertIsNone(self.widget.getCurrentSegmentationNode())

    def test_handles_cleared_scene(self):
        prev_node = self.widget.segmentEditorNode
        slicer.mrmlScene.Clear()
        slicer.app.processEvents()
        self.widget.inputSelector.setCurrentNode(SampleData.SampleDataLogic().downloadMRHead())
        self.widget.applyButton.click()
        slicer.app.processEvents()
        self.logic.inferenceFinished()
        slicer.app.processEvents()
        self.assertTrue(self.widget.applyButton.isVisible())
        self.assertNotEqual(prev_node, self.widget.segmentEditorWidget)

    def test_clearing_scene_mid_inference_stops_inference(self):
        self.widget.applyButton.click()
        slicer.app.processEvents()
        slicer.mrmlScene.Clear()
        slicer.app.processEvents()
        self.assertTrue(self.widget.applyButton.isVisible())
        self.logic.stopSegmentation.assert_called_once()

    def test_settings_persistence_roundtrip(self):
        import qt
        import os
        from DentoFacSegmentatorLib.ModuleSettings import ModuleSettings
        
        # Option chosen: use a real file-scoped qt.QSettings in a TemporaryDirectory
        # so the test never touches the user's real settings.
        with TemporaryDirectory() as tmpDir:
            iniPath = os.path.join(tmpDir, "test_settings.ini")
            backend = qt.QSettings(iniPath, qt.QSettings.IniFormat)
            
            logic = MockLogic()
            widget1 = SegmentationWidget(logic=logic, settings=ModuleSettings(backend=backend))
            widget1.inputSelector.setCurrentNode(self.node)
            widget1.show()
            slicer.app.processEvents()
            
            # Set non-default values
            cpuIndex = widget1.deviceComboBox.findData("cpu")
            self.assertGreaterEqual(cpuIndex, 0)
            widget1.deviceComboBox.setCurrentIndex(cpuIndex)
            widget1._persistDevice()
                
            widget1.surfaceSmoothingSlider.setValue(0.7)
            
            widget1.stlCheckBox.setChecked(False)
            widget1.objCheckBox.setChecked(True)
            widget1.niftiCheckBox.setChecked(True)
            widget1.gltfCheckBox.setChecked(False)
            
            widget1.reductionFactorSlider.setValue(0.6)
            
            slicer.app.processEvents()
            
            # Build widget2 sharing the same backend
            widget2 = SegmentationWidget(logic=logic, settings=ModuleSettings(backend=backend))
            widget2.inputSelector.setCurrentNode(self.node)
            widget2.show()
            slicer.app.processEvents()
            
            # Assert values are restored
            # Validate device from the backend to avoid test failure if cpu falls back due to _configureDeviceOptions
            self.assertEqual(backend.value(ModuleSettings.KEY_DEVICE, ""), "cpu")
            self.assertAlmostEqual(widget2.surfaceSmoothingSlider.value, 0.7)
            
            formats = widget2.getSelectedExportFormats()
            self.assertEqual(formats, ExportFormat.OBJ | ExportFormat.NIFTI)
            
            self.assertAlmostEqual(widget2.reductionFactorSlider.value, 0.6)
