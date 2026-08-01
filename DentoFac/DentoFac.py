import qt
import slicer
from slicer.ScriptedLoadableModule import ScriptedLoadableModule, ScriptedLoadableModuleWidget

from DentoFacLib import (
    DENTAL_SEGMENTATOR_MODEL,
    ModelStore,
    NNUNetDependencyService,
    collect_runtime_status,
    collect_segmentator_readiness,
)


class DentoFac(ScriptedLoadableModule):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent.title = "DentoFac Hub"
        self.parent.categories = ["DentoFac"]
        self.parent.contributors = ["DentoFac contributors"]
        self.parent.helpText = (
            "Set up and inspect the shared DentoFac environment. "
            "Workflow-specific actions live in their own DentoFac modules."
        )


class DentoFacWidget(ScriptedLoadableModuleWidget):
    def setup(self):
        super().setup()

        content = qt.QWidget()
        layout = qt.QFormLayout(content)
        self.layout.addWidget(content)

        introduction = qt.QLabel(
            "DentoFac Hub is the single place for shared setup, model storage, "
            "runtime checks, model storage, and diagnostics. Segmentator execution "
            "and clinical controls remain in DentoFac Segmentator."
        )
        introduction.wordWrap = True
        layout.addRow(introduction)

        self.pythonVersionLabel = qt.QLabel()
        self.slicerVersionLabel = qt.QLabel()
        self.statusLabel = qt.QLabel()
        self.statusLabel.wordWrap = True
        layout.addRow("Python:", self.pythonVersionLabel)
        layout.addRow("Slicer:", self.slicerVersionLabel)
        layout.addRow("Shared runtime:", self.statusLabel)

        self.segmentatorStatusLabel = qt.QLabel()
        self.segmentatorStatusLabel.wordWrap = True
        layout.addRow("DentoFac Segmentator:", self.segmentatorStatusLabel)

        self.installDependenciesButton = qt.QPushButton("Install NNUNet requirements")
        self.installDependenciesButton.connect("clicked()", self.installDependencies)
        layout.addRow(self.installDependenciesButton)

        self.downloadModelButton = qt.QPushButton("Download Segmentator model")
        self.downloadModelButton.connect("clicked()", self.downloadModel)
        layout.addRow(self.downloadModelButton)

        self.importLegacyModelButton = qt.QPushButton("Import validated legacy model…")
        self.importLegacyModelButton.connect("clicked()", self.importLegacyModel)
        layout.addRow(self.importLegacyModelButton)

        refreshButton = qt.QPushButton("Refresh status")
        refreshButton.connect("clicked()", self.refresh)
        layout.addRow(refreshButton)
        layout.addRow(qt.QLabel(""))

        self.refresh()

    def refresh(self):
        status = collect_runtime_status()
        self.pythonVersionLabel.text = status.python_version
        self.slicerVersionLabel.text = status.slicer_version or "Unavailable"
        readiness = collect_segmentator_readiness()
        self.statusLabel.text = "Shared readiness and versioned DentoFac model cache are active."
        self.segmentatorStatusLabel.text = readiness.summary
        self.installDependenciesButton.setEnabled(readiness.dependency_ready is False)
        self.downloadModelButton.setEnabled(readiness.dependency_ready)

    def installDependencies(self):
        service = NNUNetDependencyService()
        if not service.status().extension_installed:
            slicer.util.errorDisplay(
                "Install the NNUNet extension in Slicer's Extension Manager and restart, then return to DentoFac Hub."
            )
            self.refresh()
            return
        self.installDependenciesButton.setEnabled(False)
        try:
            if not service.install_python_requirements():
                slicer.util.errorDisplay("NNUNet Python requirement installation did not complete. Check the application log and retry.")
        finally:
            self.refresh()

    def _segmentator_checker(self):
        # The model descriptor/cache is shared; the release format and progress UI
        # remain workflow-specific until another workflow uses the same protocol.
        from DentoFacSegmentatorLib.PythonDependencyChecker import PythonDependencyChecker
        return PythonDependencyChecker(destWeightFolder=ModelStore(DENTAL_SEGMENTATOR_MODEL).model_root)

    def downloadModel(self):
        self.downloadModelButton.setEnabled(False)
        try:
            self._segmentator_checker().downloadWeightsIfNeeded(lambda message: slicer.util.showStatusMessage(message, 3000))
        finally:
            self.refresh()

    def importLegacyModel(self):
        from DentoFacSegmentatorLib.ModelPath import legacyModelRoot
        store = ModelStore(DENTAL_SEGMENTATOR_MODEL)
        legacy = legacyModelRoot()
        if not legacy.exists():
            slicer.util.infoDisplay("No legacy Segmentator model cache was found.")
            return
        confirmed = qt.QMessageBox.question(
            self, "Import legacy model",
            f"Copy the validated legacy model from:\n{legacy}\n\nto DentoFac's private cache:\n{store.model_root}\n\nThe original will not be changed.",
        ) == qt.QMessageBox.Yes
        if not confirmed:
            return
        from DentoFacLib.Models import validate_model
        if not store.copy_validated_legacy(legacy, lambda *_: True, validate_model):
            slicer.util.errorDisplay("The legacy model was invalid, the DentoFac cache already exists, or the copy could not be completed.")
        self.refresh()
