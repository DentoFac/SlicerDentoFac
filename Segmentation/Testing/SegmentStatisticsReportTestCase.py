# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2024, Gauthier DOT
# Adapted by DentoFac from SlicerDentalSegmentator commit 476043f00009c372f0653dc759d69e2e559ed0f4; modified from upstream.

import csv
import io
import unittest

from ._headless_stubs import install as _install
_install()

from DentoFacSegmentatorLib.SegmentStatisticsReport import buildReport


class SegmentStatisticsReportTestCase(unittest.TestCase):
    def test_builds_clinically_ordered_display_rows_and_csv(self):
        report = buildReport({
            "Lower Teeth": 1234.5,
            "Mandible": 4567.89,
            "Maxilla & Upper Skull": 10,
        })

        self.assertEqual(
            [row.structure for row in report.rows],
            ["Maxilla & Upper Skull", "Mandible", "Lower Teeth"],
        )
        self.assertEqual(report.rows[1].volume_cc, "4.568")
        self.assertEqual(report.rows[1].volume_mm3, "4567.890")

        csv_rows = list(csv.reader(io.StringIO(report.csv_text)))
        self.assertEqual(csv_rows[0], ["Structure", "Volume (cc)", "Volume (mm³)"])
        self.assertEqual(csv_rows[2], ["Mandible", "4.568", "4567.890"])

    def test_omits_invalid_or_negative_values_but_keeps_zero(self):
        report = buildReport({
            "Empty but present": 0,
            "Negative": -1,
            "Not a number": "bad",
            "Infinite": float("inf"),
        })

        self.assertEqual(len(report.rows), 1)
        self.assertEqual(report.rows[0].structure, "Empty but present")
        self.assertEqual(report.rows[0].volume_cc, "0.000")
        self.assertEqual(report.rows[0].volume_mm3, "0.000")


if __name__ == "__main__":
    unittest.main()
