# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2024, Gauthier DOT
# Adapted by DentoFac from SlicerDentalSegmentator commit 476043f00009c372f0653dc759d69e2e559ed0f4; modified from upstream.

import sys
import types
import unittest
from pathlib import Path
import tempfile
import shutil
from unittest import mock

import pytest

# Headless, network-free tests for PythonDependencyChecker. These run under plain
# Python in CI (no Slicer application) and also under Slicer's self-test runner.
#
# When Slicer is already loaded the real `slicer`/`qt` modules are present and must NOT be
# replaced. The shared bootstrap only installs lightweight stubs when running headless, and
# each test patches `qt.QMessageBox` locally so the assertions work identically against the
# real qt. See Testing/_headless_stubs.py — order-independent across the pure suites.
from ._headless_stubs import install as _install_headless_stubs
_install_headless_stubs()

import qt
from DentoFacSegmentatorLib.PythonDependencyChecker import PythonDependencyChecker


class PythonDependencyCheckerTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.dest_folder = Path(self.temp_dir) / "Weights"
        self.config_folder = self.dest_folder / "Dataset111_453CT" / "nnUNetTrainer__nnUNetPlans__3d_fullres"
        self.config_folder.mkdir(parents=True, exist_ok=True)
        (self.config_folder / "dataset.json").write_text("{}")

        self.checker = PythonDependencyChecker(
            repoPath="dummy/repo",
            destWeightFolder=self.dest_folder,
            hasInternetConnectionF=lambda: True,
            errorDisplayF=lambda *args, **kwargs: None,
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_qmessagebox_no_declines_download(self):
        with mock.patch.object(qt.QMessageBox, "question", return_value=qt.QMessageBox.No):
            self.checker.areWeightsOutdated = lambda: True
            self.checker.downloadWeights = lambda cb: self.fail("downloadWeights should not be called")

            res = self.checker.downloadWeightsIfNeeded(lambda _: None)
            self.assertTrue(res)

    def test_download_failure_keeps_existing_weights(self):
        def failing_get_url():
            raise RuntimeError("Fake network failure")

        self.checker.getLatestReleaseUrl = failing_get_url

        res = self.checker.downloadWeights(lambda _: None)

        self.assertFalse(res)
        self.assertTrue(self.dest_folder.exists())
        self.assertTrue((self.config_folder / "dataset.json").exists())

    def test_outdated_check_ignores_release_discovery_error(self):
        # Valid local weights with recorded download info, but release discovery
        # fails (e.g. no zip asset). The update check must not propagate the error
        # and block inference; it should report the weights as up to date.
        self.checker.writeDownloadInfoURL("recorded_url")

        def failing_get_url():
            raise RuntimeError("No zip asset found")

        self.checker.getLatestReleaseUrl = failing_get_url

        self.assertFalse(self.checker.areWeightsOutdated())

    def test_outdated_check_ignores_request_timeout(self):
        import requests

        self.checker.writeDownloadInfoURL("recorded_url")
        self.checker.getLatestReleaseUrl = mock.Mock(side_effect=requests.Timeout("timed out"))

        self.assertFalse(self.checker.areWeightsOutdated())

    def test_corrupt_download_metadata_does_not_break_update_check(self):
        self.checker.getWeightDownloadInfoPath().write_text("{not valid json", encoding="utf-8")
        self.checker.getLatestReleaseUrl = lambda: "https://example.com/fake.zip"

        self.assertTrue(self.checker.areWeightsOutdated())

    def test_get_latest_release_empty_releases(self):
        class MockReleases:
            totalCount = 0

        class MockRepo:
            def get_releases(self):
                return MockReleases()

        constructor_args = []

        class MockGithub:
            def __init__(self, **kwargs):
                constructor_args.append(kwargs)

            def get_repo(self, repo_path):
                return MockRepo()

        mod = sys.modules["DentoFacSegmentatorLib.PythonDependencyChecker"]
        with mock.patch.object(mod, "Github", MockGithub):
            with self.assertRaisesRegex(RuntimeError, "No releases found"):
                self.checker.getLatestReleaseUrl()
        self.assertEqual(constructor_args, [{"timeout": mod.GITHUB_API_TIMEOUT_SECONDS}])

    def test_zip_path_traversal(self):
        zip_path = Path(self.temp_dir) / "evil.zip"

        class MockZipFile:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def namelist(self):
                return ["../evil.txt"]

            def extractall(self, path):
                pass

        mod = sys.modules["DentoFacSegmentatorLib.PythonDependencyChecker"]
        with mock.patch.object(mod.zipfile, "ZipFile", MockZipFile):
            with self.assertRaisesRegex(RuntimeError, "Unsafe path in archive: ../evil.txt"):
                self.checker.extractWeightsToWeightsFolder(zip_path, extractDir=Path(self.temp_dir))

    def test_formatMB(self):
        from DentoFacSegmentatorLib.PythonDependencyChecker import PythonDependencyChecker
        self.assertEqual(PythonDependencyChecker._formatMB(0), "0.0")
        self.assertEqual(PythonDependencyChecker._formatMB(1024 * 1024), "1.0")
        self.assertEqual(PythonDependencyChecker._formatMB(int(2.5 * 1024 * 1024)), "2.5")

    def test_trustworthyContentLength(self):
        from DentoFacSegmentatorLib.PythonDependencyChecker import PythonDependencyChecker
        self.assertEqual(PythonDependencyChecker._trustworthyContentLength({"Content-Length": "1048576"}), 1048576)
        self.assertIsNone(PythonDependencyChecker._trustworthyContentLength({}))
        self.assertIsNone(PythonDependencyChecker._trustworthyContentLength({"Content-Length": "0"}))
        self.assertIsNone(PythonDependencyChecker._trustworthyContentLength({"Content-Length": "abc"}))
        self.assertIsNone(PythonDependencyChecker._trustworthyContentLength({"Content-Length": "1048576", "Transfer-Encoding": "chunked"}))

    def test_download_progress_narration(self):
        class FakeResponse:
            def __init__(self, headers):
                self.headers = headers
            def raise_for_status(self):
                pass
            def iter_content(self, chunk_size):
                yield b"a" * (25 * 1024 * 1024)
                yield b"b" * (1 * 1024 * 1024)

        request_calls = []

        class FakeSession:
            def get(self, url, stream=True, timeout=None):
                request_calls.append((url, stream, timeout))
                return FakeResponse({"Content-Length": str(26 * 1024 * 1024)})

        import requests
        with mock.patch.object(requests, "Session", return_value=FakeSession()):
            self.checker.getLatestReleaseUrl = lambda: "https://example.com/fake.zip"

            def fake_extract(zipPath, extractDir):
                d = Path(extractDir) / "Dataset1_Test" / "nnUNetTrainer__nnUNetPlans__3d_fullres"
                d.mkdir(parents=True, exist_ok=True)
                (d / "dataset.json").touch()
            self.checker.extractWeightsToWeightsFolder = fake_extract

            logs = []
            self.checker.downloadWeights(lambda msg: logs.append(msg))

            self.assertIn("Downloading model weights...", logs)
            self.assertTrue(any("25.0 MB / 26.0 MB" in l for l in logs))
            self.assertTrue(any("26.0 MB / 26.0 MB" in l for l in logs))
            self.assertIn("Extracting model weights...", logs)
            self.assertIn("Extraction complete.", logs)
            self.assertIn("Validating downloaded weights...", logs)
            self.assertIn("Validation complete.", logs)
            self.assertTrue(any("Model weights installed at:" in l for l in logs))
            self.assertFalse(any("%" in l for l in logs))
            self.assertEqual(
                request_calls,
                [("https://example.com/fake.zip", True, (10, 60))],
            )

    def test_download_progress_narration_no_content_length(self):
        class FakeResponse:
            def __init__(self, headers):
                self.headers = headers
            def raise_for_status(self):
                pass
            def iter_content(self, chunk_size):
                yield b"a" * (25 * 1024 * 1024)

        class FakeSession:
            def get(self, url, stream=True, timeout=None):
                return FakeResponse({"Transfer-Encoding": "chunked", "Content-Length": "123"})

        import requests
        with mock.patch.object(requests, "Session", return_value=FakeSession()):
            self.checker.getLatestReleaseUrl = lambda: "https://example.com/fake.zip"
            def fake_extract(zipPath, extractDir):
                d = Path(extractDir) / "Dataset1_Test" / "nnUNetTrainer__nnUNetPlans__3d_fullres"
                d.mkdir(parents=True, exist_ok=True)
                (d / "dataset.json").touch()
            self.checker.extractWeightsToWeightsFolder = fake_extract

            logs = []
            self.checker.downloadWeights(lambda msg: logs.append(msg))

            self.assertTrue(any("Downloading model weights: 25.0 MB" == l for l in logs))
            self.assertFalse(any("/" in l and "MB" in l for l in logs))
            self.assertFalse(any("%" in l for l in logs))

    def test_download_rejects_flattened_extracted_archive(self):
        class FakeResponse:
            def __init__(self, headers):
                self.headers = headers
            def raise_for_status(self):
                pass
            def iter_content(self, chunk_size):
                yield b"a" * 1024

        class FakeSession:
            def get(self, url, stream=True, timeout=None):
                return FakeResponse({"Content-Length": "1024"})

        import requests
        with mock.patch.object(requests, "Session", return_value=FakeSession()):
            self.checker.getLatestReleaseUrl = lambda: "https://example.com/fake.zip"

            def fake_extract(zipPath, extractDir):
                (Path(extractDir) / "dataset.json").touch()
            self.checker.extractWeightsToWeightsFolder = fake_extract

            logs = []
            self.checker.errorDisplay = lambda *args, **kwargs: logs.extend(list(args) + [str(v) for v in kwargs.values()])
            result = self.checker.downloadWeights(lambda msg: logs.append(msg))

            self.assertFalse(result)
            self.assertTrue((self.config_folder / "dataset.json").exists())
            self.assertTrue(any("Downloaded archive did not contain dataset.json" in l for l in logs))

    def test_mid_swap_failure_rolls_back(self):
        class FakeResponse:
            def __init__(self, headers):
                self.headers = headers
            def raise_for_status(self):
                pass
            def iter_content(self, chunk_size):
                yield b"a" * 1024

        class FakeSession:
            def get(self, url, stream=True, timeout=None):
                return FakeResponse({"Content-Length": "1024"})

        import requests
        with mock.patch.object(requests, "Session", return_value=FakeSession()):
            self.checker.getLatestReleaseUrl = lambda: "https://example.com/fake.zip"

            def fake_extract(zipPath, extractDir):
                d = Path(extractDir) / "Dataset1_Test" / "nnUNetTrainer__nnUNetPlans__3d_fullres"
                d.mkdir(parents=True, exist_ok=True)
                (d / "dataset.json").touch()
            self.checker.extractWeightsToWeightsFolder = fake_extract

            (self.config_folder / "dataset.json").write_text('{"marker": "original"}')

            import os
            real_replace = os.replace

            # Fail only the forward swap (new weights -> live destination), letting the
            # "move current aside to backup" and "roll backup back" replaces through. We
            # discriminate on the backup naming convention (`.bak_`) rather than the
            # staging dir's literal name so the injection survives a rename of the
            # staging tree: the forward swap's src is the validated staging content (no
            # `.bak_`), while the rollback's src is the `.bak_*` backup.
            injected = []

            def flaky_replace(src, dst, *a, **k):
                if Path(dst) == self.dest_folder and ".bak_" not in Path(src).name:
                    injected.append((src, dst))
                    raise OSError("simulated mid-swap failure")
                return real_replace(src, dst, *a, **k)

            error_calls = []
            self.checker.errorDisplay = lambda *args, **kwargs: error_calls.append(args)

            with mock.patch("os.replace", side_effect=flaky_replace):
                result = self.checker.downloadWeights(lambda msg: None)

            # Guard against a false-green if the predicate ever stops matching the swap:
            # the failure must actually have been injected for this test to mean anything.
            self.assertEqual(len(injected), 1)
            self.assertFalse(result)
            self.assertTrue(self.dest_folder.exists())

            import json
            content = json.loads((self.config_folder / "dataset.json").read_text())
            self.assertEqual(content.get("marker"), "original")

            backups = list(self.dest_folder.parent.glob(f"{self.dest_folder.name}.bak_*"))
            self.assertEqual(len(backups), 0)

            staging = list(self.dest_folder.parent.glob("dentalseg_weights_*"))
            self.assertEqual(len(staging), 0)

            self.assertEqual(len(error_calls), 1)

    def test_failed_rollback_preserves_existing_weights_backup(self):
        class FakeResponse:
            headers = {"Content-Length": "1024"}

            def raise_for_status(self):
                pass

            def iter_content(self, chunk_size):
                yield b"a" * 1024

        class FakeSession:
            def get(self, url, stream=True, timeout=None):
                return FakeResponse()

        import requests
        with mock.patch.object(requests, "Session", return_value=FakeSession()):
            self.checker.getLatestReleaseUrl = lambda: "https://example.com/fake.zip"

            def fake_extract(zipPath, extractDir):
                d = Path(extractDir) / "Dataset1_Test" / "nnUNetTrainer__nnUNetPlans__3d_fullres"
                d.mkdir(parents=True, exist_ok=True)
                (d / "dataset.json").touch()
            self.checker.extractWeightsToWeightsFolder = fake_extract

            (self.config_folder / "dataset.json").write_text('{"marker": "original"}')

            import os
            real_replace = os.replace

            def fail_forward_and_rollback(src, dst, *args, **kwargs):
                if Path(dst) == self.dest_folder:
                    raise OSError("simulated Windows sharing violation")
                return real_replace(src, dst, *args, **kwargs)

            error_calls = []
            self.checker.errorDisplay = lambda *args, **kwargs: error_calls.append((args, kwargs))

            with mock.patch("os.replace", side_effect=fail_forward_and_rollback):
                result = self.checker.downloadWeights(lambda msg: None)

        self.assertFalse(result)
        self.assertFalse(self.dest_folder.exists())
        backups = list(self.dest_folder.parent.glob(f"{self.dest_folder.name}.bak_*"))
        self.assertEqual(len(backups), 1)
        restored_dataset = backups[0] / "Dataset111_453CT" / "nnUNetTrainer__nnUNetPlans__3d_fullres" / "dataset.json"
        self.assertIn("original", restored_dataset.read_text())
        self.assertEqual(len(error_calls), 1)
        self.assertIn("backup has been preserved", error_calls[0][1]["detailedText"])

    def test_metadata_write_failure_is_non_fatal(self):
        class FakeResponse:
            def __init__(self, headers):
                self.headers = headers
            def raise_for_status(self):
                pass
            def iter_content(self, chunk_size):
                yield b"a" * 1024

        class FakeSession:
            def get(self, url, stream=True, timeout=None):
                return FakeResponse({"Content-Length": "1024"})

        import requests
        with mock.patch.object(requests, "Session", return_value=FakeSession()):
            self.checker.getLatestReleaseUrl = lambda: "https://example.com/fake.zip"

            def fake_extract(zipPath, extractDir):
                d = Path(extractDir) / "Dataset1_Test" / "nnUNetTrainer__nnUNetPlans__3d_fullres"
                d.mkdir(parents=True, exist_ok=True)
                (d / "dataset.json").touch()
            self.checker.extractWeightsToWeightsFolder = fake_extract

            def failing_write(url):
                raise OSError("disk full")
            self.checker.writeDownloadInfoURL = failing_write

            error_calls = []
            self.checker.errorDisplay = lambda *args, **kwargs: error_calls.append(args)

            logs = []
            result = self.checker.downloadWeights(lambda msg: logs.append(msg))

            self.assertTrue(result)

            from DentoFacSegmentatorLib.ModelPath import findConfigurationFolder
            found = findConfigurationFolder(self.dest_folder)
            self.assertIsNotNone(found)
            self.assertTrue((self.dest_folder / "Dataset1_Test" / "nnUNetTrainer__nnUNetPlans__3d_fullres" / "dataset.json").exists())

            self.assertTrue(any("failed to record version info" in l for l in logs))
            self.assertEqual(len(error_calls), 0)

            staging = list(self.dest_folder.parent.glob("dentalseg_weights_*"))
            self.assertEqual(len(staging), 0)

    @pytest.mark.baseline_slicer_runtime_quarantine
    def test_model_path_valid_nested_layout(self):
        from DentoFacSegmentatorLib.ModelPath import findConfigurationFolder, validate, ValidationStatus
        
        # Build confirmed tree
        temp_dir = Path(self.temp_dir)
        root = temp_dir / "ValidNested"
        config_folder = root / "Dataset111_453CT" / "nnUNetTrainer__nnUNetPlans__3d_fullres"
        config_folder.mkdir(parents=True, exist_ok=True)
        (config_folder / "dataset.json").touch()
        (config_folder / "plans.json").touch()
        fold_0 = config_folder / "fold_0"
        fold_0.mkdir(parents=True, exist_ok=True)
        (fold_0 / "checkpoint_final.pth").touch()
        
        found = findConfigurationFolder(root)
        self.assertEqual(found, config_folder)
        
        res = validate(root)
        self.assertTrue(res.isValid)
        self.assertFalse(res.authoritative)
        self.assertEqual(res.status, ValidationStatus.VALID)
        self.assertEqual(res.configurationFolder, config_folder)

    @pytest.mark.baseline_slicer_runtime_quarantine
    def test_model_path_flattened_layout_detected(self):
        from DentoFacSegmentatorLib.ModelPath import validate, ValidationStatus
        
        root = Path(self.temp_dir) / "Flattened"
        root.mkdir()
        
        # Valid weight files at root but no config folder
        (root / "dataset.json").touch()
        (root / "plans.json").touch()
        (root / "checkpoint_final.pth").touch()
        
        res = validate(root=root)
        self.assertFalse(res.isValid)
        self.assertFalse(res.authoritative)
        self.assertEqual(res.status, ValidationStatus.FLATTENED)

    def test_detectFlattenedLayout(self):
        from DentoFacSegmentatorLib.ModelPath import detectFlattenedLayout
        
        root = Path(self.temp_dir) / "Detect"
        root.mkdir()
        
        # Empty
        self.assertFalse(detectFlattenedLayout(root))
        
        # Single nested config folder (valid layout)
        configFolder = root / "Dataset1_Foo" / "nnUNetTrainer__nnUNetPlans__3d_fullres"
        configFolder.mkdir(parents=True)
        (configFolder / "dataset.json").touch()
        (configFolder / "plans.json").touch()
        (configFolder / "fold_0").mkdir()
        (configFolder / "fold_0" / "checkpoint_final.pth").touch()
        self.assertFalse(detectFlattenedLayout(root))
        
        shutil.rmtree(configFolder.parent)
        
        # Flat files
        (root / "dataset.json").touch()
        self.assertTrue(detectFlattenedLayout(root))

    @pytest.mark.baseline_slicer_runtime_quarantine
    def test_model_path_missing_weights(self):
        from DentoFacSegmentatorLib.ModelPath import findConfigurationFolder, validate, ValidationStatus
        
        temp_dir = Path(self.temp_dir)
        root = temp_dir / "Empty"
        root.mkdir(parents=True, exist_ok=True)
        
        found = findConfigurationFolder(root)
        self.assertIsNone(found)
        
        res = validate(root)
        self.assertFalse(res.isValid)
        self.assertFalse(res.authoritative)
        self.assertEqual(res.status, ValidationStatus.MISSING)


class WeightsDiagnosticTestCase(unittest.TestCase):
    def test_weightsDiagnostic(self):
        from DentoFacSegmentatorLib.InstallationStatus import weightsDiagnostic
        from DentoFacSegmentatorLib.ModelPath import ValidationResult, ValidationStatus, EXPECTED_LAYOUT_DESCRIPTION
        
        root = Path("/fake/root")
        
        # INVALID
        res_invalid = ValidationResult(False, "Some reason", True, Path("/fake/config"), ValidationStatus.INVALID)
        short, long_guidance = weightsDiagnostic(res_invalid, root)
        self.assertEqual(short, "Installed but invalid")
        self.assertIn("/fake/config", long_guidance)
        self.assertIn(EXPECTED_LAYOUT_DESCRIPTION, long_guidance)
        self.assertIn("Click *Re-download weights*", long_guidance)
        self.assertIn("Some reason", long_guidance)
        
        # FLATTENED
        res_flat = ValidationResult(False, "", True, None, ValidationStatus.FLATTENED)
        short, long_guidance = weightsDiagnostic(res_flat, root)
        self.assertEqual(short, "Legacy/flattened layout detected")
        self.assertIn("/fake/root", long_guidance)
        self.assertIn(EXPECTED_LAYOUT_DESCRIPTION, long_guidance)
        self.assertIn("Click *Re-download weights*", long_guidance)


class ValidateParameterReuseTestCase(unittest.TestCase):
    """Covers ModelPath.validate(parameter=...) — the reuse path added so the device
    check and weight validation share a single Parameter instead of constructing two.
    The prior InstallationStatus tests mock validate() wholesale, so this exercises the
    real authoritative branch with a fake Parameter."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        # Make `import SlicerNNUNetLib` succeed so validate() takes the authoritative
        # branch. Its Parameter must never be constructed when one is supplied.
        self.mock_module = types.ModuleType("SlicerNNUNetLib")

        def _fail_construct(*args, **kwargs):
            raise AssertionError(
                "validate() constructed a new Parameter instead of reusing the supplied one"
            )

        self.mock_module.Parameter = _fail_construct
        sys.modules["SlicerNNUNetLib"] = self.mock_module

    def tearDown(self):
        sys.modules.pop("SlicerNNUNetLib", None)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_supplied_parameter_is_reused_when_valid(self):
        from DentoFacSegmentatorLib.ModelPath import validate, ValidationStatus

        class FakeParameter:
            _configurationFolder = Path("/fake/config/folder")

            def isValid(self):
                return True, ""

        res = validate(root=Path(self.temp_dir), parameter=FakeParameter())
        self.assertTrue(res.isValid)
        self.assertTrue(res.authoritative)
        self.assertEqual(res.status, ValidationStatus.VALID)
        self.assertEqual(res.configurationFolder, Path("/fake/config/folder"))

    def test_supplied_invalid_parameter_reason_propagated(self):
        from DentoFacSegmentatorLib.ModelPath import validate, ValidationStatus

        class FakeParameter:
            def isValid(self):
                return False, "weights missing"

        # Empty temp root -> no config folder on disk -> MISSING (deterministic).
        res = validate(root=Path(self.temp_dir), parameter=FakeParameter())
        self.assertFalse(res.isValid)
        self.assertTrue(res.authoritative)
        self.assertEqual(res.reason, "weights missing")
        self.assertEqual(res.status, ValidationStatus.MISSING)

    def test_forced_download(self):
        from DentoFacSegmentatorLib.PythonDependencyChecker import PythonDependencyChecker
        
        checker = PythonDependencyChecker(
            destWeightFolder=Path(self.temp_dir),
            hasInternetConnectionF=lambda: True,
        )
        checker.areWeightsMissing = lambda: False
        checker.areWeightsOutdated = lambda: False
        
        download_called = False
        def fake_download(*args, **kwargs):
            nonlocal download_called
            download_called = True
            return True
            
        checker.downloadWeights = fake_download
        
        # Force = False should not call downloadWeights since missing/outdated are False
        checker.downloadWeightsIfNeeded(lambda msg: None, force=False)
        self.assertFalse(download_called)
        
        # Force = True should call downloadWeights unconditionally
        checker.downloadWeightsIfNeeded(lambda msg: None, force=True)
        self.assertTrue(download_called)


class InstallationStatusTestCase(unittest.TestCase):
    def setUp(self):
        class MockParameter:
            def __init__(self, folds, modelPath, device):
                self.device = device
            def isSelectedDeviceAvailable(self):
                return True
            def _getDevice(self):
                return self.device

        self.mock_slicer_nnunet = types.ModuleType("SlicerNNUNetLib")
        self.mock_slicer_nnunet.Parameter = MockParameter
        sys.modules["SlicerNNUNetLib"] = self.mock_slicer_nnunet

        from DentoFacSegmentatorLib.PythonDependencyChecker import PythonDependencyChecker
        self.patcher_outdated = mock.patch.object(PythonDependencyChecker, "areWeightsOutdated", return_value=False)
        self.patcher_outdated.start()

    def tearDown(self):
        if "SlicerNNUNetLib" in sys.modules:
            del sys.modules["SlicerNNUNetLib"]
        self.patcher_outdated.stop()

    @mock.patch("DentoFacSegmentatorLib.SegmentationWidget.SegmentationWidget.isNNUNetModuleInstalled", return_value=True)
    @mock.patch("DentoFacSegmentatorLib.PythonDependencyChecker.PythonDependencyChecker.areDependenciesSatisfied", return_value=True)
    @mock.patch("DentoFacSegmentatorLib.InstallationStatus.validate")
    def test_all_good(self, mock_validate, mock_deps, mock_nnunet):
        from DentoFacSegmentatorLib.ModelPath import ValidationResult, ValidationStatus
        from DentoFacSegmentatorLib.InstallationStatus import collect_status
        mock_validate.return_value = ValidationResult(isValid=True, reason="", authoritative=True, configurationFolder=None, status=ValidationStatus.VALID)

        status = collect_status("cuda")
        self.assertTrue(status.is_ready)
        weights_line = next(l for l in status.lines if l.label == "Model weights")
        self.assertTrue(weights_line.ok)
        self.assertIn("Valid", weights_line.detail)

    @mock.patch("DentoFacSegmentatorLib.SegmentationWidget.SegmentationWidget.isNNUNetModuleInstalled", return_value=True)
    @mock.patch("DentoFacSegmentatorLib.PythonDependencyChecker.PythonDependencyChecker.areDependenciesSatisfied", return_value=True)
    @mock.patch("DentoFacSegmentatorLib.InstallationStatus.validate")
    def test_weights_missing(self, mock_validate, mock_deps, mock_nnunet):
        from DentoFacSegmentatorLib.ModelPath import ValidationResult, ValidationStatus
        from DentoFacSegmentatorLib.InstallationStatus import collect_status
        mock_validate.return_value = ValidationResult(isValid=False, reason="", authoritative=True, configurationFolder=None, status=ValidationStatus.MISSING)

        status = collect_status("cuda")
        self.assertFalse(status.is_ready)
        weights_line = next(l for l in status.lines if l.label == "Model weights")
        self.assertFalse(weights_line.ok)
        self.assertIn("Not installed", weights_line.detail)

    @mock.patch("DentoFacSegmentatorLib.SegmentationWidget.SegmentationWidget.isNNUNetModuleInstalled", return_value=True)
    @mock.patch("DentoFacSegmentatorLib.PythonDependencyChecker.PythonDependencyChecker.areDependenciesSatisfied", return_value=True)
    @mock.patch("DentoFacSegmentatorLib.InstallationStatus.validate")
    def test_weights_invalid(self, mock_validate, mock_deps, mock_nnunet):
        from DentoFacSegmentatorLib.ModelPath import ValidationResult, ValidationStatus
        from DentoFacSegmentatorLib.InstallationStatus import collect_status
        mock_validate.return_value = ValidationResult(isValid=False, reason="broken tree", authoritative=True, configurationFolder=None, status=ValidationStatus.INVALID)

        status = collect_status("cuda")
        self.assertFalse(status.is_ready)
        weights_line = next(l for l in status.lines if l.label == "Model weights")
        self.assertFalse(weights_line.ok)
        self.assertIn("Installed but invalid", weights_line.detail)

    @mock.patch("DentoFacSegmentatorLib.SegmentationWidget.SegmentationWidget.isNNUNetModuleInstalled", return_value=False)
    @mock.patch("DentoFacSegmentatorLib.PythonDependencyChecker.PythonDependencyChecker.areDependenciesSatisfied", return_value=True)
    @mock.patch("DentoFacSegmentatorLib.InstallationStatus.validate")
    def test_non_authoritative(self, mock_validate, mock_deps, mock_nnunet):
        if "SlicerNNUNetLib" in sys.modules:
            del sys.modules["SlicerNNUNetLib"]
        from DentoFacSegmentatorLib.ModelPath import ValidationResult, ValidationStatus
        from DentoFacSegmentatorLib.InstallationStatus import collect_status
        
        mock_validate.return_value = ValidationResult(isValid=True, reason="", authoritative=False, configurationFolder=None, status=ValidationStatus.VALID)

        status = collect_status("cuda")
        self.assertFalse(status.is_ready)
        weights_line = next(l for l in status.lines if l.label == "Model weights")
        self.assertFalse(weights_line.ok)
        self.assertIn("Cannot verify", weights_line.detail)

    @mock.patch("DentoFacSegmentatorLib.SegmentationWidget.SegmentationWidget.isNNUNetModuleInstalled", return_value=True)
    @mock.patch("DentoFacSegmentatorLib.PythonDependencyChecker.PythonDependencyChecker.areDependenciesSatisfied", return_value=False)
    @mock.patch("DentoFacSegmentatorLib.InstallationStatus.validate")
    def test_deps_missing(self, mock_validate, mock_deps, mock_nnunet):
        from DentoFacSegmentatorLib.ModelPath import ValidationResult, ValidationStatus
        from DentoFacSegmentatorLib.InstallationStatus import collect_status
        mock_validate.return_value = ValidationResult(isValid=True, reason="", authoritative=True, configurationFolder=None, status=ValidationStatus.VALID)

        status = collect_status("cuda")
        self.assertFalse(status.is_ready)
        deps_line = next(l for l in status.lines if "Python dependencies" in l.label)
        self.assertFalse(deps_line.ok)

    @mock.patch("DentoFacSegmentatorLib.SegmentationWidget.SegmentationWidget.isNNUNetModuleInstalled", return_value=True)
    @mock.patch("DentoFacSegmentatorLib.PythonDependencyChecker.PythonDependencyChecker.areDependenciesSatisfied", return_value=False)
    @mock.patch("DentoFacSegmentatorLib.InstallationStatus.validate")
    def test_device_line_when_deps_missing_does_not_claim_extension_missing(self, mock_validate, mock_deps, mock_nnunet):
        # Regression: extension present but torch missing. The device probe imports
        # torch, so it must NOT be caught and reported as "NNUNet not installed" — that
        # contradicts the extension line and points users at the wrong fix.
        from DentoFacSegmentatorLib.ModelPath import ValidationResult, ValidationStatus
        from DentoFacSegmentatorLib.InstallationStatus import collect_status
        mock_validate.return_value = ValidationResult(isValid=True, reason="", authoritative=True, configurationFolder=None, status=ValidationStatus.VALID)

        # Even if the device probe would raise ImportError (torch missing), we must not
        # reach it while deps are unsatisfied.
        def _raise(self):
            raise ImportError("No module named 'torch'")
        self.mock_slicer_nnunet.Parameter.isSelectedDeviceAvailable = _raise

        status = collect_status("cuda")
        nnunet_line = next(l for l in status.lines if l.label == "NNUNet extension")
        device_line = next(l for l in status.lines if l.label == "Compute device")
        self.assertTrue(nnunet_line.ok)
        self.assertFalse(device_line.ok)
        self.assertNotIn("NNUNet", device_line.detail)
        self.assertIn("dependencies", device_line.detail.lower())
