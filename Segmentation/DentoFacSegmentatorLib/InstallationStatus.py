# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2024, Gauthier DOT
# Adapted by DentoFac from SlicerDentalSegmentator commit 476043f00009c372f0653dc759d69e2e559ed0f4; modified from upstream.

from dataclasses import dataclass
from typing import List, Optional, Tuple
from pathlib import Path
from .ModelPath import validate, ValidationStatus, ValidationResult


def weightsDiagnostic(val_res: ValidationResult, root: Path) -> Tuple[str, str]:
    from .ModelPath import EXPECTED_LAYOUT_DESCRIPTION

    path_to_report = val_res.configurationFolder if val_res.configurationFolder else root

    if not val_res.authoritative or val_res.status == ValidationStatus.CHECK_UNAVAILABLE:
        return "Cannot verify (NNUNet not installed)", ""
    elif val_res.status == ValidationStatus.INVALID:
        short = "Installed but invalid"
        long_guidance = (
            f"Weights are present at {path_to_report} but invalid.\n\n"
            f"Details: {val_res.reason}\n\n"
            f"Expected layout:\n{EXPECTED_LAYOUT_DESCRIPTION}\n\n"
            "Click *Re-download weights* to replace the broken files."
        )
        return short, long_guidance
    elif val_res.status == ValidationStatus.FLATTENED:
        short = "Legacy/flattened layout detected"
        long_guidance = (
            f"A legacy (pre-nested) layout was detected at {path_to_report}.\n\n"
            f"Expected nested layout:\n{EXPECTED_LAYOUT_DESCRIPTION}\n\n"
            "Click *Re-download weights* to replace it with the correct structure."
        )
        return short, long_guidance
    elif val_res.status == ValidationStatus.MISSING:
        return "Not installed (will download on Apply)", ""
    else:
        return "Valid", ""


def cuda_diagnostic() -> Optional[str]:
    """Explain the CUDA situation in plain language, or None when CUDA is fully usable.

    Distinguishes the cases users routinely confuse with "my GPU is broken":
      - PyTorch installed as a CPU-only build (no CUDA support compiled in),
      - no CUDA-capable GPU / driver present,
      - a GPU that is *older* than the compute capabilities this PyTorch build was
        compiled for (recent PyTorch wheels drop support for older CUDA cores, so
        torch.cuda.is_available() can be True yet inference still crashes).
    Safe to call regardless of whether torch is importable.
    """
    try:
        import torch
    except ImportError:
        return "PyTorch is not installed"

    if torch.version.cuda is None:
        return "PyTorch is a CPU-only build (installed without CUDA support)"

    if not torch.cuda.is_available():
        return "No CUDA-capable GPU or driver detected"

    # CUDA is available; check the GPU is new enough for this PyTorch build.
    try:
        major, minor = torch.cuda.get_device_capability(0)
        device_sm = major * 10 + minor
        name = torch.cuda.get_device_name(0)
        compiled = sorted(
            int(arch.split("_")[1])
            for arch in torch.cuda.get_arch_list()
            if arch.startswith("sm_")
        )
        if compiled and device_sm < compiled[0]:
            return (
                f"GPU '{name}' (sm_{device_sm}) is older than this PyTorch build supports "
                f"(compiled for sm_{compiled[0]}+); CUDA inference will likely fail"
            )
    except Exception:  # noqa - diagnostics must never raise
        pass
    return None


def is_device_available(device_text: str) -> Optional[bool]:
    """Whether the compute device is usable.

    Returns True/False when it can be determined, or None if SlicerNNUNetLib is not
    importable (headless / NNUNet not installed) and availability cannot be verified.
    """
    try:
        import SlicerNNUNetLib
        from .ModelPath import inferenceModelPath
        param = SlicerNNUNetLib.Parameter(folds="0", modelPath=inferenceModelPath(), device=device_text)
        available = param.isSelectedDeviceAvailable()
        # torch.cuda.is_available() can be True for a GPU too old for this PyTorch
        # build; treat that as unavailable so the option is greyed out and we use CPU.
        if device_text == "cuda" and available and cuda_diagnostic() is not None:
            available = False
        return available
    except ImportError:
        return None


def device_unavailable_reason(device_text: str) -> Optional[str]:
    """Return a concise user-facing reason when one can be determined.

    This is deliberately separate from :func:`is_device_available`: callers that
    only need a boolean should not have to interpret diagnostic text.  CUDA has
    a specific runtime diagnostic; for other backends we can safely state only
    that the backend is unavailable.
    """
    if device_text == "cuda":
        return cuda_diagnostic() or "CUDA is not available"
    if device_text == "mps":
        return "Apple Metal (MPS) is not available"
    if device_text == "cpu":
        return "CPU support is not available"
    return None

@dataclass
class StatusLine:
    ok: bool
    label: str
    detail: str
    advisory: bool = False  # informational only (e.g. GPU acceleration note); not a pass/fail check

@dataclass
class InstallationStatus:
    lines: List[StatusLine]
    val_res: ValidationResult
    actual_device: Optional[str] = None

    @property
    def is_ready(self) -> bool:
        # Ignore the device line (fallback to CPU is fine) and advisory lines so they
        # don't block "Ready to run".
        return all(
            line.ok for line in self.lines
            if not line.advisory and line.label != "Compute device"
        )

def collect_status(device_text: str, check_online: bool = False) -> InstallationStatus:
    from .PythonDependencyChecker import PythonDependencyChecker

    from .SegmentationWidget import SegmentationWidget

    # 1. NNUNet extension
    nnunet_installed = SegmentationWidget.isNNUNetModuleInstalled()
    if nnunet_installed:
        nnunet_line = StatusLine(ok=True, label="NNUNet extension", detail="Installed")
    else:
        nnunet_line = StatusLine(ok=False, label="NNUNet extension", detail="Not installed")

    # 2. Python dependencies
    deps_ok = PythonDependencyChecker.areDependenciesSatisfied()
    if deps_ok:
        deps_line = StatusLine(ok=True, label="Python dependencies (torch, nnunetv2)", detail="Satisfied")
    else:
        deps_line = StatusLine(ok=False, label="Python dependencies (torch, nnunetv2)", detail="Not satisfied")

    # 3. Compute device
    gpu_line = None
    param = None
    actual_device = None
    try:
        # Only the *extension* import can fail here; keep it separate from the
        # torch-dependent device probe below so a missing torch isn't misreported as a
        # missing extension.
        import SlicerNNUNetLib
        from .ModelPath import inferenceModelPath
        param = SlicerNNUNetLib.Parameter(folds="0", modelPath=inferenceModelPath(), device=device_text)
    except ImportError:
        param = None

    if param is None:
        device_line = StatusLine(ok=False, label="Compute device", detail="Cannot verify (NNUNet extension not installed)")
    elif not deps_ok:
        # Extension present but torch/nnunetv2 not yet installed. isSelectedDeviceAvailable()
        # imports torch, so defer to the Python-dependencies line rather than probing.
        # (param is kept for weight validation below; Parameter.isValid() doesn't need torch.)
        device_line = StatusLine(ok=False, label="Compute device", detail="Cannot verify until Python dependencies are installed")
    else:
        is_avail = param.isSelectedDeviceAvailable()

        # CUDA can report "available" while the GPU is too old for this PyTorch build;
        # cuda_diagnostic() returns a reason in that case (and for CPU-only / no-GPU
        # builds). Treat any such reason as CUDA being unusable so we fall back to CPU.
        cuda_reason = cuda_diagnostic()
        cuda_usable = cuda_reason is None
        if device_text == "cuda" and not cuda_usable:
            is_avail = False
        actual_device = device_text if is_avail else "cpu"

        if is_avail:
            detail = f"Using '{actual_device}'"
        else:
            detail = f"Selected '{device_text}' is unavailable. Falling back to '{actual_device}'"

        device_line = StatusLine(ok=is_avail, label="Compute device", detail=detail)

        # Explain the CUDA situation on its own advisory line (not on the active-device
        # line), so a green "Using cpu" isn't muddied and the reason stays visible even
        # after the UI auto-switches the selection to CPU.
        if not cuda_usable:
            gpu_line = StatusLine(
                ok=True, advisory=True, label="GPU acceleration",
                detail=f"Unavailable — {cuda_reason}",
            )

    # 4. Model weights
    val_res = validate(folds="0", parameter=param)
    from .ModelPath import modelRoot
    short_msg, _ = weightsDiagnostic(val_res, modelRoot())

    if not val_res.authoritative:
        weights_line = StatusLine(ok=False, label="Model weights", detail=short_msg)
    elif val_res.status == ValidationStatus.MISSING:
        weights_line = StatusLine(ok=False, label="Model weights", detail=short_msg)
    elif val_res.status in (ValidationStatus.INVALID, ValidationStatus.FLATTENED):
        weights_line = StatusLine(ok=False, label="Model weights", detail=short_msg)
    else:
        # VALID
        update_msg = ""
        if check_online:
            checker = PythonDependencyChecker()
            if checker.areWeightsOutdated():
                update_msg = " (update available)"
            else:
                update_msg = " (no update detected)"

        weights_line = StatusLine(ok=True, label="Model weights", detail=f"Valid{update_msg}")

    lines = [nnunet_line, deps_line, device_line]
    if gpu_line is not None:
        lines.append(gpu_line)
    lines.append(weights_line)
    return InstallationStatus(lines=lines, val_res=val_res, actual_device=actual_device)
