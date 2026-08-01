"""NNUNet extension/Python dependency readiness, shared by DentoFac workflows."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DependencyStatus:
    extension_installed: bool
    python_requirements_installed: bool

    @property
    def ready(self) -> bool:
        return self.extension_installed and self.python_requirements_installed


class NNUNetDependencyService:
    def status(self) -> DependencyStatus:
        try:
            import SlicerNNUNetLib  # noqa: F401
            extension_installed = True
        except ImportError:
            extension_installed = False
        try:
            import torch  # noqa: F401
            import nnunetv2  # noqa: F401
            requirements_installed = True
        except ImportError:
            requirements_installed = False
        return DependencyStatus(extension_installed, requirements_installed)

    def install_python_requirements(self, progress_callback=None) -> bool:
        """Perform the explicit, user-initiated NNUNet Python setup."""
        try:
            from SlicerNNUNetLib import InstallLogic
        except ImportError:
            return False
        logic = InstallLogic()
        if progress_callback is not None:
            logic.progressInfo.connect(progress_callback)
        return bool(logic.setupPythonRequirements())
