import qt
import slicer
from slicer.ScriptedLoadableModule import ScriptedLoadableModule, ScriptedLoadableModuleWidget

from DentoFacLib import collect_runtime_status


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
            "runtime checks, and diagnostics. Dependency installation and model "
            "management will be added in a later migration slice."
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

        refreshButton = qt.QPushButton("Refresh status")
        refreshButton.connect("clicked()", self.refresh)
        layout.addRow(refreshButton)
        layout.addRow(qt.QLabel(""))

        self.refresh()

    def refresh(self):
        status = collect_runtime_status()
        self.pythonVersionLabel.text = status.python_version
        self.slicerVersionLabel.text = status.slicer_version or "Unavailable"
        self.statusLabel.text = (
            "Scaffold ready. No shared dependencies or models are managed yet."
        )
