"""Small, read-only runtime facts used by the initial DentoFac Hub."""

from dataclasses import dataclass
import sys
from typing import Optional

from .Dependencies import NNUNetDependencyService
from .Models import DENTAL_SEGMENTATOR_MODEL, ModelStore, validate_model


@dataclass(frozen=True)
class RuntimeStatus:
    python_version: str
    slicer_version: Optional[str]


@dataclass(frozen=True)
class WorkflowReadiness:
    """Small shared readiness contract consumed by the Hub and workflows."""
    dependency_ready: bool
    model_ready: bool
    model_authoritative: bool
    summary: str


def collect_runtime_status() -> RuntimeStatus:
    slicer_version = None
    try:
        import slicer

        slicer_version = getattr(slicer.app, "applicationVersion", None)
    except (ImportError, AttributeError):
        pass

    return RuntimeStatus(
        python_version=sys.version.split()[0],
        slicer_version=slicer_version,
    )


def collect_segmentator_readiness() -> WorkflowReadiness:
    dependencies = NNUNetDependencyService().status()
    validation = validate_model(ModelStore(DENTAL_SEGMENTATOR_MODEL).model_root)
    model_ready = validation.isValid and validation.authoritative
    if not dependencies.extension_installed:
        summary = "NNUNet extension is not installed."
    elif not dependencies.python_requirements_installed:
        summary = "NNUNet Python requirements are not installed."
    elif not validation.authoritative:
        summary = "Model cache cannot be verified until NNUNet is available."
    elif not model_ready:
        summary = "Segmentator model is not installed or is invalid."
    else:
        summary = "DentoFac Segmentator is ready."
    return WorkflowReadiness(dependencies.ready, model_ready, validation.authoritative, summary)
