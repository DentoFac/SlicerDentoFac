# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2024, Gauthier DOT
# Adapted by DentoFac from SlicerDentalSegmentator commit 476043f00009c372f0653dc759d69e2e559ed0f4; modified from upstream.

import slicer
import qt
import ctk
from pathlib import Path
from slicer.ScriptedLoadableModule import *
from slicer.i18n import tr, translate

from DentoFacSegmentatorLib import SegmentationWidget
from DentoFacSegmentatorLib.DiagnosticsTabAdapter import DiagnosticsTabAdapter


class DentoFacSegmentator(ScriptedLoadableModule):
    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = tr("DentoFac Segmentator")
        self.parent.icon = qt.QIcon(
            str(Path(__file__).parent / "Resources" / "Icons" / "dentofac-segmentator.svg")
        )
        self.parent.categories = [translate("qSlicerAbstractCoreModule", "DentoFac")]
        # DentoFac owns DentoFacLib.  Declaring the Hub first keeps the shared
        # package import explicit should the modules ever be packaged separately.
        self.parent.dependencies = ["DentoFac", "SlicerNNUNet"]
        self.parent.contributors = [
            "Gauthier DOT (AP-HP)",
            "Laurent GAJNY (ENSAM)",
            "Roman FENIOUX (KITWARE SAS)",
            "Thibault PELLETIER (KITWARE SAS)"
        ]

        self.parent.helpText = tr(
            "Fully automatic AI segmentation workflow for Dental CT and CBCT scans based on the DentoFac Segmentator nnU-Net "
            "model."
        )
        self.parent.acknowledgementText = tr(
            "DentoFac Segmentator adapts DentalSegmentator from "
            '<a href="https://github.com/gaudot/SlicerDentalSegmentator">SlicerDentalSegmentator</a> '
            "commit 476043f00009c372f0653dc759d69e2e559ed0f4. The upstream module was originally developed for the "
            '<a href="https://orthodontie-ffo.org/">Fédération Française d\'Orthodontie</a> '
            "(FFO) for the analysis of dento-maxillo-facial data."
        )


class DentoFacSegmentatorWidget(ScriptedLoadableModuleWidget):
    def __init__(self, parent=None) -> None:
        ScriptedLoadableModuleWidget.__init__(self, parent)
        self.logic = None
        self._diagnosticsTab = None
        self._helpAcknowledgementTabs = None
        self._moduleSelector = None
        self._helpTabsDefaultMinimumHeight = None
        self._helpTabsDefaultMaximumHeight = None
        self._diagnosticsTabsVisible = False
        self._inlineDiagnosticsCollapsibleButton = None
        self._isCleanedUp = False

    def setup(self) -> None:
        """Called when the user opens the module the first time and the widget is initialized."""
        ScriptedLoadableModuleWidget.setup(self)
        self.segmentationWidget = SegmentationWidget()
        self.logic = self.segmentationWidget.logic
        self.layout.addWidget(self.segmentationWidget)
        self._diagnosticsTab = self.segmentationWidget.helpDiagnosticsWidget
        self._helpAcknowledgementTabs = self._findHelpAcknowledgementTabs()
        try:
            self._moduleSelector = slicer.util.moduleSelector()
        except RuntimeError:
            # Generic module tests and batch/headless Slicer sessions have no
            # main window. Diagnostics remains available inline in that case.
            self._moduleSelector = None
        if self._moduleSelector is not None:
            self._moduleSelector.connect("moduleSelected(QString)", self._onModuleSelected)
        if self._helpAcknowledgementTabs is not None:
            self._helpTabsDefaultMinimumHeight = self._helpAcknowledgementTabs.minimumHeight
            self._helpTabsDefaultMaximumHeight = self._helpAcknowledgementTabs.maximumHeight
            self._helpAcknowledgementTabs.connect("currentChanged(int)", self._fitHelpTabToCurrentPage)
        else:
            self._mountDiagnosticsInline()
        self.layout.addStretch()
        self._onModuleSelected(self.moduleName)

    @staticmethod
    def _findHelpAcknowledgementTabs():
        """Return Slicer's optional shared tabs through the compatibility adapter."""
        return DiagnosticsTabAdapter.find_shared_tabs()

    def _mountDiagnosticsInline(self):
        """Keep diagnostics reachable when Slicer's private shared-tab lookup changes."""
        if self._diagnosticsTab is None or self._inlineDiagnosticsCollapsibleButton is not None:
            return

        fallback = ctk.ctkCollapsibleButton()
        fallback.text = tr("Diagnostics")
        fallback.collapsed = True
        fallbackLayout = qt.QVBoxLayout()
        fallbackLayout.setContentsMargins(0, 0, 0, 0)
        fallbackLayout.addWidget(self._diagnosticsTab)
        fallback.setLayout(fallbackLayout)
        self.layout.addWidget(fallback)
        self._inlineDiagnosticsCollapsibleButton = fallback

    def _onModuleSelected(self, moduleName):
        """Show Diagnostics only alongside this module's Help/Acknowledgement tabs."""
        if self._helpAcknowledgementTabs is None or self._diagnosticsTab is None:
            return
        tabIndex = self._helpAcknowledgementTabs.indexOf(self._diagnosticsTab)
        if str(moduleName) == self.moduleName:
            self._diagnosticsTabsVisible = True
            if tabIndex < 0:
                self._helpAcknowledgementTabs.addTab(self._diagnosticsTab, tr("Diagnostics"))
            self._fitHelpTabToCurrentPage()
        elif tabIndex >= 0:
            self._diagnosticsTabsVisible = False
            self._helpAcknowledgementTabs.removeTab(tabIndex)
            self._restoreHelpTabHeight()

    def _fitHelpTabToCurrentPage(self, *_):
        """Fit the shared tab control only while its Diagnostics page is selected."""
        if not self._diagnosticsTabsVisible or self._helpAcknowledgementTabs is None:
            return
        currentPage = self._helpAcknowledgementTabs.currentWidget()
        if currentPage is not self._diagnosticsTab:
            self._restoreHelpTabHeight()
            return
        frameWidth = self._helpAcknowledgementTabs.style().pixelMetric(qt.QStyle.PM_DefaultFrameWidth)
        height = (
            currentPage.minimumSizeHint.height()
            + self._helpAcknowledgementTabs.tabBar().sizeHint.height()
            + 2 * frameWidth
        )
        self._helpAcknowledgementTabs.setFixedHeight(height)

    def _restoreHelpTabHeight(self):
        if self._helpAcknowledgementTabs is None:
            return
        if self._helpTabsDefaultMinimumHeight is not None:
            self._helpAcknowledgementTabs.setMinimumHeight(self._helpTabsDefaultMinimumHeight)
        if self._helpTabsDefaultMaximumHeight is not None:
            self._helpAcknowledgementTabs.setMaximumHeight(self._helpTabsDefaultMaximumHeight)

    def cleanup(self):
        if self._isCleanedUp:
            return
        self._isCleanedUp = True
        if getattr(self, "segmentationWidget", None) is not None:
            self.segmentationWidget.cleanup()
        if self._moduleSelector is not None:
            try:
                self._moduleSelector.disconnect("moduleSelected(QString)", self._onModuleSelected)
            except (RuntimeError, TypeError):
                pass
        if self._helpAcknowledgementTabs is not None and self._diagnosticsTab is not None:
            try:
                self._helpAcknowledgementTabs.disconnect("currentChanged(int)", self._fitHelpTabToCurrentPage)
            except (RuntimeError, TypeError):
                pass
            tabIndex = self._helpAcknowledgementTabs.indexOf(self._diagnosticsTab)
            if tabIndex >= 0:
                self._helpAcknowledgementTabs.removeTab(tabIndex)
            self._restoreHelpTabHeight()


class DentoFacSegmentatorTest(ScriptedLoadableModuleTest):
    def runTest(self):
        try:
            from SlicerPythonTestRunnerLib import RunnerLogic, RunnerWidget, RunSettings, isRunningInTestMode
            from pathlib import Path
        except ImportError:
            slicer.util.warningDisplay("Please install SlicerPythonTestRunner extension to run the self tests.")
            return

        currentDirTest = Path(__file__).parent.joinpath("Testing")
        results = RunnerLogic().runAndWaitFinished(
            currentDirTest,
            RunSettings(
                extraPytestArgs=RunSettings.pytestFileFilterArgs("*TestCase.py")
                + ["-m not slow and not baseline_slicer_runtime_quarantine"]
            ),
            doRunInSubProcess=not isRunningInTestMode()
        )

        if results.failuresNumber:
            raise AssertionError(f"Test failed: \n{results.getFailingCasesString()}")

        slicer.util.delayDisplay(f"Tests OK. {results.getSummaryString()}")
