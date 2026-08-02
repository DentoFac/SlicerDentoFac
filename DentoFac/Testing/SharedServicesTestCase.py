"""Headless tests for DentoFacLib shared infrastructure."""

import tempfile
from pathlib import Path
from unittest import mock

from DentoFacLib.Diagnostics import DiagnosticsCollector, tail_logs
from DentoFacLib.Models import (
    DENTAL_SEGMENTATOR_MODEL, ModelStore, ValidationResult, ValidationStatus, validate_model,
)
from DentoFacLib.Dependencies import DependencyStatus
from DentoFacLib.ExtensionStatus import ExpectedExtension, evaluate_required_extensions


def _valid_model_tree(root: Path) -> None:
    config = root / "Dataset111_Test" / "nnUNetTrainer__nnUNetPlans__3d_fullres"
    (config / "fold_0").mkdir(parents=True)
    (config / "dataset.json").write_text("{}", encoding="utf-8")
    (config / "plans.json").write_text("{}", encoding="utf-8")
    (config / "fold_0" / "checkpoint_final.pth").write_bytes(b"test")


def test_model_store_uses_private_versioned_cache_and_confirmed_copy():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        legacy = root / "legacy"
        _valid_model_tree(legacy)
        store = ModelStore(DENTAL_SEGMENTATOR_MODEL, root / "app-data")

        assert "DentoFac/models" in str(store.model_root)
        authoritative = lambda path: ValidationResult(True, "", True, path, ValidationStatus.VALID)
        assert store.copy_validated_legacy(legacy, lambda source, target: source == legacy, authoritative)
        assert legacy.exists()  # coexistence: a legacy source is never changed
        assert validate_model(store.model_root).isValid
        assert store.metadata_path().exists()


def test_model_store_never_copies_without_confirmation_or_when_destination_exists():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        legacy = root / "legacy"
        _valid_model_tree(legacy)
        store = ModelStore(DENTAL_SEGMENTATOR_MODEL, root / "app-data")
        authoritative = lambda path: ValidationResult(True, "", True, path, ValidationStatus.VALID)
        assert not store.copy_validated_legacy(legacy, lambda *_: False, authoritative)
        assert not store.model_root.exists()


def test_shared_diagnostics_is_bounded_and_provider_failures_are_contained():
    assert tail_logs(["a" * 10] * 4, max_lines=4, max_bytes=20) == ["a" * 10, "a" * 10]
    data = DiagnosticsCollector(lambda: {"workflow": "segmentator"}).collect()
    assert data["workflow"]["workflow"] == "segmentator"
    failed = DiagnosticsCollector(lambda: (_ for _ in ()).throw(RuntimeError())).collect()
    assert "collection_error" in failed["workflow"]


def test_hub_readiness_propagates_dependency_and_model_state():
    from DentoFacLib.Models import ValidationResult, ValidationStatus
    from DentoFacLib import RuntimeStatus

    with mock.patch.object(
        RuntimeStatus.NNUNetDependencyService, "status",
        return_value=DependencyStatus(True, False),
    ), mock.patch.object(
        RuntimeStatus, "validate_model",
        return_value=ValidationResult(False, "missing", True, None, ValidationStatus.MISSING),
    ):
        readiness = RuntimeStatus.collect_segmentator_readiness()
    assert not readiness.dependency_ready
    assert not readiness.model_ready
    assert "Python requirements" in readiness.summary


def test_required_extensions_all_present_at_accepted_revision():
    report = evaluate_required_extensions(
        [ExpectedExtension("NNUNet", "0cb736d", ("0cb736d",))],
        {"NNUNet": "0cb736d"},
    )
    assert report.all_ok
    assert report.rows[0].status == "present_ok"


def test_required_extensions_marks_a_missing_extension():
    report = evaluate_required_extensions(
        [ExpectedExtension("NNUNet", "0cb736d", ("0cb736d",))],
        {"NNUNet": None},
    )
    assert not report.all_ok
    assert report.rows[0].status == "missing"


def test_required_extensions_marks_a_wrong_revision():
    report = evaluate_required_extensions(
        [ExpectedExtension("NNUNet", "0cb736d", ("0cb736d",))],
        {"NNUNet": "different-sha"},
    )
    assert not report.all_ok
    assert report.rows[0].status == "version_mismatch"


def test_required_extensions_supports_a_present_only_gate():
    report = evaluate_required_extensions(
        [ExpectedExtension("NNUNet", "site managed", (), require_accepted_revision=False)],
        {"NNUNet": "any-revision"},
    )
    assert report.all_ok
    assert report.rows[0].status == "present_ok"


def test_required_extensions_matches_a_full_detected_sha_to_a_short_accepted_sha():
    full_revision = "0cb736d" + "a" * 33
    report = evaluate_required_extensions(
        [ExpectedExtension("NNUNet", "0cb736d", ["0cb736d"])],
        {"NNUNet": full_revision},
    )
    assert report.all_ok
    assert report.rows[0].status == "present_ok"


def test_required_extensions_matches_a_short_detected_sha_to_a_full_accepted_sha():
    full_revision = "0cb736d" + "a" * 33
    report = evaluate_required_extensions(
        [ExpectedExtension("NNUNet", "0cb736d", [full_revision])],
        {"NNUNet": "0cb736d"},
    )
    assert report.all_ok
    assert report.rows[0].status == "present_ok"


def test_required_extensions_rejects_a_partial_prefix_collision():
    report = evaluate_required_extensions(
        [ExpectedExtension("NNUNet", "0cb736d", ["0cb736d"])],
        {"NNUNet": "0cb999e"},
    )
    assert not report.all_ok
    assert report.rows[0].status == "version_mismatch"


def test_required_extensions_matches_case_insensitively():
    report = evaluate_required_extensions(
        [ExpectedExtension("NNUNet", "0cb736d", ["0cb736d"])],
        {"NNUNet": "0CB736D"},
    )
    assert report.all_ok
    assert report.rows[0].status == "present_ok"


def test_required_extensions_keeps_unknown_and_missing_revisions_unhealthy():
    manifest = [ExpectedExtension("NNUNet", "0cb736d", ["0cb736d"])]
    unknown = evaluate_required_extensions(manifest, {"NNUNet": "unknown"})
    missing = evaluate_required_extensions(manifest, {"NNUNet": None})
    blank = evaluate_required_extensions(manifest, {"NNUNet": "  "})
    assert unknown.rows[0].status == "version_mismatch"
    assert missing.rows[0].status == "missing"
    assert blank.rows[0].status == "version_mismatch"
