# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2024, Gauthier DOT
# Adapted by DentoFac from SlicerDentalSegmentator commit 476043f00009c372f0653dc759d69e2e559ed0f4; modified from upstream.

from enum import Flag, auto
import os
import slicer
import qt

from .PythonDependencyChecker import hasInternetConnection


class ExportFormat(Flag):
    OBJ = auto()
    STL = auto()
    NIFTI = auto()
    GLTF = auto()


class ExportManager:
    def __init__(self, hasInternetConnectionF=None):
        # Allow injection so glTF auto-install can be exercised/short-circuited in tests,
        # mirroring PythonDependencyChecker.hasInternetConnectionF.
        self.hasInternetConnectionF = hasInternetConnectionF or hasInternetConnection

    def exportSegmentation(self, segmentationNode, folderPath, selectedFormats,
                           gltfReductionFactor=0.0):
        before = self._snapshotFolder(folderPath)
        for closedSurfaceExport in [ExportFormat.STL, ExportFormat.OBJ]:
            if selectedFormats & closedSurfaceExport:
                slicer.vtkSlicerSegmentationsModuleLogic.ExportSegmentsClosedSurfaceRepresentationToFiles(
                    folderPath,
                    segmentationNode,
                    None,
                    closedSurfaceExport.name,
                    True,
                    1.0,
                    False
                )

        if selectedFormats & ExportFormat.NIFTI:
            slicer.vtkSlicerSegmentationsModuleLogic.ExportSegmentsBinaryLabelmapRepresentationToFiles(
                folderPath,
                segmentationNode,
                None,
                "nii.gz"
            )

        if selectedFormats & ExportFormat.GLTF:
            self._exportToGLTF(segmentationNode, folderPath, gltfReductionFactor)

        after = self._snapshotFolder(folderPath)
        written = sorted(name for name, sig in after.items() if before.get(name) != sig)
        return written

    @staticmethod
    def _snapshotFolder(folderPath):
        # name -> (mtime_ns, size); tolerant if the folder doesn't exist yet.
        result = {}
        try:
            for name in os.listdir(folderPath):
                full = os.path.join(folderPath, name)
                try:
                    st = os.stat(full)
                except OSError:
                    continue
                result[name] = (st.st_mtime_ns, st.st_size)
        except OSError:
            pass
        return result

    @staticmethod
    def isOpenAnatomyAvailable():
        """True if glTF export can run without installing anything: either the
        OpenAnatomyExport module is importable now, or the SlicerOpenAnatomy
        extension is already installed."""
        try:
            import OpenAnatomyExport  # noqa: F401
            return True
        except ImportError:
            pass
        try:
            mgr = slicer.app.extensionsManagerModel()
            return bool(mgr and mgr.isExtensionInstalled("SlicerOpenAnatomy"))
        except Exception:
            return False

    def _exportToGLTF(self, segmentationNode, folderPath, gltfReductionFactor,
                      tryInstall=True):
        """
        Export input segmentation node to glTF format.
        Export relies on the SlicerOpenAnatomy extension. If extension is not available, export will try to install it
        provided an internet connection is available.

        Otherwise, export will fail and will ask users to install the extension manually to proceed.
        """
        try:
            from OpenAnatomyExport import OpenAnatomyExportLogic

            logic = OpenAnatomyExportLogic()
            shNode = slicer.vtkMRMLSubjectHierarchyNode.GetSubjectHierarchyNode(slicer.mrmlScene)
            segmentationItem = shNode.GetItemByDataNode(segmentationNode)
            logic.exportModel(segmentationItem, folderPath, gltfReductionFactor, "glTF")
        except ImportError:
            if not tryInstall or not self.hasInternetConnectionF():
                slicer.util.errorDisplay(
                    "Failed to export to glTF. Try installing the SlicerOpenAnatomy extension manually to continue."
                )
                return
            self._installOpenAnatomyExtension()
            self._exportToGLTF(segmentationNode, folderPath, gltfReductionFactor, tryInstall=False)

    @classmethod
    def _installOpenAnatomyExtension(cls):
        # Install extension from extension manager
        extensionManager = slicer.app.extensionsManagerModel()
        extensionManager.setInteractive(False)
        extName = "SlicerOpenAnatomy"
        if extensionManager.isExtensionInstalled(extName):
            return

        success = extensionManager.installExtensionFromServer(extName, False, False)
        if not success:
            slicer.util.errorDisplay(f"Failed to install {extName} extension from server.")
            return

        # If install was successful, load the open anatomy export module to be used by the exporter
        moduleName = "OpenAnatomyExport"
        modulePath = extensionManager.extensionModulePaths(extName)[0] + f"/{moduleName}.py"
        factory = slicer.app.moduleManager().factoryManager()
        factory.registerModule(qt.QFileInfo(modulePath))
        factory.loadModules([moduleName])
