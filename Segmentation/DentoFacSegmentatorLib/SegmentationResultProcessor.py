# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2024, Gauthier DOT
# Adapted by DentoFac from SlicerDentalSegmentator commit 476043f00009c372f0653dc759d69e2e559ed0f4; modified from upstream.

import SegmentEditorEffects
import numpy as np
import qt
import slicer


class SegmentationResultProcessor:
    """Applies DentoFacSegmentator's fixed segment styling and island post-processing to an
    nnUNet inference result. Owns the anatomy label/color/opacity table and the minimum
    island size so this domain knowledge lives in one place, not in the UI widget."""

    SEGMENT_LABELS = ["Maxilla & Upper Skull", "Mandible", "Upper Teeth", "Lower Teeth", "Mandibular canal"]
    SEGMENT_COLORS = ["#E3DD90", "#D4A1E6", "#DC9565", "#EBDFB4", "#D8654F"]
    SEGMENT_OPACITIES = [0.45, 0.45, 1.0, 1.0, 1.0]

    # A result below 10 mm³ is normally too small to be a useful anatomical
    # structure.  Keep this domain threshold here with the other result
    # processing constants, rather than duplicating it in the widget.
    RESULT_QUALITY_SPARSE_THRESHOLD_MM3 = 10.0
    QUALITY_MISSING = "missing"
    QUALITY_SPARSE = "sparse"

    def __init__(self, segmentEditorWidget, show3DButton, progressCallback=None,
                 minimumIslandSize_mm3=60):
        self._segmentEditorWidget = segmentEditorWidget
        self._show3DButton = show3DButton
        self._progressCallback = progressCallback or (lambda *_: None)
        self._minimumIslandSize_mm3 = minimumIslandSize_mm3

    def initializeDisplay(self, segmentationNode, volumeNode):
        if not segmentationNode:
            return

        segmentationNode.SetReferenceImageGeometryParameterFromVolumeNode(volumeNode)
        if not segmentationNode.GetDisplayNode():
            segmentationNode.CreateDefaultDisplayNodes()
            slicer.app.processEvents()

        segmentationNode.SetDisplayVisibility(True)

        # Reset 3D view to fit current segmentation
        layoutManager = slicer.app.layoutManager()
        if layoutManager is not None:
            threeDWidget = layoutManager.threeDWidget(0)
            if threeDWidget:
                threeDWidget.threeDView().rotateToViewAxis(3)
            slicer.util.resetThreeDViews()

    def updateDisplay(self, segmentationNode, volumeNode):
        if not segmentationNode:
            return

        self.initializeDisplay(segmentationNode, volumeNode)
        segmentation = segmentationNode.GetSegmentation()
        colors = [self.toRGB(c) for c in self.SEGMENT_COLORS]
        segmentIds = [self.segmentId(i) for i in range(len(self.SEGMENT_LABELS))]

        segmentationDisplayNode = segmentationNode.GetDisplayNode()
        for segmentId, label, color, opacity in zip(segmentIds, self.SEGMENT_LABELS, colors, self.SEGMENT_OPACITIES):
            segment = segmentation.GetSegment(segmentId)
            if segment is None:
                continue

            segment.SetName(label)
            segment.SetColor(*color)
            segmentationDisplayNode.SetSegmentOpacity3D(segmentId, opacity)

        self._show3DButton.setChecked(True)
        if slicer.app.layoutManager() is not None:
            slicer.util.resetThreeDViews()

    def postProcess(self, segmentationNode, volumeNode):
        self._progressCallback("Post processing results...")
        self._removeSmallIsland(segmentationNode, volumeNode, "Segment_1")
        self._removeSmallIsland(segmentationNode, volumeNode, "Segment_2")
        self._removeSmallIsland(segmentationNode, volumeNode, "Segment_3")
        self._removeSmallIsland(segmentationNode, volumeNode, "Segment_4")
        self._progressCallback("Post processing done.")

    def _keepLargestIsland(self, segmentationNode, segmentId):
        segment = self._getSegment(segmentationNode, segmentId)
        if not segment:
            return

        self._progressCallback(f"Keep largest region for {segment.GetName()}...")
        self._segmentEditorWidget.setCurrentSegmentID(segmentId)
        effect = self._segmentEditorWidget.effectByName("Islands")
        effect.setParameter("Operation", SegmentEditorEffects.KEEP_LARGEST_ISLAND)
        effect.self().onApply()

    def _removeSmallIsland(self, segmentationNode, volumeNode, segmentId):
        segment = self._getSegment(segmentationNode, segmentId)
        if not segment:
            return

        self._progressCallback(f"Remove small voxels for {segment.GetName()}...")
        self._segmentEditorWidget.setCurrentSegmentID(segmentId)
        minimumIslandSize = self.minimumIslandSizeInVoxels(volumeNode.GetSpacing(), self._minimumIslandSize_mm3)
        effect = self._segmentEditorWidget.effectByName("Islands")
        effect.setParameter("Operation", SegmentEditorEffects.REMOVE_SMALL_ISLANDS)
        effect.setParameter("MinimumSize", minimumIslandSize)
        effect.self().onApply()

    def _getSegment(self, segmentationNode, segmentId):
        if not segmentationNode:
            return
        return segmentationNode.GetSegmentation().GetSegment(segmentId)

    @staticmethod
    def segmentId(index):
        return f"Segment_{index + 1}"

    @staticmethod
    def minimumIslandSizeInVoxels(spacing, minimumIslandSize_mm3):
        """Voxel-count threshold for a mm³ island size given a volume's spacing. Pure, so it
        is unit-testable without a Slicer scene."""
        voxelSize_mm3 = np.cumprod(spacing)[-1]
        return int(np.ceil(minimumIslandSize_mm3 / voxelSize_mm3))

    @classmethod
    def classifySegmentQuality(cls, volumesMm3, sparseThresholdMm3=None):
        """Return quality warnings for empty or implausibly small segments.

        ``volumesMm3`` is a ``{segment_name: volume_mm3}`` mapping, allowing
        this classifier to be unit-tested without a Slicer scene.  Normal
        segments are deliberately omitted: callers receive only the warnings
        they need to surface to a user.
        """
        threshold = (
            cls.RESULT_QUALITY_SPARSE_THRESHOLD_MM3
            if sparseThresholdMm3 is None else float(sparseThresholdMm3)
        )
        if threshold < 0:
            raise ValueError("sparseThresholdMm3 must be non-negative")

        # Retain the familiar DentoFacSegmentator structure order, while only
        # classifying values the caller supplied.  The Slicer adapter supplies
        # zero for an omitted fixed segment so it is reported as missing.
        names = [name for name in cls.SEGMENT_LABELS if name in volumesMm3]
        names.extend(name for name in volumesMm3 if name not in cls.SEGMENT_LABELS)
        flags = []
        for name in names:
            try:
                volume = float(volumesMm3.get(name, 0))
            except (TypeError, ValueError):
                volume = 0.0
            if not np.isfinite(volume) or volume <= 0:
                flags.append((name, cls.QUALITY_MISSING))
            elif volume < threshold:
                flags.append((name, cls.QUALITY_SPARSE))
        return flags

    @staticmethod
    def toRGB(colorString):
        color = qt.QColor(colorString)
        return color.redF(), color.greenF(), color.blueF()

    @staticmethod
    def copyResultsToExistingNode(currentSegmentation, segmentationNode):
        currentName = currentSegmentation.GetName()
        currentSegmentation.Copy(segmentationNode)
        currentSegmentation.SetName(currentName)
        slicer.mrmlScene.RemoveNode(segmentationNode)
