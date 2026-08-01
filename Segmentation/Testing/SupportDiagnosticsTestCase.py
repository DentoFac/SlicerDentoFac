# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2024, Gauthier DOT
# Adapted by DentoFac from SlicerDentalSegmentator commit 476043f00009c372f0653dc759d69e2e559ed0f4; modified from upstream.

from ._headless_stubs import install as _install; _install()

import json
from pathlib import Path
from DentoFacSegmentatorLib.SupportDiagnostics import SupportDiagnostics, tail_logs
from DentoFacSegmentatorLib.InstallationStatus import InstallationStatus, StatusLine
from DentoFacSegmentatorLib.ModelPath import ValidationResult, ValidationStatus

class TestSupportDiagnostics:
    def test_tail_logs_lines(self):
        logs = [f"line {i}" for i in range(10)]
        tailed = tail_logs(logs, max_lines=5)
        assert len(tailed) == 5
        assert tailed == [f"line {i}" for i in range(5, 10)]
        
    def test_tail_logs_bytes(self):
        long_logs = ["a" * 1000] * 20
        # max_bytes = 10000, 10 lines of 1000 chars is 10000.
        tailed_bytes = tail_logs(long_logs, max_lines=100, max_bytes=10000)
        assert len(tailed_bytes) == 10

    def test_full_bundle(self):
        val_res = ValidationResult(True, None, True, Path("test_config_folder"), ValidationStatus.VALID)
        status = InstallationStatus(
            lines=[StatusLine(ok=True, label="Compute device", detail="Using 'cuda'")],
            val_res=val_res,
            actual_device="cuda"
        )

        diag = SupportDiagnostics(
            get_slicer_version=lambda: "5.1.0",
            get_module_version=lambda: "1.0",
            get_module_root=lambda: "/module",
            get_model_root=lambda: "/model",
            is_nnunet_installed=lambda: True,
            get_torch_info_f=lambda: {"installed": True, "version": "1.8", "cuda_available": True},
            get_status_f=lambda _: status,
            get_logs_f=lambda: ["log1", "log2"],
            device_text="cuda"
        )
        
        data = diag.collect()
        
        # Test valid JSON
        json_str = diag.serialize_json(data)
        parsed = json.loads(json_str)
        assert parsed["slicer_version"] == "5.1.0"
        assert parsed["nnunet_available"] is True
        assert parsed["compute_device"]["actual"] == "cuda"
        assert parsed["model_validation"]["status"] == "VALID"
        assert parsed["logs"] == ["log1", "log2"]

        # Test markdown consistency
        md = diag.serialize_markdown(data)
        assert "5.1.0" in md
        assert "log2" in md
        assert "cuda" in md
        assert "VALID" in md

    def test_missing_subsystems_do_not_raise(self):
        val_res = ValidationResult(False, "Missing weights", False, None, ValidationStatus.MISSING)
        status = InstallationStatus(
            lines=[StatusLine(ok=False, label="Compute device", detail="Selected 'cuda' is unavailable. Falling back to 'cpu'")],
            val_res=val_res,
            actual_device="cpu"
        )

        def raise_exception(*args, **kwargs):
            raise RuntimeError("Should be caught")

        diag = SupportDiagnostics(
            get_slicer_version=raise_exception,
            get_module_version=raise_exception,
            get_module_root=raise_exception,
            get_model_root=raise_exception,
            is_nnunet_installed=raise_exception,
            get_torch_info_f=raise_exception,
            get_status_f=lambda _: status,
            get_logs_f=raise_exception,
            device_text="cuda"
        )
        
        # Should not raise
        data = diag.collect()
        assert data["slicer_version"] is None
        assert data["nnunet_available"] is False
        assert data["torch"]["installed"] is False
        assert data["compute_device"]["actual"] == "cpu"
        assert data["model_validation"]["status"] == "MISSING"
        assert data["logs"] == []

    def test_prepare_github_issue_body(self):
        diag = SupportDiagnostics()
        
        # Test short body
        short_md = "## Support Diagnostics\n\n### Logs\nline1\nline2\n"
        assert diag.prepare_github_issue_body(short_md) == short_md
        
        # Test long body with logs
        long_md = "## Support Diagnostics\n\n" + ("a" * 8000) + "\n### Logs\n" + ("b" * 1000)
        fallback = diag.prepare_github_issue_body(long_md)
        assert "<!-- Please attach the saved JSON file below -->" in fallback
        assert "<Logs truncated due to length" in fallback
        assert "b" * 1000 not in fallback
        
        # Test long body without logs (should not truncate)
        long_md_no_logs = "## Support Diagnostics\n\n" + ("a" * 8000)
        assert diag.prepare_github_issue_body(long_md_no_logs) == long_md_no_logs
