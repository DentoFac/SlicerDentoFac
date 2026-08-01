import qt
from slicer.ScriptedLoadableModule import ScriptedLoadableModule, ScriptedLoadableModuleWidget

from DentoFacLib import collect_runtime_status


class DentoFacSegmentator(ScriptedLoadableModule):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent.title = "DentoFac Segmentator"
        self.parent.categories = ["DentoFac"]
        self.parent.contributors = ["DentoFac contributors"]
        self.parent.helpText = (
            "DentoFac's dental segmentation workflow. "
            "The clinical workflow will be added here in tested slices."
        )


class DentoFacSegmentatorWidget(ScriptedLoadableModuleWidget):
    def setup(self):
        super().setup()

        layout = self.layout

        message = qt.QLabel(
            "The DentoFac Segmentator module boundary is ready. "
            "Clinical inference, model migration, and exports have not yet been "
            "ported from the legacy extension."
        )
        message.wordWrap = True
        layout.addWidget(message)

        status = collect_runtime_status()
        layout.addWidget(
            qt.QLabel(
                f"Shared DentoFac library imported successfully "
                f"(Python {status.python_version})."
            )
        )
        layout.addStretch()
