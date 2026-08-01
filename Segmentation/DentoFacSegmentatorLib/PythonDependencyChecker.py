# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2024, Gauthier DOT
# Adapted by DentoFac from SlicerDentalSegmentator commit 476043f00009c372f0653dc759d69e2e559ed0f4; modified from upstream.

import json
import zipfile
from pathlib import Path
from typing import Optional, Callable

import requests
import qt
import slicer
from github import Github, GithubException


GITHUB_API_TIMEOUT_SECONDS = 15
WEIGHTS_DOWNLOAD_TIMEOUT_SECONDS = (10, 60)
UPSTREAM_MODEL_REPOSITORY = "gaudot/SlicerDentalSegmentator"
UPSTREAM_MODEL_URL = "https://github.com/gaudot/SlicerDentalSegmentator"
DENTOFAC_SUPPORT_URL = "https://github.com/DentoFac/SlicerDentoFac"
WEIGHTS_STAGING_PREFIX = "dentofac-segmentator-weights_"


def hasInternetConnection(timeOut_sec=2) -> bool:
    """
    Check if user has access to the internet.
    """
    try:
        requests.get("https://api.github.com", timeout=timeOut_sec)
        return True
    except requests.RequestException:
        return False


class PythonDependencyChecker:
    """
    Class responsible for installing the Modules dependencies and downloading the model weights.
    """

    def __init__(
            self,
            repoPath: Optional[str] = None,
            destWeightFolder: Optional[Path] = None,
            hasInternetConnectionF: Optional[Callable[[], bool]] = None,
            errorDisplayF=None
    ):
        """
        :param repoPath: Optional path to the github repository from which the weights will be downloaded from.
        :param destWeightFolder: Optional path to where the weights will be saved.
        :param hasInternetConnectionF: Optional function returning True when internet connection is available, False
            otherwise.
        :param errorDisplayF: Optional function used to display error information.
        """
        from .ModelPath import modelRoot
        self.dependencyChecked = False
        self.destWeightFolder = Path(destWeightFolder or modelRoot())
        # Model downloads retain the pinned upstream release as explicit provenance.
        self.repo_path = repoPath or UPSTREAM_MODEL_REPOSITORY
        self.hasInternetConnectionF = hasInternetConnectionF or hasInternetConnection
        self.errorDisplay = errorDisplayF or slicer.util.errorDisplay

    @classmethod
    def areDependenciesSatisfied(cls):
        try:
            import torch
            import nnunetv2
            return True
        except ImportError:
            return False

    def downloadWeightsIfNeeded(self, progressCallback, force=False):
        if force:
            return self.downloadWeights(progressCallback)

        if self.areWeightsMissing():
            return self.downloadWeights(progressCallback)

        elif self.areWeightsOutdated():
            if qt.QMessageBox.question(
                    None,
                    "New weights are available",
                    "New weights are available. Would you like to download them?"
            ) == qt.QMessageBox.Yes:
                return self.downloadWeights(progressCallback)
        return True

    def areWeightsMissing(self):
        return self.getDatasetPath() is None

    def getLatestReleaseUrl(self):
        g = Github(timeout=GITHUB_API_TIMEOUT_SECONDS)
        repo = g.get_repo(self.repo_path)
        releases = repo.get_releases()
        if releases.totalCount == 0:
            raise RuntimeError(f"No releases found for repository {self.repo_path}")
        
        latest_release = releases[0]
        for asset in latest_release.get_assets():
            if asset.name.endswith(".zip"):
                return asset.browser_download_url
        
        raise RuntimeError(f"No zip asset found in the latest release of {self.repo_path}")

    def areWeightsOutdated(self) -> bool:
        """
        :returns: True if weights information are missing or internet connection is available and weights information
            don't match the ones on the GitHub page. False otherwise.
        """
        if not self.getWeightDownloadInfoPath().exists():
            return self.areWeightsMissing()

        if not self.hasInternetConnectionF():
            return False

        try:
            return self.getLastDownloadedWeights() != self.getLatestReleaseUrl()
        except (GithubException, RuntimeError, requests.RequestException):
            # The update check is best-effort. If the latest release cannot be
            # resolved (no releases, no zip asset, API/network error), keep using
            # the existing local weights rather than blocking inference.
            return False

    def getDestWeightFolder(self):
        return self.destWeightFolder

    def getDatasetPath(self):
        return self.getDatasetPathIn(self.destWeightFolder)

    @classmethod
    def getDatasetPathIn(cls, folderPath: Path):
        from .ModelPath import findConfigurationFolder
        config_folder = findConfigurationFolder(folderPath)
        return config_folder / "dataset.json" if config_folder else None

    @staticmethod
    def _isNNUNetDatasetPathValid(datasetPath: Path):
        from .ModelPath import _isNNUNetDatasetPathValid
        return _isNNUNetDatasetPathValid(datasetPath)

    @staticmethod
    def _formatMB(numBytes: int) -> str:
        return f"{numBytes / (1024 * 1024):.1f}"

    @staticmethod
    def _trustworthyContentLength(response) -> Optional[int]:
        headers = response if isinstance(response, dict) else getattr(response, 'headers', {})
        if "chunked" in headers.get("Transfer-Encoding", "").lower():
            return None
        content_length = headers.get("Content-Length")
        if content_length is None:
            return None
        try:
            length = int(content_length)
            return length if length > 0 else None
        except (ValueError, TypeError):
            return None

    def getWeightDownloadInfoPath(self):
        return self.destWeightFolder / "download_info.json"

    def getLastDownloadedWeights(self):
        infoPath = self.getWeightDownloadInfoPath()
        if not infoPath.exists():
            return None

        try:
            info = json.loads(infoPath.read_text(encoding="utf-8"))
            return info.get("download_url") if isinstance(info, dict) else None
        except (OSError, json.JSONDecodeError):
            return None

    def _extractedTreeHasDataset(self, extractDir: Path) -> bool:
        return self.getDatasetPathIn(extractDir) is not None

    def downloadWeights(self, progressCallback) -> bool:
        """
        Removes the weight folder and tries to download the weights from the GitHub page.
        If an internet connection is not available, keeps the current weights unchanged.

        :returns: True if download was successful. False in case of no internet or failure during download.
        """
        import shutil
        import tempfile
        import traceback
        import os

        progressCallback("Downloading model weights...")
        if not self.hasInternetConnectionF():
            self.errorDisplay(
                "Failed to download weights (no internet connection). "
                "Please retry or manually install them to proceed.\n"
                "To manually install the weights, please refer to the documentation here :\n"
                f"{DENTOFAC_SUPPORT_URL}\n\n"
                f"Model source and provenance: {UPSTREAM_MODEL_URL}",
            )
            return False

        # Stage the download/extraction on the SAME filesystem as the destination
        # (a sibling of destWeightFolder) so the final swap is an atomic rename
        # rather than a cross-filesystem copy. The existing weights are moved aside
        # to a backup and deleted only once the swap succeeds, so every failure
        # path can roll back to the previous working weights.
        self.destWeightFolder.parent.mkdir(parents=True, exist_ok=True)
        tmpParent = tempfile.mkdtemp(
            dir=str(self.destWeightFolder.parent), prefix=WEIGHTS_STAGING_PREFIX
        )
        backupFolder = None
        weightsCommitted = False
        try:
            download_url = self.getLatestReleaseUrl()
            session = requests.Session()
            response = session.get(
                download_url,
                stream=True,
                timeout=WEIGHTS_DOWNLOAD_TIMEOUT_SECONDS,
            )
            response.raise_for_status()

            file_name = download_url.split("/")[-1]
            destZipPath = Path(tmpParent) / file_name

            import time
            total_bytes = self._trustworthyContentLength(response)
            downloadedBytes = 0
            last_report_time = 0.0
            last_report_bytes = 0

            with open(destZipPath, "wb") as f:
                for chunk in response.iter_content(1024 * 1024):
                    f.write(chunk)
                    downloadedBytes += len(chunk)
                    current_time = time.monotonic()
                    if (current_time - last_report_time >= 2.0) or (downloadedBytes - last_report_bytes >= 25 * 1024 * 1024):
                        dl_mb = self._formatMB(downloadedBytes)
                        if total_bytes is not None:
                            tot_mb = self._formatMB(total_bytes)
                            progressCallback(f"Downloading model weights: {dl_mb} MB / {tot_mb} MB")
                        else:
                            progressCallback(f"Downloading model weights: {dl_mb} MB")
                        last_report_time = current_time
                        last_report_bytes = downloadedBytes

            dl_mb = self._formatMB(downloadedBytes)
            if total_bytes is not None:
                tot_mb = self._formatMB(total_bytes)
                progressCallback(f"Downloading model weights: {dl_mb} MB / {tot_mb} MB")
            else:
                progressCallback(f"Downloading model weights: {dl_mb} MB")

            extractDir = Path(tmpParent) / "extracted"
            extractDir.mkdir()

            progressCallback("Extracting model weights...")
            self.extractWeightsToWeightsFolder(destZipPath, extractDir=extractDir)
            progressCallback("Extraction complete.")

            progressCallback("Validating downloaded weights...")
            if not self._extractedTreeHasDataset(extractDir):
                raise RuntimeError("Downloaded archive did not contain dataset.json")
            progressCallback("Validation complete.")

            validated_content_root = extractDir

            # Move existing weights aside, rename the validated content into place,
            # then drop the backup only after the swap succeeds. Roll back on failure.
            if self.destWeightFolder.exists():
                backupFolder = self.destWeightFolder.parent / f"{self.destWeightFolder.name}.bak_{Path(tmpParent).name}"
                os.replace(self.destWeightFolder, backupFolder)

            try:
                os.replace(validated_content_root, self.destWeightFolder)
            except Exception:
                if backupFolder is not None and not self.destWeightFolder.exists():
                    try:
                        os.replace(backupFolder, self.destWeightFolder)
                        backupFolder = None
                    except Exception as rollbackError:
                        raise RuntimeError(
                            "Failed to restore the previous model weights. "
                            f"The backup has been preserved at: {backupFolder}"
                        ) from rollbackError
                raise

            weightsCommitted = True

            # The weights are committed once the swap above succeeds. Recording the
            # version metadata is best-effort: a failure here only affects future
            # "is outdated?" checks and must not fail an otherwise successful update
            # (which would abort inference and, via the rollback, discard valid weights).
            try:
                self.writeDownloadInfoURL(download_url)
            except Exception:  # noqa
                progressCallback("Warning: weights installed but failed to record version info.")

            from .ModelPath import findConfigurationFolder, inferenceModelPath
            config_folder = findConfigurationFolder(self.destWeightFolder)
            installed_path = config_folder if config_folder else inferenceModelPath(self.destWeightFolder)
            progressCallback(f"Model weights installed at: {installed_path}")

            return True
        except Exception:  # noqa
            self.errorDisplay(
                "Failed to download weights. Please retry or manually install them to proceed.\n"
                "To manually install the weights, please refer to the documentation here :\n"
                f"{DENTOFAC_SUPPORT_URL}\n\n"
                f"Model source and provenance: {UPSTREAM_MODEL_URL}",
                detailedText=traceback.format_exc()
            )
            return False
        finally:
            if weightsCommitted and backupFolder is not None:
                shutil.rmtree(backupFolder, ignore_errors=True)
            shutil.rmtree(tmpParent, ignore_errors=True)

    def extractWeightsToWeightsFolder(self, zipPath, extractDir=None):
        extractDir = Path(extractDir or self.destWeightFolder).resolve()
        with zipfile.ZipFile(zipPath, "r") as f:
            for member in f.namelist():
                target = (extractDir / member).resolve()
                if target != extractDir and extractDir not in target.parents:
                    raise RuntimeError(f"Unsafe path in archive: {member}")
            f.extractall(extractDir)

    def writeDownloadInfoURL(self, download_url):
        infoPath = self.getWeightDownloadInfoPath()
        temporaryPath = infoPath.with_name(f"{infoPath.name}.tmp")
        temporaryPath.write_text(
            json.dumps({"download_url": download_url}),
            encoding="utf-8",
        )
        import os
        os.replace(temporaryPath, infoPath)
