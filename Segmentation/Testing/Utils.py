# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2024, Gauthier DOT
# Adapted by DentoFac from SlicerDentalSegmentator commit 476043f00009c372f0653dc759d69e2e559ed0f4; modified from upstream.

import unittest
from pathlib import Path

import slicer


class DentoFacSegmentatorTestCase(unittest.TestCase):
    def setUp(self):
        self._clearScene()

    @staticmethod
    def _clearScene():
        slicer.app.processEvents()
        slicer.mrmlScene.Clear()
        slicer.app.processEvents()

    def tearDown(self):
        slicer.app.processEvents()


def _dataFolderPath():
    return Path(__file__).parent.joinpath("Data")


def load_test_CT_volume():
    import SampleData
    SampleData.SampleDataLogic().downloadDentalSurgery()
    return list(slicer.mrmlScene.GetNodesByName("PostDentalSurgery"))[0]


def get_test_multi_label_path():
    return _dataFolderPath().joinpath("PostDentalSurgery_Segmentation.nii.gz").as_posix()


def get_test_multi_label_path_with_segments_1_3_5():
    return _dataFolderPath().joinpath("PostDentalSurgery_Segmentation_1_3_5.nii.gz").as_posix()
