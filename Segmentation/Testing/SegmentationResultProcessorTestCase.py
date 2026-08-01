# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2024, Gauthier DOT
# Adapted by DentoFac from SlicerDentalSegmentator commit 476043f00009c372f0653dc759d69e2e559ed0f4; modified from upstream.

import unittest
import numpy as np

from ._headless_stubs import install as _install
_install()

from DentoFacSegmentatorLib import SegmentationResultProcessor

class _FakeEffect:
    def __init__(self):
        self.parameters = {}
        self.applied = False

    def setParameter(self, key, value):
        self.parameters[key] = value

    def self(self):
        return self

    def onApply(self):
        self.applied = True


class _FakeSegmentEditorWidget:
    def __init__(self):
        self.currentSegmentID = None
        self.effect = _FakeEffect()

    def setCurrentSegmentID(self, segmentId):
        self.currentSegmentID = segmentId

    def effectByName(self, name):
        if name == "Islands":
            return self.effect
        return None


class _FakeSegment:
    def __init__(self, name):
        self.name = name

    def GetName(self):
        return self.name


class _FakeSegmentation:
    def GetSegment(self, segmentId):
        if segmentId == "Segment_5":
            return None # e.g. omitted or just returning for valid ones
        return _FakeSegment(f"Fake {segmentId}")


class _FakeSegmentationNode:
    def __init__(self):
        self.segmentation = _FakeSegmentation()

    def GetSegmentation(self):
        return self.segmentation


class _FakeVolumeNode:
    def GetSpacing(self):
        return (0.5, 0.5, 0.5)


class SegmentationResultProcessorTestCase(unittest.TestCase):
    def test_minimumIslandSizeInVoxels(self):
        # spacing=(0.5, 0.5, 0.5), minSize=60 -> voxel volume 0.125 -> ceil(60/0.125) = 480
        self.assertEqual(
            SegmentationResultProcessor.minimumIslandSizeInVoxels((0.5, 0.5, 0.5), 60),
            480
        )

        # spacing=(1.0, 1.0, 1.0), minSize=60 -> 60
        self.assertEqual(
            SegmentationResultProcessor.minimumIslandSizeInVoxels((1.0, 1.0, 1.0), 60),
            60
        )

        # non-integer case exercising ceil: spacing=(0.4, 0.4, 0.4) -> 64e-3 -> ceil(60/0.064) = 938
        self.assertEqual(
            SegmentationResultProcessor.minimumIslandSizeInVoxels((0.4, 0.4, 0.4), 60),
            938
        )

    def test_domain_table_integrity(self):
        self.assertEqual(len(SegmentationResultProcessor.SEGMENT_LABELS), 5)
        self.assertEqual(len(SegmentationResultProcessor.SEGMENT_COLORS), 5)
        self.assertEqual(len(SegmentationResultProcessor.SEGMENT_OPACITIES), 5)

        self.assertEqual(
            SegmentationResultProcessor.SEGMENT_LABELS,
            ["Maxilla & Upper Skull", "Mandible", "Upper Teeth", "Lower Teeth", "Mandibular canal"]
        )

        self.assertEqual(SegmentationResultProcessor.segmentId(0), "Segment_1")
        self.assertEqual(SegmentationResultProcessor.segmentId(4), "Segment_5")

    def test_classifySegmentQuality_returns_only_missing_and_sparse_segments(self):
        flags = SegmentationResultProcessor.classifySegmentQuality({
            "Maxilla & Upper Skull": 1250,
            "Mandible": 0,
            "Upper Teeth": 9.9,
            "Lower Teeth": 10,
            "Mandibular canal": None,
        })

        self.assertEqual(flags, [
            ("Mandible", SegmentationResultProcessor.QUALITY_MISSING),
            ("Upper Teeth", SegmentationResultProcessor.QUALITY_SPARSE),
            ("Mandibular canal", SegmentationResultProcessor.QUALITY_MISSING),
        ])

    def test_classifySegmentQuality_uses_configurable_threshold(self):
        flags = SegmentationResultProcessor.classifySegmentQuality(
            {"Mandible": 24}, sparseThresholdMm3=25
        )
        self.assertEqual(flags, [("Mandible", SegmentationResultProcessor.QUALITY_SPARSE)])
        self.assertEqual(
            SegmentationResultProcessor.classifySegmentQuality({"Mandible": 25}, sparseThresholdMm3=25),
            [],
        )

    def test_postProcess_targets_right_segments(self):
        fake_editor = _FakeSegmentEditorWidget()
        processor = SegmentationResultProcessor(
            segmentEditorWidget=fake_editor,
            show3DButton=None, # not used in postProcess
            minimumIslandSize_mm3=60
        )

        fake_segmentation_node = _FakeSegmentationNode()
        fake_volume_node = _FakeVolumeNode()

        # Track what happens across the 4 valid segments (Segment_1 to Segment_4)
        # Note: In our current implementation, we just call them in sequence.
        # But _removeSmallIsland reaches into the fake editor each time and overwrites state.
        # We can just verify it completes without error, or we can use a mock.
        # Given it runs in sequence, the last segment processed is Segment_4.

        processor.postProcess(fake_segmentation_node, fake_volume_node)

        self.assertEqual(fake_editor.currentSegmentID, "Segment_4")
        self.assertEqual(fake_editor.effect.parameters["Operation"], "REMOVE_SMALL_ISLANDS")
        self.assertEqual(fake_editor.effect.parameters["MinimumSize"], 480)
        self.assertTrue(fake_editor.effect.applied)
