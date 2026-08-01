# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2024, Gauthier DOT
# Adapted by DentoFac from SlicerDentalSegmentator commit 476043f00009c372f0653dc759d69e2e559ed0f4; modified from upstream.

import enum
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


class ValidationStatus(enum.Enum):
    VALID = "valid"
    MISSING = "missing"
    INVALID = "invalid"
    FLATTENED = "flattened"
    CHECK_UNAVAILABLE = "check-unavailable"


@dataclass
class ValidationResult:
    isValid: bool
    reason: str
    authoritative: bool
    configurationFolder: Optional[Path]
    status: ValidationStatus


EXPECTED_LAYOUT_DESCRIPTION = """Resources/ML/
  Dataset<id>_<name>/
    <trainer>__<plans>__<configuration>/
      dataset.json
      plans.json
      fold_0/checkpoint_final.pth"""


def modelRoot() -> Path:
    """The Resources/ML directory (model root). Single source of the hardcoded location.
    Replaces SegmentationWidget.nnUnetFolder()'s body."""
    fileDir = Path(__file__).parent
    return fileDir.joinpath("..", "Resources", "ML").resolve()


def findConfigurationFolder(root: Optional[Path] = None) -> Optional[Path]:
    """Locate the nnUNet *configuration* folder (the `<trainer>__<plans>__<conf>` dir
    that directly contains dataset.json) under `root` (defaults to modelRoot()).
    Returns None if no structurally-plausible folder is found. Pure-stdlib; reuses the
    existing rglob + lenient structural check."""
    rootPath = root or modelRoot()
    try:
        return next(
            datasetPath.parent
            for datasetPath in rootPath.rglob("dataset.json")
            if _isNNUNetDatasetPathValid(datasetPath)
        )
    except StopIteration:
        return None


def _isNNUNetDatasetPathValid(datasetPath: Path) -> bool:
    configurationFolder = datasetPath.parent
    datasetFolder = configurationFolder.parent
    return (
        len(configurationFolder.name.split("__")) == 3
        and (datasetFolder.name.startswith("Dataset") or datasetFolder.name.isdigit())
    )


def detectFlattenedLayout(root: Optional[Path] = None) -> bool:
    """Returns True if weight-ish files exist but not in a valid nested config folder."""
    rootPath = root or modelRoot()
    if findConfigurationFolder(rootPath) is not None:
        return False
    
    for path in rootPath.rglob("*"):
        if path.is_file() and (path.name == "dataset.json" or path.name == "plans.json" or path.suffix == ".pth"):
            return True
    return False


def inferenceModelPath(root: Optional[Path] = None) -> Path:
    """The exact path to hand to SlicerNNUNetLib.Parameter(modelPath=...). Return the
    model root (Parameter resolves down from it); centralizing it here means callers stop
    hardcoding it."""
    return root or modelRoot()


def validate(root: Optional[Path] = None, folds: str = "0", parameter=None) -> ValidationResult:
    """Authoritative validation. If SlicerNNUNetLib is importable, build a Parameter with
    modelPath=inferenceModelPath(root) and the given folds and delegate to
    Parameter.isValid(), mapping its (bool, reason) into ValidationResult. If
    SlicerNNUNetLib is NOT importable (headless), fall back to the lenient structural
    check and set result.authoritative = False so callers can tell the difference.
    
    Note: The headless fallback only produces VALID or MISSING statuses, and cannot
    verify if model weights (plans.json, checkpoint_final.pth) are actually present.
    UI components must not trust a headless 'valid' status as proof of readiness."""
    rootPath = root or modelRoot()
    modelPathVal = inferenceModelPath(rootPath)

    try:
        import SlicerNNUNetLib
        if parameter is None:
            parameter = SlicerNNUNetLib.Parameter(folds=folds, modelPath=modelPathVal)
        isValid, reason = parameter.isValid()
        
        configFolder = None
        if isValid:
            try:
                configFolder = parameter._configurationFolder
            except AttributeError:
                pass
        
        if configFolder is None:
            configFolder = findConfigurationFolder(rootPath)

        if isValid:
            status = ValidationStatus.VALID
        else:
            if findConfigurationFolder(rootPath) is None:
                if detectFlattenedLayout(rootPath):
                    status = ValidationStatus.FLATTENED
                else:
                    status = ValidationStatus.MISSING
            else:
                status = ValidationStatus.INVALID

        return ValidationResult(
            isValid=isValid,
            reason=reason,
            authoritative=True,
            configurationFolder=configFolder,
            status=status
        )
    except ImportError:
        configFolder = findConfigurationFolder(rootPath)
        if configFolder is None:
            if detectFlattenedLayout(rootPath):
                status = ValidationStatus.FLATTENED
            else:
                status = ValidationStatus.MISSING
            return ValidationResult(
                isValid=False,
                reason="Lenient check failed: no valid dataset.json found",
                authoritative=False,
                configurationFolder=None,
                status=status
            )
        else:
            return ValidationResult(
                isValid=True,
                reason="",
                authoritative=False,
                configurationFolder=configFolder,
                status=ValidationStatus.VALID
            )
