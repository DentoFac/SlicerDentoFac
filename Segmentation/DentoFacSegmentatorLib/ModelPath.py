# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2024, Gauthier DOT
# Adapted by DentoFac from SlicerDentalSegmentator commit 476043f00009c372f0653dc759d69e2e559ed0f4; modified from upstream.

from pathlib import Path
from typing import Optional

from DentoFacLib.Models import (
    DENTAL_SEGMENTATOR_MODEL,
    ModelStore,
    ValidationResult,
    ValidationStatus,
    find_configuration_folder,
    validate_model,
)


EXPECTED_LAYOUT_DESCRIPTION = DENTAL_SEGMENTATOR_MODEL.expected_layout


def modelStore() -> ModelStore:
    """The shared DentoFac cache for this workflow's descriptor."""
    return ModelStore(DENTAL_SEGMENTATOR_MODEL)


def modelRoot() -> Path:
    """The DentoFac-owned, versioned writable model cache, never package files."""
    return modelStore().model_root


def legacyModelRoot() -> Path:
    """Return the old extension-relative cache for read-only, confirmed migration.

    Callers must validate and copy it through ``ModelStore``; it is never used for
    inference or modified by DentoFac.
    """
    return (Path(__file__).parent / ".." / "Resources" / "ML").resolve()


def findConfigurationFolder(root: Optional[Path] = None) -> Optional[Path]:
    """Locate the nnUNet *configuration* folder (the `<trainer>__<plans>__<conf>` dir
    that directly contains dataset.json) under `root` (defaults to modelRoot()).
    Returns None if no structurally-plausible folder is found. Pure-stdlib; reuses the
    existing rglob + lenient structural check."""
    rootPath = root or modelRoot()
    return find_configuration_folder(rootPath)


def _isNNUNetDatasetPathValid(datasetPath: Path) -> bool:
    from DentoFacLib.Models.ModelStore import _is_nnunet_dataset_path_valid
    return _is_nnunet_dataset_path_valid(datasetPath)


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
    return validate_model(root or modelRoot(), folds=folds, parameter=parameter)
