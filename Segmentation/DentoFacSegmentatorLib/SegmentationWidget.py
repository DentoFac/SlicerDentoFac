# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2024, Gauthier DOT
# Adapted by DentoFac from SlicerDentalSegmentator commit 476043f00009c372f0653dc759d69e2e559ed0f4; modified from upstream.

from pathlib import Path
import time

import ctk
import qt
import slicer

from .IconPath import icon, iconPath
from .PythonDependencyChecker import PythonDependencyChecker
from .Utils import (
    createButton,
    addInCollapsibleLayout,
    set3DViewBackgroundColors,
    setConventionalWideScreenView,
    setBoxAndTextVisibilityOnThreeDViews,
)


from .ExportManager import ExportManager, ExportFormat
from .SegmentationResultProcessor import SegmentationResultProcessor
from .ModuleSettings import ModuleSettings
from .InferenceProgress import ProgressTracker, formatElapsedTime, parseProgress
from .SegmentStatisticsReport import buildReport


class SegmentationWidget(qt.QWidget):
    _DEVICE_OPTIONS = ("cuda", "cpu", "mps")

    def __init__(self, logic=None, parent=None, settings=None):
        super().__init__(parent)
        self._settings = settings if settings is not None else ModuleSettings()
        self.logic = logic or self._createSlicerSegmentationLogic()
        self._prevSegmentationNode = None

        self.inputSelector = slicer.qMRMLNodeComboBox(self)
        self.inputSelector.nodeTypes = ["vtkMRMLScalarVolumeNode"]
        self.inputSelector.addEnabled = False
        self.inputSelector.showHidden = False
        self.inputSelector.removeEnabled = False
        self.inputSelector.setMRMLScene(slicer.mrmlScene)
        self.inputSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onInputChanged)

        # Configure inference device options
        self.deviceComboBox = qt.QComboBox()
        # Store the backend value as item data.  The visible label may include
        # an availability explanation, but settings and inference must always
        # receive the canonical device value.
        for device in self._DEVICE_OPTIONS:
            self.deviceComboBox.addItem(device, device)
        self.deviceComboBox.currentIndexChanged.connect(self.refreshInstallationStatus)

        # Configure segment editor node selector
        self.segmentationNodeSelector = slicer.qMRMLNodeComboBox(self)
        self.segmentationNodeSelector.nodeTypes = ["vtkMRMLSegmentationNode"]
        self.segmentationNodeSelector.selectNodeUponCreation = True
        self.segmentationNodeSelector.addEnabled = True
        self.segmentationNodeSelector.removeEnabled = True
        self.segmentationNodeSelector.showHidden = False
        self.segmentationNodeSelector.renameEnabled = True
        self.segmentationNodeSelector.setMRMLScene(slicer.mrmlScene)
        self.segmentationNodeSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateSegmentEditorWidget)

        # Override default segment node selector text to be more explicit than "Select Segmentation"
        segmentationSelectorComboBox = self.segmentationNodeSelector.findChild("ctkComboBox")
        segmentationSelectorComboBox.defaultText = "Create new Segmentation on Apply"

        # Create segment editor widget
        self.segmentEditorWidget = slicer.qMRMLSegmentEditorWidget(self)
        self.segmentEditorWidget.setMRMLScene(slicer.mrmlScene)
        self.segmentEditorWidget.setSegmentationNodeSelectorVisible(False)
        self.segmentEditorWidget.setSourceVolumeNodeSelectorVisible(False)
        self.segmentEditorWidget.layout().setContentsMargins(0, 0, 0, 0)
        self.segmentEditorNode = None

        # Find show 3D Button in widget
        self.show3DButton = slicer.util.findChild(self.segmentEditorWidget, "Show3DButton")

        # Create surface smoothing and connect it to show3D button surface smoothing
        smoothingSlider = self.show3DButton.findChild("ctkSliderWidget")
        self.surfaceSmoothingSlider = ctk.ctkSliderWidget(self)
        self.surfaceSmoothingSlider.setToolTip(
            "Higher value means stronger smoothing during closed surface representation conversion."
        )
        self.surfaceSmoothingSlider.decimals = 2
        self.surfaceSmoothingSlider.maximum = 1
        self.surfaceSmoothingSlider.singleStep = 0.1
        self.surfaceSmoothingSlider.setValue(smoothingSlider.value)
        self.surfaceSmoothingSlider.tracking = False
        self.surfaceSmoothingSlider.valueChanged.connect(smoothingSlider.setValue)

        # Export Widget
        exportWidget = qt.QWidget()
        exportLayout = qt.QFormLayout(exportWidget)
        self.stlCheckBox = qt.QCheckBox(exportWidget)
        self.stlCheckBox.setChecked(True)
        self.objCheckBox = qt.QCheckBox(exportWidget)
        self.niftiCheckBox = qt.QCheckBox(exportWidget)
        self.gltfCheckBox = qt.QCheckBox(exportWidget)
        self.reductionFactorSlider = ctk.ctkSliderWidget()
        self.reductionFactorSlider.maximum = 1.0
        self.reductionFactorSlider.value = 0.9
        self.reductionFactorSlider.singleStep = 0.01
        self.reductionFactorSlider.toolTip = (
            "Decimation factor determining how much the mesh complexity will be reduced. "
            "Higher value means stronger reduction (smaller files, less details preserved)."
        )

        exportLayout.addRow("Export STL", self.stlCheckBox)
        exportLayout.addRow("Export OBJ", self.objCheckBox)
        exportLayout.addRow("Export NIFTI", self.niftiCheckBox)
        exportLayout.addRow("Export glTF", self.gltfCheckBox)
        exportLayout.addRow("glTF reduction factor :", self.reductionFactorSlider)

        self.exportButton = createButton("Export", callback=self.onExportClicked, parent=exportWidget)
        exportLayout.addRow(self.exportButton)

        self._lastExportFolder = ""
        self._lastSuccessfulExportFolder = ""
        self.exportFolderLabel = qt.QLabel("No folder selected yet.")
        self.exportFolderLabel.setWordWrap(True)
        exportLayout.addRow("Output folder:", self.exportFolderLabel)

        self.exportResultLabel = qt.QLabel()
        self.exportResultLabel.setWordWrap(True)
        self.exportResultLabel.setVisible(False)
        self.openExportFolderButton = createButton(
            "Open folder",
            callback=self.onOpenExportFolderClicked,
            toolTip="Open the folder containing the most recently exported files.",
            parent=exportWidget,
        )
        self.openExportFolderButton.setVisible(False)
        self.openExportFolderButton.setEnabled(False)
        exportResultWidget = qt.QWidget(exportWidget)
        exportResultLayout = qt.QHBoxLayout(exportResultWidget)
        exportResultLayout.setContentsMargins(0, 0, 0, 0)
        exportResultLayout.addWidget(self.exportResultLabel, 1)
        exportResultLayout.addWidget(self.openExportFolderButton)
        exportLayout.addRow("Export result:", exportResultWidget)

        layout = qt.QVBoxLayout(self)

        # This widget is mounted as a tab next to Slicer's Help and
        # Acknowledgement tabs by DentoFacSegmentatorWidget.
        self.helpDiagnosticsWidget = qt.QWidget(self)
        helpDiagnosticsLayout = qt.QVBoxLayout(self.helpDiagnosticsWidget)
        helpDiagnosticsLayout.setContentsMargins(0, 0, 0, 0)
        self.showLogsButton = createButton(
            "View activity log", callback=self.showInfoLogs,
            toolTip="Show the detailed module activity log.", parent=self.helpDiagnosticsWidget,
        )
        self.supportDiagnosticsButton = createButton(
            "Create support report…", callback=self.onExportDiagnosticsClicked,
            toolTip="Collect diagnostic information to share with support.", parent=self.helpDiagnosticsWidget,
        )
        helpDiagnosticsLayout.addWidget(self.showLogsButton)
        helpDiagnosticsLayout.addWidget(self.supportDiagnosticsButton)
        helpDiagnosticsLayout.addStretch()

        # Installation Status Panel (kept before the run controls so users see readiness first)
        statusWidget = qt.QWidget()
        statusLayout = qt.QVBoxLayout(statusWidget)

        self.statusVerdictLabel = qt.QLabel()
        self.statusVerdictLabel.setStyleSheet("font-weight: bold;")
        statusLayout.addWidget(self.statusVerdictLabel)

        self.statusLabels = {}
        for key in ["NNUNet extension", "Python dependencies (torch, nnunetv2)", "Compute device", "GPU acceleration", "Model weights"]:
            lbl = qt.QLabel()
            lbl.setWordWrap(True)
            self.statusLabels[key] = lbl
            statusLayout.addWidget(lbl)

        # Busy indicator shown during the dependency install. pip installs on the GUI
        # thread, so during the wheel-unpack phase (no pip output) the event loop can't
        # turn and this bar will appear frozen — the label sets that expectation up
        # front so a stalled bar doesn't read as a crash. Keep it with the installation
        # state rather than below the Apply action.
        self.installProgressWidget = qt.QWidget(statusWidget)
        installProgressLayout = qt.QVBoxLayout(self.installProgressWidget)
        installProgressLayout.setContentsMargins(0, 0, 0, 0)
        self.installProgressLabel = qt.QLabel()
        self.installProgressLabel.setWordWrap(True)
        self.installProgressBar = qt.QProgressBar()
        self.installProgressBar.setRange(0, 0)  # indeterminate / busy
        self.installProgressBar.setTextVisible(False)
        installProgressLayout.addWidget(self.installProgressLabel)
        installProgressLayout.addWidget(self.installProgressBar)
        self.installProgressWidget.setVisible(False)
        statusLayout.addWidget(self.installProgressWidget)

        self.statusActionButton = createButton("Re-check", callback=self.onStatusActionClicked, parent=statusWidget)
        statusLayout.addWidget(self.statusActionButton)

        # Setup details should be immediately visible until the module is ready.
        # Once configured, retain them behind this compact affordance so the primary
        # scan-and-run workflow is not pushed down the panel.
        self.installationStatusCollapsibleButton = addInCollapsibleLayout(
            statusWidget, layout, "Installation Status", isCollapsed=False
        )

        self.inputWidget = qt.QWidget(self)
        inputLayout = qt.QFormLayout(self.inputWidget)
        inputLayout.setContentsMargins(0, 0, 0, 0)
        inputVolumeWidget = qt.QWidget(self.inputWidget)
        inputVolumeLayout = qt.QHBoxLayout(inputVolumeWidget)
        inputVolumeLayout.setContentsMargins(0, 0, 0, 0)
        inputVolumeLayout.addWidget(self.inputSelector, 1)
        self.loadSampleVolumeButton = createButton(
            "Load sample volume",
            callback=self.onLoadSampleVolumeClicked,
            toolTip="Download and select the CBCT Dental Surgery sample volume.",
            parent=inputVolumeWidget,
        )
        # This remains a secondary action beside the user's input selector, but it
        # needs a standard button affordance so users recognize it as clickable.
        self.loadSampleVolumeButton.setFlat(False)
        inputVolumeLayout.addWidget(self.loadSampleVolumeButton)
        inputLayout.addRow("Input volume:", inputVolumeWidget)

        self.outputSegmentationLabel = qt.QLabel("Output segmentation:", self.inputWidget)
        self.outputSegmentationLabel.setBuddy(self.segmentationNodeSelector)
        inputLayout.addRow(self.outputSegmentationLabel, self.segmentationNodeSelector)

        # Device is currently the only runtime preference. Keep it direct and
        # legible instead of wrapping one row in an otherwise empty disclosure.
        self.deviceLabel = qt.QLabel("Device:", self.inputWidget)
        self.deviceLabel.setBuddy(self.deviceComboBox)
        inputLayout.addRow(self.deviceLabel, self.deviceComboBox)
        self.deviceHintLabel = qt.QLabel()
        self.deviceHintLabel.setWordWrap(True)
        self.deviceHintLabel.setStyleSheet("color: #555;")
        inputLayout.addRow("", self.deviceHintLabel)
        layout.addWidget(self.inputWidget)

        # Kept separate from the detailed run log so warnings are still
        # visible after inference completes and while revisiting a result.
        self.resultQualityFlagsLabel = qt.QLabel()
        self.resultQualityFlagsLabel.setWordWrap(True)
        self.resultQualityFlagsLabel.setStyleSheet("color: #9c5700;")
        self.resultQualityFlagsLabel.setVisible(False)
        layout.addWidget(self.resultQualityFlagsLabel)

        self.applyButton = createButton(
            "Apply",
            callback=self.onApplyClicked,
            toolTip="Click to run the segmentation.",
            icon=icon("start_icon.png")
        )

        self.fullInfoLogs = []
        self._logDialog = None
        self._liveLogTextEdit = None

        # Keep inference status in a stable position above Apply. It is disabled
        # until a run starts, preventing the panel from jumping when progress arrives.
        self.inferenceStatusWidget = qt.QWidget(self)
        inferenceStatusLayout = qt.QVBoxLayout(self.inferenceStatusWidget)
        inferenceStatusLayout.setContentsMargins(0, 0, 0, 0)
        self.inferenceStageLabel = qt.QLabel("Stage: waiting to start")
        self.inferenceElapsedLabel = qt.QLabel("Elapsed: 00:00")
        self.inferenceEtaLabel = qt.QLabel()
        self.inferenceProgressBar = qt.QProgressBar()
        # A determinate zero-value bar remains still while idle. Indeterminate
        # animation is enabled only after inference starts and before nnU-Net
        # emits a parseable percentage.
        self.inferenceProgressBar.setRange(0, 100)
        self.inferenceProgressBar.setValue(0)
        self.inferenceProgressBar.setTextVisible(False)
        inferenceStatusLayout.addWidget(self.inferenceStageLabel)
        progressLayout = qt.QHBoxLayout()
        progressLayout.setContentsMargins(0, 0, 0, 0)
        progressLayout.addWidget(self.inferenceProgressBar, 1)
        self.viewLiveLogButton = createButton(
            "View live log…", callback=self.showInfoLogs,
            toolTip="Open the live activity log without interrupting inference.", parent=self.inferenceStatusWidget,
        )
        progressLayout.addWidget(self.viewLiveLogButton)
        inferenceStatusLayout.addLayout(progressLayout)
        timingLayout = qt.QHBoxLayout()
        timingLayout.setContentsMargins(0, 0, 0, 0)
        timingLayout.addWidget(self.inferenceElapsedLabel)
        timingLayout.addWidget(self.inferenceEtaLabel)
        timingLayout.addStretch()
        inferenceStatusLayout.addLayout(timingLayout)
        self.inferenceEtaLabel.setVisible(False)

        self.stopButton = createButton(
            "Stop",
            callback=self.onStopClicked,
            toolTip="Click to Stop the segmentation."
        )
        self.stopWidget = qt.QWidget(self)
        stopLayout = qt.QVBoxLayout(self.stopWidget)
        stopLayout.setContentsMargins(0, 0, 0, 0)
        stopLayout.addWidget(self.stopButton)
        self.stopWidget.setVisible(False)
        self.inferenceStatusWidget.setEnabled(False)
        self.loading = qt.QMovie(iconPath("loading.gif"))
        self.loading.setScaledSize(qt.QSize(24, 24))
        self.loading.frameChanged.connect(self._updateStopIcon)
        self.loading.start()

        self.applyWidget = qt.QWidget(self)
        applyLayout = qt.QHBoxLayout(self.applyWidget)
        applyLayout.setContentsMargins(0, 0, 0, 0)
        applyLayout.addWidget(self.applyButton, 1)

        layout.addWidget(self.inferenceStatusWidget)
        layout.addWidget(self.applyWidget)
        layout.addWidget(self.stopWidget)

        # Refinement controls are meaningful only after a segmentation exists. Keep
        # the editor and the display-only surface conversion setting together so the
        # default scan-and-run panel does not imply that smoothing affects inference.
        self.refineResultCollapsibleButton = ctk.ctkCollapsibleButton()
        self.refineResultCollapsibleButton.text = "Refine result"
        # Reviewing the result is the immediate next task after inference, so leave
        # this section open the first time it becomes available.
        self.refineResultCollapsibleButton.collapsed = False
        refineResultLayout = qt.QVBoxLayout(self.refineResultCollapsibleButton)
        refineResultLayout.setContentsMargins(0, 0, 0, 0)
        refineResultLayout.addWidget(self.segmentEditorWidget)

        self.surfaceSmoothingWidget = qt.QWidget(self.refineResultCollapsibleButton)
        surfaceSmoothingLayout = qt.QFormLayout(self.surfaceSmoothingWidget)
        surfaceSmoothingLayout.setContentsMargins(0, 0, 0, 0)
        surfaceSmoothingLayout.addRow("Surface smoothing:", self.surfaceSmoothingSlider)
        refineResultLayout.addWidget(self.surfaceSmoothingWidget)
        self.refineResultCollapsibleButton.setVisible(False)
        layout.addWidget(self.refineResultCollapsibleButton)

        self.measurementsWidget = qt.QWidget(self)
        measurementsLayout = qt.QVBoxLayout(self.measurementsWidget)
        measurementsLayout.setContentsMargins(0, 0, 0, 0)
        self.measurementsTable = qt.QTableWidget(0, 3, self.measurementsWidget)
        self.measurementsTable.setHorizontalHeaderLabels(["Structure", "Volume (cc)", "Volume (mm³)"])
        self.measurementsTable.setEditTriggers(qt.QAbstractItemView.NoEditTriggers)
        self.measurementsTable.setSelectionMode(qt.QAbstractItemView.NoSelection)
        self.measurementsTable.horizontalHeader().setStretchLastSection(True)
        measurementsLayout.addWidget(self.measurementsTable)
        measurementsActions = qt.QHBoxLayout()
        self.copyMeasurementsButton = createButton("Copy CSV", callback=self.onCopyMeasurementsClicked)
        self.saveMeasurementsButton = createButton("Save CSV…", callback=self.onSaveMeasurementsClicked)
        measurementsActions.addWidget(self.copyMeasurementsButton)
        measurementsActions.addWidget(self.saveMeasurementsButton)
        measurementsActions.addStretch()
        measurementsLayout.addLayout(measurementsActions)
        self.measurementsCollapsibleButton = ctk.ctkCollapsibleButton()
        self.measurementsCollapsibleButton.text = "Measurements"
        self.measurementsCollapsibleButton.collapsed = False
        self.measurementsCollapsibleButton.setLayout(qt.QVBoxLayout())
        self.measurementsCollapsibleButton.layout().addWidget(self.measurementsWidget)
        self.measurementsCollapsibleButton.setVisible(False)
        layout.addWidget(self.measurementsCollapsibleButton)

        self.exportCollapsibleButton = addInCollapsibleLayout(
            exportWidget, layout, "Export segmentation", isCollapsed=True
        )
        layout.addStretch()

        self.isStopping = False
        self._inferenceTimer = qt.QTimer(self)
        self._inferenceTimer.setInterval(1000)
        self._inferenceTimer.timeout.connect(self._updateInferenceElapsedTime)
        self._inferenceStartedAt = None
        self._inferenceProgressActive = False
        self._inferenceProgressTracker = ProgressTracker()
        self._measurementReports = {}
        self._measurementReport = None
        self._qualityFlagsBySegmentation = {}

        self._dependencyChecker = PythonDependencyChecker()
        self.exportManager = ExportManager()
        self.processedVolumes = {}
        self._clearMeasurements()
        self._clearResultQualityFlags()
        self.resultProcessor = SegmentationResultProcessor(
            self.segmentEditorWidget,
            self.show3DButton,
            progressCallback=self.onProgressInfo,
        )

        self.onInputChanged()
        self.updateSegmentEditorWidget()
        self.sceneCloseObserver = slicer.mrmlScene.AddObserver(slicer.mrmlScene.EndCloseEvent, self.onSceneChanged)
        self.onSceneChanged(doStopInference=False)
        self._connectSegmentationLogic()
        self._loadPersistedSettings()
        self._connectSettingsPersistence()
        self._configureDeviceOptions()
        self.refreshInstallationStatus()
        self._updateResultUiVisibility()

    def onStatusActionClicked(self, *_):
        """Status-panel button. Installs missing dependencies when something
        installable is missing, otherwise re-checks status (including online)."""
        if getattr(self, "_statusActionIsInstall", False) or getattr(self, "_statusActionIsForcedWeights", False):
            self._installMissingDependencies()
        else:
            self._configureDeviceOptions()
            self.refreshInstallationStatus(check_online=True)

    def _installMissingDependencies(self):
        """Install the Python requirements and download model weights, then refresh."""
        if not self.isNNUNetModuleInstalled():
            slicer.util.errorDisplay(
                "This module depends on the NNUNet module."
                " Please install the NNUNet module and restart to proceed."
            )
            self.refreshInstallationStatus()
            return

        self.statusActionButton.setEnabled(False)
        try:
            if not self._installNNUNetIfNeeded():
                return

            if getattr(self, "_statusActionIsForcedWeights", False):
                from .ModelPath import modelRoot
                if qt.QMessageBox.question(
                        None,
                        "Re-download weights",
                        f"This will replace the weights folder at:\n{modelRoot()}\n\n"
                        "Existing files are only replaced after a successful download.\n\n"
                        "Proceed?"
                ) != qt.QMessageBox.Yes:
                    return
                self._dependencyChecker.downloadWeightsIfNeeded(self.onProgressInfo, force=True)
            else:
                self._dependencyChecker.downloadWeightsIfNeeded(self.onProgressInfo)
        finally:
            self.statusActionButton.setEnabled(True)
            self._configureDeviceOptions()
            self.refreshInstallationStatus(check_online=True)
            self._setInstallInProgress(None)

    def _configureDeviceOptions(self):
        """Grey out compute devices that aren't available and, if the current
        selection is unavailable, fall back to the first available device.

        No-op when availability cannot be verified (SlicerNNUNet not installed),
        leaving every option enabled.
        """
        from .InstallationStatus import device_unavailable_reason, is_device_available

        # A prior check may have decorated an unavailable option.  Always
        # restore its base label before checking again, including when the
        # backend is temporarily not verifiable.
        model = self.deviceComboBox.model()
        for i in range(self.deviceComboBox.count):
            self.deviceComboBox.setItemText(i, self._deviceOptionValue(i))
            model.item(i).setEnabled(True)

        availabilities = [
            is_device_available(self._deviceOptionValue(i))
            for i in range(self.deviceComboBox.count)
        ]
        if any(available is None for available in availabilities):
            return

        firstAvailableIndex = None
        for i, available in enumerate(availabilities):
            model.item(i).setEnabled(available)
            if not available:
                device = self._deviceOptionValue(i)
                reason = device_unavailable_reason(device)
                if reason:
                    self.deviceComboBox.setItemText(i, f"{device} ({reason})")
            if available and firstAvailableIndex is None:
                firstAvailableIndex = i

        if not availabilities[self.deviceComboBox.currentIndex] and firstAvailableIndex is not None:
            # Change selection without retriggering a status refresh; callers refresh next.
            self.deviceComboBox.blockSignals(True)
            self.deviceComboBox.setCurrentIndex(firstAvailableIndex)
            self.deviceComboBox.blockSignals(False)

    def _deviceOptionValue(self, index=None):
        """Return the canonical backend value for a combo-box option."""
        if index is None:
            index = self.deviceComboBox.currentIndex
        value = self.deviceComboBox.itemData(index)
        return str(value) if value is not None else self.deviceComboBox.itemText(index)

    def _selectedDevice(self):
        return self._deviceOptionValue()

    def _updateDeviceHint(self):
        """Show the selected device's speed expectation before Apply."""
        messages = {
            "cuda": "GPU (CUDA) — fast.",
            "mps": "Apple GPU (MPS) — fast.",
            "cpu": "CPU — segmentation may take up to ~1 hour.",
        }
        self.deviceHintLabel.setText(messages.get(self._selectedDevice(), ""))

    def refreshInstallationStatus(self, check_online=False):
        from .InstallationStatus import collect_status, weightsDiagnostic
        from .ModelPath import modelRoot, ValidationStatus

        self._updateDeviceHint()
        status = collect_status(self._selectedDevice(), check_online=check_online)
        val_res = status.val_res
        _, weights_long = weightsDiagnostic(val_res, modelRoot())

        issue_count = sum(
            not line.ok for line in status.lines
            if not line.advisory and line.label != "Compute device"
        )
        if status.is_ready:
            verdict_str = "Ready to run"
        else:
            verdict_str = f"{issue_count} issue(s) — see below"

        verdict_changed = not hasattr(self, '_lastInstallationVerdict') or self._lastInstallationVerdict != verdict_str
        lines_changed = not hasattr(self, '_lastInstallationLines') or self._lastInstallationLines != [l.detail for l in status.lines]
        should_log = check_online or verdict_changed or lines_changed

        self.statusVerdictLabel.setText(verdict_str)
        self.installationStatusCollapsibleButton.text = "● Installation Status"
        self.installationStatusCollapsibleButton.setStyleSheet(
            f"color: {'#2e7d32' if status.is_ready else '#c62828'};"
        )
        # Keep actionable setup problems visible.  When all required dependencies
        # first become available, collapse the verbose per-component checklist and
        # leave the user on the concise, ready-to-run panel.  Do not re-collapse a
        # panel the user has deliberately reopened during a subsequent re-check.
        was_ready = getattr(self, "_wasInstallationReady", None)
        if not status.is_ready:
            self.installationStatusCollapsibleButton.collapsed = False
        elif was_ready is not True:
            self.installationStatusCollapsibleButton.collapsed = True
        self._wasInstallationReady = status.is_ready
        if should_log:
            self.onProgressInfo(f"[Status] Verdict: {verdict_str}")

        for line in status.lines:
            prefix = "ℹ" if line.advisory else ("✓" if line.ok else "✗")
            if line.label in self.statusLabels:
                lbl = self.statusLabels[line.label]
                lbl.setText(f"{prefix} {line.label}: {line.detail}")
                if line.label == "Model weights":
                    if weights_long:
                        lbl.setToolTip(weights_long)
                    else:
                        lbl.setToolTip("")
            if should_log:
                state = "INFO" if line.advisory else ("VALID" if line.ok else "INVALID")
                self.onProgressInfo(f"[Status] {line.label}: {state} - {line.detail}")
                if line.label == "Model weights" and weights_long:
                    self.onProgressInfo(weights_long)

        # Hide (and clear) pre-created labels that have no line this round (e.g. the
        # GPU-acceleration advisory only appears when CUDA is unusable).
        presentLabels = {line.label for line in status.lines}
        for key, lbl in self.statusLabels.items():
            present = key in presentLabels
            lbl.setVisible(present)
            if not present:
                lbl.setText("")

        self._lastInstallationVerdict = verdict_str
        self._lastInstallationLines = [l.detail for l in status.lines]

        # Toggle the status-panel button between "Install" and "Re-check" based on
        # whether there is something we can actually install (extension present, but
        # Python deps and/or model weights missing).
        labelsOk = {line.label: line.ok for line in status.lines}
        extensionOk = labelsOk.get("NNUNet extension", False)
        depsOk = labelsOk.get("Python dependencies (torch, nnunetv2)", False)
        weightsOk = labelsOk.get("Model weights", False)
        self._statusActionIsInstall = extensionOk and not (depsOk and weightsOk)

        # Only offer forced re-download when validation is authoritative (NNUNet present):
        # a non-authoritative FLATTENED result renders as "Cannot verify", and forcing a
        # download would just hit the NNUNet-extension-missing error. Keep button and
        # diagnostic consistent.
        if val_res.authoritative and val_res.status in (ValidationStatus.INVALID, ValidationStatus.FLATTENED):
            self._statusActionIsForcedWeights = True
            self.statusActionButton.setText("Re-download weights")
            self.statusActionButton.setToolTip("Replace the broken or legacy model weights.")
        else:
            self._statusActionIsForcedWeights = False
            self.statusActionButton.setText("Install" if self._statusActionIsInstall else "Re-check")
            self.statusActionButton.setToolTip(
                "Install the missing Python dependencies and/or model weights."
                if self._statusActionIsInstall
                else "Re-check installation status (also checks online for weight updates)."
            )

        # Disable Apply until dependencies are met (device availability is ignored,
        # as the run falls back to CPU).
        self.applyButton.setEnabled(self.getCurrentVolumeNode() is not None and status.is_ready)

    def __del__(self):
        try:
            slicer.mrmlScene.RemoveObserver(self.sceneCloseObserver)
        except Exception:  # noqa
            pass

    def onSceneChanged(self, *_, doStopInference=True):
        if doStopInference:
            self.onStopClicked()
        self.segmentEditorNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentEditorNode")
        self.segmentEditorWidget.setMRMLSegmentEditorNode(self.segmentEditorNode)
        self.processedVolumes = {}
        self._measurementReports.clear()
        self._qualityFlagsBySegmentation.clear()
        self._clearMeasurements()
        self._clearResultQualityFlags()
        self._prevSegmentationNode = None
        self._initSlicerDisplay()
        self._updateResultUiVisibility()

    @staticmethod
    def _initSlicerDisplay():
        """
        Initialize 3D Slicer's display with white background and no 3D Cube / labels.
        """
        set3DViewBackgroundColors([1, 1, 1], [1, 1, 1])
        setConventionalWideScreenView()
        setBoxAndTextVisibilityOnThreeDViews(False)

    def _updateStopIcon(self):
        # A final QMovie frame can arrive while Slicer is tearing down this widget.
        # The button has then already been deleted, so there is nothing left to update.
        try:
            self.stopButton.setIcon(qt.QIcon(self.loading.currentPixmap()))
        except (RuntimeError, ValueError):
            try:
                self.loading.stop()
            except (RuntimeError, ValueError):
                pass

    def onStopClicked(self):
        """
        When user kills the execution, don't show any error window and wait for process to be killed in the logic.
        Once cleanup is done, restore buttons.
        """
        self._stopInferenceProgress()
        if self.logic is None:
            self._updateResultUiVisibility()
            return

        self.isStopping = True
        self.logic.stopSegmentation()
        self.logic.waitForSegmentationFinished()
        slicer.app.processEvents()
        self.isStopping = False
        self._setApplyVisible(True)
        self._updateResultUiVisibility()

    def onApplyClicked(self, *_):
        """
        On apply, clear the output log infos, hide apply button, install dependencies and start the segmentation process
        """
        if not self.isNNUNetModuleInstalled() or self.logic is None:
            slicer.util.errorDisplay(
                "This module depends on the NNUNet module."
                " Please install the NNUNet module and restart to proceed."
            )
            self.refreshInstallationStatus()
            return

        self._setApplyVisible(False)
        try:
            if not self._installNNUNetIfNeeded():
                self._setApplyVisible(True)
                self.refreshInstallationStatus()
                return

            if not self._dependencyChecker.downloadWeightsIfNeeded(self.onProgressInfo):
                self._setApplyVisible(True)
                self.refreshInstallationStatus()
                return

            self._runSegmentation()
        finally:
            # Hide the install busy indicator last — after the status panel has been
            # refreshed on the early-return paths — so it doesn't blink out before the
            # panel reflects the newly installed dependencies. Also guarantees the bar
            # never gets stranded if an install/download step raises.
            self._setInstallInProgress(None)

    def _setApplyVisible(self, isVisible):
        """
        Toggles visibility of the apply / stop buttons and make sure the selectors are disabled when running
        segmentation.
        """
        self.applyWidget.setVisible(isVisible)
        self.stopWidget.setVisible(not isVisible)
        self.inferenceStatusWidget.setEnabled(
            not isVisible and self._inferenceProgressActive
        )
        if isVisible:
            self.inferenceProgressBar.setRange(0, 100)
            self.inferenceProgressBar.setValue(0)
            self.inferenceProgressBar.setTextVisible(False)
        self.inputWidget.setEnabled(isVisible)

    def _runSegmentation(self):
        """
        Make sure the dependencies are available and user is aware CPU process may take time if current install doesn't
        support CUDA before starting the actual segmentation from the logic object.
        """
        from SlicerNNUNetLib import Parameter
        from .ModelPath import inferenceModelPath

        parameter = Parameter(folds="0", modelPath=inferenceModelPath(), device=self._selectedDevice())
        if not parameter.isSelectedDeviceAvailable():
            deviceName = parameter.device.upper()
            ret = qt.QMessageBox.question(
                self,
                f"{deviceName} device not available",
                f"Selected device ({deviceName}) is not currently available on your system and will "
                "default to CPU device.\n"
                "Running the segmentation may take up to 1 hour.\n"
                "Would you like to proceed?"
            )
            if ret == qt.QMessageBox.No:
                self._setApplyVisible(True)
                return

        slicer.app.processEvents()
        self.logic.setParameter(parameter)
        self._startInferenceProgress()
        try:
            self.logic.startSegmentation(self.getCurrentVolumeNode())
        except Exception:
            self._stopInferenceProgress()
            raise

    def _startInferenceProgress(self):
        """Reset and start the live elapsed-time/progress display for a run."""
        self._inferenceStartedAt = time.monotonic()
        self._inferenceProgressActive = True
        self._inferenceProgressTracker.reset()
        self.inferenceStageLabel.setText("Stage: starting inference…")
        self.inferenceElapsedLabel.setText("Elapsed: 00:00")
        self.inferenceEtaLabel.setText("")
        self.inferenceEtaLabel.setVisible(False)
        self.inferenceProgressBar.setRange(0, 0)
        self.inferenceProgressBar.setTextVisible(False)
        self.inferenceStatusWidget.setEnabled(True)
        self._inferenceTimer.start()

    def _stopInferenceProgress(self):
        """Stop the elapsed-time timer while retaining the last visible values."""
        if self._inferenceProgressActive:
            self._updateInferenceElapsedTime()
        self._inferenceTimer.stop()
        self._inferenceProgressActive = False
        self._inferenceStartedAt = None

    def _updateInferenceElapsedTime(self):
        if not self._inferenceProgressActive or self._inferenceStartedAt is None:
            return
        elapsed = time.monotonic() - self._inferenceStartedAt
        self.inferenceElapsedLabel.setText(f"Elapsed: {formatElapsedTime(elapsed)}")
        self._renderInferenceEta(self._inferenceProgressTracker.snapshot(elapsed).eta_minutes)

    def _renderInferenceEta(self, eta_minutes):
        if eta_minutes is None:
            self.inferenceEtaLabel.setVisible(False)
            return
        self.inferenceEtaLabel.setText(f"Estimate: ~{eta_minutes} min remaining")
        self.inferenceEtaLabel.setVisible(True)

    def _applyInferenceProgressUpdate(self, update):
        """Render the pure tracker's state after one parsed progress update."""
        elapsed = time.monotonic() - self._inferenceStartedAt
        state = self._inferenceProgressTracker.apply(update, elapsed)
        self.inferenceStageLabel.setText(f"Stage: {state.stage}")
        if not state.is_determinate:
            self.inferenceProgressBar.setRange(0, 0)
            self.inferenceProgressBar.setTextVisible(False)
        else:
            self.inferenceProgressBar.setRange(0, 1000)
            self.inferenceProgressBar.setValue(round(state.fraction * 1000))
            self.inferenceProgressBar.setTextVisible(True)
        self._renderInferenceEta(state.eta_minutes)

    def onInputChanged(self, *_):
        """
        When changing the input, update the apply button enable status and restore previous segmentation if any.
        """
        volumeNode = self.getCurrentVolumeNode()
        self.applyButton.setEnabled(volumeNode is not None)
        if slicer.app.layoutManager() is not None:
            slicer.util.setSliceViewerLayers(background=volumeNode)
            slicer.util.resetSliceViews()
        self._restoreProcessedSegmentation()
        if hasattr(self, "exportCollapsibleButton"):
            self._updateResultUiVisibility()
        if hasattr(self, 'statusVerdictLabel'):
            self.refreshInstallationStatus()

    def onLoadSampleVolumeClicked(self, *_):
        """Download the CBCT Dental Surgery sample and make it the active input.

        ``SampleData`` downloads synchronously, so keep the button disabled while it
        is running to prevent duplicate downloads.  The enclosing input widget is
        disabled during inference, which also prevents this action while a run is
        active.
        """
        from .PythonDependencyChecker import hasInternetConnection

        if not hasInternetConnection():
            slicer.util.errorDisplay(
                "Unable to load the sample volume because no internet connection is available. "
                "Please connect to the internet and try again."
            )
            return

        self.loadSampleVolumeButton.setEnabled(False)
        try:
            import SampleData

            volumeNode = self._postDentalSurgeryVolumeNode(
                SampleData.SampleDataLogic().downloadDentalSurgery()
            )
            if volumeNode is None:
                # Some SampleData APIs do not return the loaded node. The
                # registered CBCT Dental Surgery sample uses this stable name.
                nodes = slicer.mrmlScene.GetNodesByName("PostDentalSurgery")
                volumeNode = nodes.GetItemAsObject(0) if nodes.GetNumberOfItems() else None
            if volumeNode is None:
                raise RuntimeError("Sample Data did not return a volume node.")

            self.inputSelector.setCurrentNode(volumeNode)
        except Exception as error:  # SampleData exposes network errors as varied exception types.
            slicer.util.errorDisplay(
                "Unable to load the CBCT Dental Surgery sample volume. "
                "Please check your internet connection and try again.\n\n"
                f"Details: {error}"
            )
        finally:
            self.loadSampleVolumeButton.setEnabled(True)

    @staticmethod
    def _postDentalSurgeryVolumeNode(downloadResult):
        """Return the post-surgery volume from SampleData's download result.

        Current Slicer SampleData returns both the pre- and post-surgery volumes
        as a list. Older API variants may instead return one volume node or no
        node, the latter being resolved from the scene by the caller.
        """
        if isinstance(downloadResult, (list, tuple)):
            return next(
                (
                    node for node in downloadResult
                    if node is not None and node.GetName() == "PostDentalSurgery"
                ),
                None,
            )
        return downloadResult

    def _restoreProcessedSegmentation(self):
        """
        Restore the previous segmentation based on the currently selected volume node.
        """
        segmentationNode = self.processedVolumes.get(self.getCurrentVolumeNode())
        self.segmentationNodeSelector.setCurrentNode(segmentationNode)

    def _storeProcessedSegmentation(self):
        """
        Save the pair volumeNode / SegmentationNode for future input selector changes.
        """
        volumeNode = self.getCurrentVolumeNode()
        segmentationNode = self.getCurrentSegmentationNode()
        if volumeNode and segmentationNode:
            self.processedVolumes[volumeNode] = segmentationNode

    def updateSegmentEditorWidget(self, *_):
        """
        Update the segment editor status based on the current selected segmentation node.
        Hide previous segmentation node to make visualization smoother.
        """
        if self._prevSegmentationNode:
            self._prevSegmentationNode.SetDisplayVisibility(False)
            if hasattr(self, '_segmentationNodeObserver'):
                self._prevSegmentationNode.RemoveObserver(self._segmentationNodeObserver)

        segmentationNode = self.getCurrentSegmentationNode()
        self._prevSegmentationNode = segmentationNode

        if segmentationNode:
            self._segmentationNodeObserver = segmentationNode.AddObserver(
                "ModifiedEvent", self._updateResultUiVisibility
            )

        self.resultProcessor.initializeDisplay(segmentationNode, self.getCurrentVolumeNode())
        self.segmentEditorWidget.setSegmentationNode(segmentationNode)
        self.segmentEditorWidget.setSourceVolumeNode(self.getCurrentVolumeNode())
        self._showMeasurementsForSegmentation(segmentationNode)
        self._showResultQualityFlagsForSegmentation(segmentationNode)
        self._updateResultUiVisibility()

    def getCurrentVolumeNode(self):
        return self.inputSelector.currentNode()

    def getCurrentSegmentationNode(self):
        return self.segmentationNodeSelector.currentNode()

    def onInferenceFinished(self, *_):
        """
        Restore apply button visibility, load the segmentation results if the inference was not manually stopped.
        """
        self._stopInferenceProgress()
        if self.isStopping:
            self._setApplyVisible(True)
            self._updateResultUiVisibility()
            return

        try:
            self.onProgressInfo("Loading inference results...")
            self._loadSegmentationResults()
            self.onProgressInfo("Inference ended successfully.")
        except RuntimeError as e:
            slicer.util.errorDisplay(e)
            self.onProgressInfo(f"Error loading results :\n{e}")
        finally:
            self._setApplyVisible(True)
            self._updateResultUiVisibility()

    def _loadSegmentationResults(self):
        """
        Load the segmentation results from the logic segmentation folder. Update the segmentation display names and
        run some simple post-processing on the segmentation.
        """
        currentSegmentation = self.getCurrentSegmentationNode()
        segmentationNode = self.logic.loadSegmentation()
        segmentationNode.SetName(self.getCurrentVolumeNode().GetName() + "_Segmentation")
        if currentSegmentation is not None:
            self.resultProcessor.copyResultsToExistingNode(currentSegmentation, segmentationNode)
        else:
            self.segmentationNodeSelector.setCurrentNode(segmentationNode)
        slicer.app.processEvents()
        node = self.getCurrentSegmentationNode()
        volumeNode = self.getCurrentVolumeNode()
        self.resultProcessor.updateDisplay(node, volumeNode)
        self.resultProcessor.postProcess(node, volumeNode)
        self._calculateMeasurements(node)
        self._storeProcessedSegmentation()
        self._updateResultUiVisibility()

    def _calculateMeasurements(self, segmentationNode):
        """Collect labelmap volumes through Slicer's SegmentStatistics module.

        SegmentStatistics is part of Slicer rather than this extension, so a
        missing or incompatible module must not prevent users from seeing their
        inference result.  Empty (zero-volume) segments are intentionally left
        out; result-quality flags handle those separately.
        """
        if not segmentationNode:
            self._clearMeasurements()
            return
        try:
            import SegmentStatistics

            statisticsLogic = SegmentStatistics.SegmentStatisticsLogic()
            parameterNode = statisticsLogic.getParameterNode()
            parameterNode.SetParameter("Segmentation", segmentationNode.GetID())
            parameterNode.SetParameter("visibleSegmentsOnly", "False")
            statisticsLogic.computeStatistics()
            statistics = statisticsLogic.getStatistics()
            allVolumes = self._resultVolumesMm3(statistics, segmentationNode)
            presentVolumes = {
                name: volume for name, volume in allVolumes.items()
                if volume > 0
            }
            report = buildReport(presentVolumes)
            flags = self.resultProcessor.classifySegmentQuality(allVolumes)
        except (ImportError, AttributeError, RuntimeError, TypeError, ValueError) as error:
            # SegmentStatistics is optional; known module/API/data failures must
            # not prevent users from seeing their inference result. Unexpected
            # programming errors are allowed to surface during development.
            self.onProgressInfo(f"Measurements unavailable ({type(error).__name__}): {error}")
            self._measurementReports.pop(segmentationNode, None)
            self._qualityFlagsBySegmentation.pop(segmentationNode, None)
            self._clearMeasurements()
            self._clearResultQualityFlags()
            return

        self._measurementReports[segmentationNode] = report
        self._qualityFlagsBySegmentation[segmentationNode] = (flags, allVolumes)
        self._renderMeasurements(report)
        self._renderResultQualityFlags(flags, allVolumes)
        for name, status in flags:
            self.onProgressInfo(self._resultQualityFlagText(name, status, allVolumes[name]))

    def _resultVolumesMm3(self, statistics, segmentationNode):
        """Gather all fixed result volumes, treating omitted segments as empty."""
        statisticKey = "LabelmapSegmentStatisticsPlugin.volume_mm3"
        volumes = {}
        segmentation = segmentationNode.GetSegmentation()
        for index, name in enumerate(SegmentationResultProcessor.SEGMENT_LABELS):
            segmentId = SegmentationResultProcessor.segmentId(index)
            segment = segmentation.GetSegment(segmentId)
            rawVolume = statistics.get((segmentId, statisticKey)) if segment else 0
            try:
                volumes[name] = float(rawVolume) if rawVolume is not None else 0.0
            except (TypeError, ValueError):
                volumes[name] = 0.0
        return volumes

    def _showMeasurementsForSegmentation(self, segmentationNode):
        report = self._measurementReports.get(segmentationNode) if segmentationNode else None
        if report is None:
            self._clearMeasurements()
        else:
            self._renderMeasurements(report)

    def _showResultQualityFlagsForSegmentation(self, segmentationNode):
        result = self._qualityFlagsBySegmentation.get(segmentationNode) if segmentationNode else None
        if result is None:
            self._clearResultQualityFlags()
        else:
            self._renderResultQualityFlags(*result)

    @staticmethod
    def _resultQualityFlagText(name, status, volumeMm3):
        if status == SegmentationResultProcessor.QUALITY_MISSING:
            return f"⚠ {name} not detected."
        return f"⚠ {name} may be incomplete (only {volumeMm3:.1f} mm³)."

    def _renderResultQualityFlags(self, flags, volumesMm3):
        messages = [
            self._resultQualityFlagText(name, status, volumesMm3[name])
            for name, status in flags
        ]
        self.resultQualityFlagsLabel.setText("\n".join(messages))
        self.resultQualityFlagsLabel.setVisible(bool(messages))

    def _clearResultQualityFlags(self):
        if not hasattr(self, "resultQualityFlagsLabel"):
            return
        self.resultQualityFlagsLabel.setText("")
        self.resultQualityFlagsLabel.setVisible(False)

    def _renderMeasurements(self, report):
        self._measurementReport = report
        self.measurementsTable.setRowCount(len(report.rows))
        for rowIndex, row in enumerate(report.rows):
            for columnIndex, value in enumerate((row.structure, row.volume_cc, row.volume_mm3)):
                self.measurementsTable.setItem(rowIndex, columnIndex, qt.QTableWidgetItem(value))
        hasRows = bool(report.rows)
        self.copyMeasurementsButton.setEnabled(hasRows)
        self.saveMeasurementsButton.setEnabled(hasRows)
        self.measurementsCollapsibleButton.setVisible(
            hasRows and self._hasUsableSegmentation()
        )

    def _clearMeasurements(self):
        self._measurementReport = None
        if not hasattr(self, "measurementsTable"):
            return
        self.measurementsTable.clearContents()
        self.measurementsTable.setRowCount(0)
        self.copyMeasurementsButton.setEnabled(False)
        self.saveMeasurementsButton.setEnabled(False)
        self.measurementsCollapsibleButton.setVisible(False)

    def onCopyMeasurementsClicked(self):
        if self._measurementReport:
            qt.QApplication.clipboard().setText(self._measurementReport.csv_text)

    def onSaveMeasurementsClicked(self):
        if not self._measurementReport:
            return
        defaultPath = (
            str(Path(self._lastExportFolder) / "dentofac-segmentator-measurements.csv")
            if self._lastExportFolder else "dentofac-segmentator-measurements.csv"
        )
        fileName = qt.QFileDialog.getSaveFileName(
            self, "Save measurements", defaultPath, "CSV Files (*.csv)"
        )
        if not fileName:
            return
        filePath = Path(fileName)
        if filePath.suffix.lower() != ".csv":
            filePath = filePath.with_suffix(".csv")
        try:
            # UTF-8 BOM lets Excel reliably recognize the mm³ column header.
            filePath.write_text(self._measurementReport.csv_text, encoding="utf-8-sig")
        except OSError as error:
            slicer.util.errorDisplay(f"Failed to save measurements to {filePath}:\n{error}")

    def onInferenceError(self, errorMsg):
        """
        Displays error message in case of inference errors if inference was not manually stopped.
        """
        self._stopInferenceProgress()
        if self.isStopping:
            self._updateResultUiVisibility()
            return

        self._setApplyVisible(True)
        self._updateResultUiVisibility()

        from .ModelPath import validate, modelRoot, ValidationStatus
        from .InstallationStatus import weightsDiagnostic

        val_res = validate()
        if val_res.status not in (ValidationStatus.VALID, ValidationStatus.CHECK_UNAVAILABLE):
            _, weights_long = weightsDiagnostic(val_res, modelRoot())
            if weights_long:
                errorMsg = f"{weights_long}\n\nOriginal error:\n{errorMsg}"

        slicer.util.errorDisplay("Encountered error during inference :\n" + str(errorMsg))

    def onProgressInfo(self, infoMsg):
        """
        Prints progress information in module log console and in separate log dialog.
        """
        infoMsg = self.removeImageIOError(infoMsg)
        if self._inferenceProgressActive:
            # A malformed or changed nnU-Net log line must never interfere with
            # logging or inference; parsing is strictly an optional enhancement.
            try:
                for line in infoMsg.splitlines():
                    update = parseProgress(line)
                    if update is not None:
                        self._applyInferenceProgressUpdate(update)
            except Exception:  # noqa: the parser is intentionally best-effort
                pass
        logEntries = self.insertDatedInfoLogs(infoMsg)
        self._appendToLiveLog(logEntries)
        slicer.app.processEvents()

    @staticmethod
    def removeImageIOError(infoMsg):
        """
        Filter out ImageIO error which comes from ITK and is of no interest to current processing.
        """
        return "\n".join([msg for msg in infoMsg.strip().splitlines() if "Error ImageIO factory" not in msg])

    def insertDatedInfoLogs(self, infoMsg):
        now = qt.QDateTime.currentDateTime().toString("yyyy/MM/dd hh:mm:ss.zzz")
        entries = [f"{now} :: {msgLine}" for msgLine in infoMsg.splitlines()]
        self.fullInfoLogs.extend(entries)
        return entries

    def showInfoLogs(self):
        """
        Display the activity log in a non-modal dialog that can stay open during inference.
        """
        if self._logDialog is not None:
            try:
                self._logDialog.show()
                self._logDialog.raise_()
                self._logDialog.activateWindow()
                return
            except (RuntimeError, ValueError):
                self._logDialog = None
                self._liveLogTextEdit = None

        dialog = qt.QDialog(self)
        dialog.setWindowTitle("DentoFac Segmentator activity log")
        layout = qt.QVBoxLayout(dialog)

        textEdit = qt.QTextEdit()
        textEdit.setReadOnly(True)
        textEdit.setPlainText("\n".join(self.fullInfoLogs))
        textEdit.setLineWrapMode(qt.QTextEdit.NoWrap)
        self.moveTextEditToEnd(textEdit)
        layout.addWidget(textEdit)
        dialog.setWindowFlags(qt.Qt.Dialog | qt.Qt.WindowCloseButtonHint)
        self._resizeUtilityDialog(dialog)
        dialog.destroyed.connect(self._onLiveLogDialogDestroyed)
        self._logDialog = dialog
        self._liveLogTextEdit = textEdit
        dialog.show()

    def _appendToLiveLog(self, entries):
        if not entries or self._liveLogTextEdit is None:
            return
        try:
            self._liveLogTextEdit.insertPlainText("\n".join(entries) + "\n")
            self.moveTextEditToEnd(self._liveLogTextEdit)
        except (RuntimeError, ValueError):
            self._logDialog = None
            self._liveLogTextEdit = None

    def _onLiveLogDialogDestroyed(self, *_):
        self._logDialog = None
        self._liveLogTextEdit = None

    def onExportDiagnosticsClicked(self):
        import datetime
        from .SupportDiagnostics import SupportDiagnostics
        
        diag = SupportDiagnostics(
            device_text=self._selectedDevice(),
            get_logs_f=lambda: self.fullInfoLogs
        )
        data = diag.collect()
        json_text = diag.serialize_json(data)
        md_text = diag.serialize_markdown(data)

        dialog = qt.QDialog()
        dialog.setWindowTitle("Support Diagnostics")
        layout = qt.QVBoxLayout(dialog)

        textEdit = qt.QTextEdit()
        textEdit.setReadOnly(False)
        textEdit.setPlainText(md_text)
        textEdit.setLineWrapMode(qt.QTextEdit.NoWrap)
        layout.addWidget(textEdit)
        
        btnLayout = qt.QHBoxLayout()
        
        def onCopy():
            qt.QApplication.clipboard().setText(textEdit.toPlainText())
            slicer.util.infoDisplay("Copied to clipboard.")
            
        def onSave():
            fileName = qt.QFileDialog.getSaveFileName(dialog, "Save Diagnostics", f"dentofac-segmentator-diagnostics-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}.json", "JSON Files (*.json)")
            if fileName:
                try:
                    with open(fileName, "w", encoding="utf-8") as f:
                        f.write(json_text)
                    slicer.util.infoDisplay(f"Saved to {fileName}")
                except Exception as e:
                    slicer.util.errorDisplay(f"Failed to save {fileName}:\n{e}")

        def onReport():
            import urllib.parse
            
            # Support belongs to DentoFac. The acknowledgement and model-download
            # diagnostics retain the upstream links as provenance.
            repo_slug = "DentoFac/SlicerDentoFac"
            title = "Bug report: [Brief description]"
            
            body = diag.prepare_github_issue_body(textEdit.toPlainText())
            encoded_body = urllib.parse.quote(body)
                
            url = f"https://github.com/{repo_slug}/issues/new?title={urllib.parse.quote(title)}&body={encoded_body}"
            qt.QDesktopServices.openUrl(qt.QUrl(url))
        
        btnLayout.addWidget(createButton("Copy to clipboard", callback=onCopy))
        btnLayout.addWidget(createButton("Save to file...", callback=onSave))
        btnLayout.addWidget(createButton("Report an issue", callback=onReport))
        
        layout.addLayout(btnLayout)

        dialog.setWindowFlags(qt.Qt.WindowCloseButtonHint)
        self._resizeUtilityDialog(dialog)
        dialog.exec()

    @staticmethod
    def _resizeUtilityDialog(dialog):
        """Keep utility dialogs narrow while retaining enough vertical reading space."""
        mainWindow = slicer.util.mainWindow()
        if mainWindow:
            # Dialogs were 70% of the main window in both dimensions. Retain that
            # useful height, but use 40% of the former width (28% overall).
            dialog.resize(round(mainWindow.width * .28), round(mainWindow.height * .7))

    @staticmethod
    def moveTextEditToEnd(textEdit):
        cursor = textEdit.textCursor()
        cursor.movePosition(qt.QTextCursor.End)
        textEdit.setTextCursor(cursor)
        textEdit.verticalScrollBar().setValue(textEdit.verticalScrollBar().maximum)

    def getSelectedExportFormats(self):
        selectedFormats = ExportFormat(0)
        checkBoxes = {
            self.objCheckBox: ExportFormat.OBJ,
            self.stlCheckBox: ExportFormat.STL,
            self.niftiCheckBox: ExportFormat.NIFTI,
            self.gltfCheckBox: ExportFormat.GLTF
        }

        for checkBox, exportFormat in checkBoxes.items():
            if checkBox.isChecked():
                selectedFormats |= exportFormat

        return selectedFormats

    def _applyExportFormats(self, formats):
        self.stlCheckBox.setChecked(bool(formats & ExportFormat.STL))
        self.objCheckBox.setChecked(bool(formats & ExportFormat.OBJ))
        self.niftiCheckBox.setChecked(bool(formats & ExportFormat.NIFTI))
        self.gltfCheckBox.setChecked(bool(formats & ExportFormat.GLTF))

    def _loadPersistedSettings(self):
        # Device: apply with signals blocked so we don't trigger refreshInstallationStatus
        # before the status labels exist; the __init__ tail refreshes once afterwards.
        devices = [self._deviceOptionValue(i) for i in range(self.deviceComboBox.count)]
        device = self._settings.getDevice(devices, default=self._selectedDevice())
        idx = devices.index(device) if device in devices else -1
        if idx >= 0:
            self.deviceComboBox.blockSignals(True)
            self.deviceComboBox.setCurrentIndex(idx)
            self.deviceComboBox.blockSignals(False)

        # Surface smoothing: set after valueChanged is connected (it is, by construction time)
        # so the value propagates to the show3D slider / 3D view.
        self.surfaceSmoothingSlider.setValue(
            self._settings.getSurfaceSmoothing(default=self.surfaceSmoothingSlider.value)
        )

        # Export formats: default preserves today's "STL on, others off".
        self._applyExportFormats(
            self._settings.getExportFormats(default=self.getSelectedExportFormats())
        )

        # glTF reduction factor.
        self.reductionFactorSlider.setValue(
            self._settings.getReductionFactor(default=self.reductionFactorSlider.value)
        )

        # Last export folder (item 8 left this session-only).
        folder = self._settings.getLastExportFolder(default=self._lastExportFolder)
        if folder:
            self._lastExportFolder = folder
            self.exportFolderLabel.setText(folder)
            self.exportFolderLabel.setToolTip(folder)

    def _connectSettingsPersistence(self):
        self.deviceComboBox.currentIndexChanged.connect(self._persistDevice)
        self.surfaceSmoothingSlider.valueChanged.connect(self._persistSurfaceSmoothing)
        for box in (self.stlCheckBox, self.objCheckBox, self.niftiCheckBox, self.gltfCheckBox):
            box.toggled.connect(self._persistExportFormats)
        self.reductionFactorSlider.valueChanged.connect(self._persistReductionFactor)

    def _persistDevice(self, *_):
        self._settings.setDevice(self._selectedDevice())

    def _persistSurfaceSmoothing(self, *_):
        self._settings.setSurfaceSmoothing(self.surfaceSmoothingSlider.value)

    def _persistExportFormats(self, *_):
        self._settings.setExportFormats(self.getSelectedExportFormats())

    def _persistReductionFactor(self, *_):
        self._settings.setReductionFactor(self.reductionFactorSlider.value)

    def _segmentationHasContent(self, segmentationNode):
        if not segmentationNode:
            return False
        segmentation = segmentationNode.GetSegmentation()
        return bool(segmentation) and segmentation.GetNumberOfSegments() > 0

    def _hasUsableSegmentation(self):
        """Whether the selected node contains a result that can be reviewed or exported.

        This deliberately uses the node's segment count instead of the session-local
        ``processedVolumes`` mapping. A segmentation saved in a previous session or
        manually selected from the scene is therefore treated as a usable result too.
        """
        return self._segmentationHasContent(self.getCurrentSegmentationNode())

    def _updateResultUiVisibility(self, *_):
        """Show result-only controls only while a usable segmentation is selected."""
        hasResult = self._hasUsableSegmentation()
        self.refineResultCollapsibleButton.setVisible(hasResult)
        self.exportCollapsibleButton.setVisible(hasResult)
        if not hasResult:
            self.measurementsCollapsibleButton.setVisible(False)
        self._updateExportButtonState()

    def _updateExportButtonState(self, *_):
        self.exportButton.setEnabled(self._hasUsableSegmentation())

    def _clearExportResult(self):
        self._lastSuccessfulExportFolder = ""
        self.exportResultLabel.clear()
        self.exportResultLabel.setToolTip("")
        self.exportResultLabel.setVisible(False)
        self.openExportFolderButton.setEnabled(False)
        self.openExportFolderButton.setVisible(False)

    def onOpenExportFolderClicked(self, *_):
        """Open the folder containing the most recently successful export."""
        if not self._lastSuccessfulExportFolder:
            return

        folderUrl = qt.QUrl.fromLocalFile(self._lastSuccessfulExportFolder)
        if not qt.QDesktopServices.openUrl(folderUrl):
            slicer.util.warningDisplay(
                f"Could not open the export folder:\n{self._lastSuccessfulExportFolder}"
            )

    def onExportClicked(self):
        segmentationNode = self.getCurrentSegmentationNode()
        if not self._hasUsableSegmentation():
            slicer.util.warningDisplay(
                "Please select a segmentation with at least one segment before exporting."
            )
            return

        selectedFormats = self.getSelectedExportFormats()
        if selectedFormats == ExportFormat(0):
            slicer.util.warningDisplay("Please select at least one export format before exporting.")
            return

        folderPath = qt.QFileDialog.getExistingDirectory(
            self, "Please select the export folder", self._lastExportFolder
        )
        if not folderPath:
            return
        self._lastExportFolder = folderPath
        self._settings.setLastExportFolder(folderPath)
        self.exportFolderLabel.setText(folderPath)
        self.exportFolderLabel.setToolTip(folderPath)

        if (selectedFormats & ExportFormat.GLTF) and not self.exportManager.isOpenAnatomyAvailable():
            proceed = slicer.util.confirmYesNoDisplay(
                "glTF export requires the SlicerOpenAnatomy extension, which is not installed.\n\n"
                "If you are online it will be installed automatically now; otherwise glTF export "
                "will be skipped and you must install SlicerOpenAnatomy manually.\n\n"
                "Continue with the export?"
            )
            if not proceed:
                return

        self._clearExportResult()
        writtenFiles = None
        with slicer.util.tryWithErrorDisplay(f"Export to {folderPath} failed.", waitCursor=True):
            writtenFiles = self.exportManager.exportSegmentation(
                segmentationNode,
                folderPath,
                selectedFormats,
                gltfReductionFactor=self.reductionFactorSlider.value,
            )

        if writtenFiles:
            for name in writtenFiles:
                self.onProgressInfo(f"Wrote {name}")
            self._lastSuccessfulExportFolder = folderPath
            self.exportResultLabel.setText(
                f"Exported {len(writtenFiles)} file(s) to:\n{folderPath}"
            )
            self.exportResultLabel.setToolTip(folderPath)
            self.exportResultLabel.setVisible(True)
            self.openExportFolderButton.setEnabled(True)
            self.openExportFolderButton.setVisible(True)
        else:
            slicer.util.warningDisplay(
                f"Export to {folderPath} completed but no files were written. "
                f"Check that the segmentation contains segments and that the formats are supported."
            )

    def exportSegmentation(self, segmentationNode, folderPath, selectedFormats):
        return self.exportManager.exportSegmentation(
            segmentationNode, folderPath, selectedFormats,
            gltfReductionFactor=self.reductionFactorSlider.value,
        )

    @staticmethod
    def isNNUNetModuleInstalled():
        try:
            import SlicerNNUNetLib
            return True
        except ImportError:
            return False

    def _installNNUNetIfNeeded(self) -> bool:
        from SlicerNNUNetLib import InstallLogic
        logic = InstallLogic()
        logic.progressInfo.connect(self.onProgressInfo)

        # Only surface the busy indicator when an install will actually run, so a normal
        # Apply (dependencies already present) doesn't flash it. Callers hide it again in
        # their cleanup, *after* refreshing the installation status, so the bar stays up
        # across that refresh instead of blinking out before the panel catches up.
        if not PythonDependencyChecker.areDependenciesSatisfied():
            self._setInstallInProgress(
                "Installing PyTorch and nnU-Net dependencies (~2 GB download).\n"
                "This can take several minutes, and the bar may appear frozen while large "
                "packages are unpacked. Please keep Slicer open."
            )
        return logic.setupPythonRequirements()

    def _setInstallInProgress(self, message):
        """Show/hide the install busy indicator. Pass a message to show it, None to hide.

        Calls processEvents so the label paints before the GUI thread blocks inside pip.
        """
        if message is None:
            self.installProgressWidget.setVisible(False)
        else:
            self.installProgressLabel.setText(message)
            self.installProgressWidget.setVisible(True)
            self.installationStatusCollapsibleButton.collapsed = False
        slicer.app.processEvents()

    def _createSlicerSegmentationLogic(self):
        if not self.isNNUNetModuleInstalled():
            return None

        from SlicerNNUNetLib import SegmentationLogic
        return SegmentationLogic()

    def _connectSegmentationLogic(self):
        if self.logic is None:
            return

        self.logic.progressInfo.connect(self.onProgressInfo)
        self.logic.errorOccurred.connect(self.onInferenceError)
        self.logic.inferenceFinished.connect(self.onInferenceFinished)

    @classmethod
    def nnUnetFolder(cls) -> Path:
        from .ModelPath import modelRoot
        return modelRoot()
