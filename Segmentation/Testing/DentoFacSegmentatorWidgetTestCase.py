# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2024, Gauthier DOT
# Adapted by DentoFac from SlicerDentalSegmentator commit 476043f00009c372f0653dc759d69e2e559ed0f4; modified from upstream.

"""Slicer-only coverage for the module host's Diagnostics-tab lifecycle."""

import unittest
from unittest.mock import MagicMock, patch

import qt
import slicer

from DentoFacSegmentator import DentoFacSegmentatorWidget


class DentoFacSegmentatorWidgetTestCase(unittest.TestCase):
    def setUp(self):
        self.parent = slicer.qMRMLWidget()
        self.parent.setMRMLScene(slicer.mrmlScene)
        self.parent.setLayout(qt.QVBoxLayout())
        self.widget = DentoFacSegmentatorWidget(parent=self.parent)

    def tearDown(self):
        if self.widget is not None:
            self.widget.cleanup()
        self.parent.deleteLater()
        slicer.app.processEvents()

    def _setupWithSharedTabs(self):
        sharedTabs = qt.QTabWidget()
        sharedTabs.setMinimumHeight(31)
        sharedTabs.setMaximumHeight(16777215)
        with patch.object(
            self.widget, "_findHelpAcknowledgementTabs", return_value=sharedTabs
        ):
            self.widget.setup()
        return sharedTabs

    def test_fallback_keeps_diagnostics_reachable_without_shared_tabs(self):
        with patch.object(
            self.widget, "_findHelpAcknowledgementTabs", return_value=None
        ):
            self.widget.setup()

        fallback = self.widget._inlineDiagnosticsCollapsibleButton
        self.assertIsNotNone(fallback)
        self.assertEqual(fallback.text, "Diagnostics")
        self.assertTrue(fallback.collapsed)
        self.assertIs(self.widget._diagnosticsTab.parent(), fallback)

        fallback.collapsed = False
        self.parent.show()
        slicer.app.processEvents()
        self.assertTrue(self.widget.segmentationWidget.showLogsButton.isVisible())
        self.assertTrue(self.widget.segmentationWidget.supportDiagnosticsButton.isVisible())

    def test_shared_tab_is_limited_to_this_module_and_restores_other_pages(self):
        sharedTabs = self._setupWithSharedTabs()
        helpPage = qt.QWidget()
        acknowledgementPage = qt.QWidget()
        sharedTabs.insertTab(0, helpPage, "Help")
        sharedTabs.insertTab(1, acknowledgementPage, "Acknowledgement")

        diagnosticsIndex = sharedTabs.indexOf(self.widget._diagnosticsTab)
        self.assertGreaterEqual(diagnosticsIndex, 0)
        self.assertIsNone(self.widget._inlineDiagnosticsCollapsibleButton)

        sharedTabs.setCurrentIndex(diagnosticsIndex)
        self.widget._fitHelpTabToCurrentPage()
        diagnosticsHeight = sharedTabs.minimumHeight
        self.assertEqual(sharedTabs.minimumHeight, sharedTabs.maximumHeight)

        sharedTabs.setCurrentIndex(sharedTabs.indexOf(helpPage))
        self.widget._fitHelpTabToCurrentPage()
        self.assertEqual(sharedTabs.minimumHeight, 31)
        self.assertEqual(sharedTabs.maximumHeight, 16777215)
        self.assertNotEqual(diagnosticsHeight, 0)

        self.widget._onModuleSelected("OtherModule")
        self.assertLess(sharedTabs.indexOf(self.widget._diagnosticsTab), 0)

    def test_cleanup_removes_shared_tab_and_restores_height(self):
        sharedTabs = self._setupWithSharedTabs()
        diagnosticsIndex = sharedTabs.indexOf(self.widget._diagnosticsTab)
        self.assertGreaterEqual(diagnosticsIndex, 0)

        sharedTabs.setCurrentIndex(diagnosticsIndex)
        self.widget._fitHelpTabToCurrentPage()
        self.assertEqual(sharedTabs.minimumHeight, sharedTabs.maximumHeight)

        # Disconnect the real application selector first, then replace it with a
        # mock so the cleanup contract itself is asserted without leaving a test
        # connection behind in Slicer's global module selector.
        self.widget._moduleSelector.disconnect(
            "moduleSelected(QString)", self.widget._onModuleSelected
        )
        moduleSelector = MagicMock()
        self.widget._moduleSelector = moduleSelector
        self.widget.cleanup()
        moduleSelector.disconnect.assert_called_once_with(
            "moduleSelected(QString)", self.widget._onModuleSelected
        )
        self.assertLess(sharedTabs.indexOf(self.widget._diagnosticsTab), 0)
        self.assertEqual(sharedTabs.minimumHeight, 31)
        self.assertEqual(sharedTabs.maximumHeight, 16777215)
        self.widget = None
