# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2024, Gauthier DOT
# Adapted by DentoFac from SlicerDentalSegmentator commit 476043f00009c372f0653dc759d69e2e559ed0f4; modified from upstream.

import unittest

# Register the headless qt/slicer/SegmentationWidget stubs before importing the package.
from ._headless_stubs import install as _install_headless_stubs
_install_headless_stubs()

from DentoFacSegmentatorLib.InferenceProgress import (
    ProgressTracker,
    ProgressUpdate,
    formatElapsedTime,
    parseProgress,
)


class InferenceProgressTestCase(unittest.TestCase):
    def test_parses_nnunet_stage_markers(self):
        self.assertEqual(
            parseProgress("preprocessing input images"),
            ProgressUpdate("Preprocessing"),
        )
        self.assertEqual(
            parseProgress("Predicting case 001 with sliding window"),
            ProgressUpdate("Predicting"),
        )
        self.assertEqual(
            parseProgress("exporting segmentation"),
            ProgressUpdate("Post-processing"),
        )

    def test_parses_percent_progress_when_present(self):
        self.assertEqual(
            parseProgress(" 42%|████▏     | 42/100 [00:10<00:14, 4.2it/s]"),
            ProgressUpdate("Predicting", 0.42),
        )
        self.assertEqual(
            parseProgress("Preprocessing: 100% complete"),
            ProgressUpdate("Preprocessing", 1.0),
        )

    def test_ignores_unrelated_or_malformed_lines(self):
        self.assertIsNone(parseProgress("using device: cuda"))
        self.assertIsNone(parseProgress("progress: 125%"))
        self.assertIsNone(parseProgress(""))
        self.assertIsNone(parseProgress(None))

    def test_formats_elapsed_time(self):
        self.assertEqual(formatElapsedTime(0), "00:00")
        self.assertEqual(formatElapsedTime(65.9), "01:05")
        self.assertEqual(formatElapsedTime(3661), "1:01:01")
        self.assertEqual(formatElapsedTime(-1), "00:00")

    def test_tracker_resets_fraction_when_stage_changes_or_has_no_percentage(self):
        tracker = ProgressTracker()
        tracker.apply(ProgressUpdate("Predicting", 0.5), elapsed=20)

        state = tracker.apply(ProgressUpdate("Post-processing"), elapsed=21)
        self.assertEqual(state.stage, "Post-processing")
        self.assertFalse(state.is_determinate)
        self.assertEqual(state.fraction_samples, 0)
        self.assertIsNone(state.eta_minutes)

    def test_tracker_requires_stable_progress_and_restarts_after_decrease(self):
        tracker = ProgressTracker()
        self.assertIsNone(tracker.apply(ProgressUpdate("Predicting", 0.3), elapsed=20).eta_minutes)
        self.assertIsNotNone(tracker.apply(ProgressUpdate("Predicting", 0.5), elapsed=40).eta_minutes)

        state = tracker.apply(ProgressUpdate("Predicting", 0.4), elapsed=50)
        self.assertEqual(state.fraction_samples, 1)
        self.assertIsNone(state.eta_minutes)

    def test_tracker_eta_is_anchored_to_last_progress_observation(self):
        tracker = ProgressTracker()
        tracker.apply(ProgressUpdate("Predicting", 0.25), elapsed=60)
        observed = tracker.apply(ProgressUpdate("Predicting", 0.5), elapsed=120)

        self.assertEqual(observed.eta_minutes, 2)
        self.assertEqual(tracker.snapshot(elapsed=1000).eta_minutes, 2)

    def test_tracker_hides_eta_before_ten_seconds_and_when_complete(self):
        tracker = ProgressTracker()
        tracker.apply(ProgressUpdate("Predicting", 0.25), elapsed=5)
        self.assertIsNone(tracker.apply(ProgressUpdate("Predicting", 0.5), elapsed=9).eta_minutes)
        self.assertIsNotNone(tracker.snapshot(elapsed=10).eta_minutes)
        self.assertIsNone(tracker.apply(ProgressUpdate("Predicting", 1.0), elapsed=11).eta_minutes)
