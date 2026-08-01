"""DentoFac-owned model cache and nnU-Net model-layout validation.

The cache is deliberately outside the installed extension.  Its layout is
``<app-data>/DentoFac/models/<model-id>/<version>``; a workflow therefore never
writes into another extension's cache or an immutable package directory.
"""

from __future__ import annotations

import enum
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional


MODEL_CACHE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ModelDescriptor:
    model_id: str
    display_name: str
    source_url: str
    version: str
    expected_layout: str
    license_notice: str
    citation: str
    compatible_workflow_version: str
    integrity_sha256: Optional[str] = None


DENTAL_SEGMENTATOR_MODEL = ModelDescriptor(
    model_id="dental-segmentator-nnunet",
    display_name="DentoFac Segmentator nnU-Net model",
    source_url="https://github.com/gaudot/SlicerDentalSegmentator",
    version="upstream-latest",
    expected_layout="Dataset<id>_<name>/<trainer>__<plans>__<configuration>/fold_0/checkpoint_final.pth",
    license_notice="Downloaded from the upstream release; redistribution terms are not asserted by DentoFac.",
    citation="See the upstream SlicerDentalSegmentator project for model citation and provenance.",
    compatible_workflow_version="1",
)


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


EXPECTED_LAYOUT_DESCRIPTION = """<model cache>/
  Dataset<id>_<name>/
    <trainer>__<plans>__<configuration>/
      dataset.json
      plans.json
      fold_0/checkpoint_final.pth"""


def _default_application_data_directory() -> Path:
    """Return a writable application-data location without requiring Slicer.

    ``DENTOFAC_APP_DATA_DIR`` is intentionally supported for administrators and
    headless tests. Slicer uses Qt's per-application data location; the standard
    platform fallback keeps this service usable in command-line diagnostics.
    """
    configured = os.environ.get("DENTOFAC_APP_DATA_DIR")
    if configured:
        return Path(configured).expanduser()
    try:
        import qt
        location = qt.QStandardPaths.writableLocation(qt.QStandardPaths.AppDataLocation)
        if location:
            return Path(location)
    except (ImportError, AttributeError):
        pass
    return Path.home() / ".local" / "share" / "DentoFac"


class ModelStore:
    """Owns one model descriptor's private DentoFac cache.

    A legacy cache is never modified. ``copy_validated_legacy`` stages a copy on
    the destination filesystem and only replaces the destination after validation
    and an explicit confirmation callback. There is no automatic cleanup: version
    directories are retained until a future policy supplies a user-visible cleanup
    workflow.
    """

    def __init__(self, descriptor: ModelDescriptor, application_data_dir: Optional[Path] = None):
        self.descriptor = descriptor
        self.application_data_dir = Path(application_data_dir or _default_application_data_directory())

    @property
    def cache_root(self) -> Path:
        return self.application_data_dir / "DentoFac" / "models"

    @property
    def model_root(self) -> Path:
        return self.cache_root / self.descriptor.model_id / self.descriptor.version

    def metadata_path(self) -> Path:
        return self.model_root / "dentofac-model-cache.json"

    def write_metadata(self) -> None:
        import json
        self.model_root.mkdir(parents=True, exist_ok=True)
        tmp = self.metadata_path().with_suffix(".tmp")
        tmp.write_text(json.dumps({
            "schema_version": MODEL_CACHE_SCHEMA_VERSION,
            "model_id": self.descriptor.model_id,
            "model_version": self.descriptor.version,
            "source_url": self.descriptor.source_url,
        }, indent=2), encoding="utf-8")
        os.replace(tmp, self.metadata_path())

    def copy_validated_legacy(
        self, legacy_root: Path, confirm: Callable[[Path, Path], bool],
        validator: Callable[[Path], ValidationResult] = lambda path: validate_model(path),
    ) -> bool:
        """Copy a valid legacy installation after the caller obtains confirmation."""
        legacy_root = Path(legacy_root)
        source_validation = validator(legacy_root)
        if self.model_root.exists() or not source_validation.isValid or not source_validation.authoritative:
            return False
        if not confirm(legacy_root, self.model_root):
            return False
        self.model_root.parent.mkdir(parents=True, exist_ok=True)
        staging_parent = Path(tempfile.mkdtemp(prefix="dentofac-model-copy_", dir=self.model_root.parent))
        staged = staging_parent / self.model_root.name
        try:
            shutil.copytree(legacy_root, staged)
            staged_validation = validator(staged)
            if not staged_validation.isValid or not staged_validation.authoritative:
                return False
            os.replace(staged, self.model_root)
            self.write_metadata()
            return True
        finally:
            shutil.rmtree(staging_parent, ignore_errors=True)


def find_configuration_folder(root: Path) -> Optional[Path]:
    try:
        return next(
            path.parent for path in Path(root).rglob("dataset.json")
            if is_nnunet_dataset_path_valid(path)
        )
    except StopIteration:
        return None


def is_nnunet_dataset_path_valid(dataset_path: Path) -> bool:
    """Return whether ``dataset.json`` is in an expected nnU-Net layout."""
    configuration = dataset_path.parent
    dataset = configuration.parent
    return len(configuration.name.split("__")) == 3 and (
        dataset.name.startswith("Dataset") or dataset.name.isdigit()
    )


def has_flattened_layout(root: Path) -> bool:
    """Detect model-like files that are not arranged as a valid nnU-Net model."""
    if find_configuration_folder(root) is not None:
        return False
    return any(
        path.is_file() and (path.name in {"dataset.json", "plans.json"} or path.suffix == ".pth")
        for path in Path(root).rglob("*")
    )


def validate_model(root: Path, folds: str = "0", parameter=None) -> ValidationResult:
    root = Path(root)
    try:
        import SlicerNNUNetLib
        if parameter is None:
            parameter = SlicerNNUNetLib.Parameter(folds=folds, modelPath=root)
        is_valid, reason = parameter.isValid()
        configuration = getattr(parameter, "_configurationFolder", None) or find_configuration_folder(root)
        if is_valid:
            status = ValidationStatus.VALID
        elif find_configuration_folder(root) is None:
            status = ValidationStatus.FLATTENED if has_flattened_layout(root) else ValidationStatus.MISSING
        else:
            status = ValidationStatus.INVALID
        return ValidationResult(is_valid, reason, True, configuration, status)
    except ImportError:
        configuration = find_configuration_folder(root)
        if configuration is not None:
            return ValidationResult(True, "", False, configuration, ValidationStatus.VALID)
        status = ValidationStatus.FLATTENED if has_flattened_layout(root) else ValidationStatus.MISSING
        return ValidationResult(False, "Lenient check failed: no valid dataset.json found", False, None, status)
