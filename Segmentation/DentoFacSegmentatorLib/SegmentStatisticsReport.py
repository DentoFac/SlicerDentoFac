# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2024, Gauthier DOT
# Adapted by DentoFac from SlicerDentalSegmentator commit 476043f00009c372f0653dc759d69e2e559ed0f4; modified from upstream.

"""Pure formatting and CSV serialization for segmentation volume measurements."""

import csv
import io
import math
from dataclasses import dataclass


STRUCTURE_ORDER = (
    "Maxilla & Upper Skull",
    "Mandible",
    "Upper Teeth",
    "Lower Teeth",
    "Mandibular canal",
)


@dataclass(frozen=True)
class SegmentVolumeRow:
    """One display-ready volume measurement.

    The display strings are deliberately also used in the CSV, so copied and
    saved reports contain exactly the values presented in the table.
    """

    structure: str
    volume_cc: str
    volume_mm3: str


@dataclass(frozen=True)
class SegmentStatisticsReport:
    rows: tuple
    csv_text: str


def buildReport(volumes_mm3):
    """Create display rows and CSV text from ``{segment_name: volume_mm3}``.

    Invalid and negative measurements are ignored.  Zero is retained here so
    callers that explicitly consider a zero-volume segment present can report
    it; the Slicer adapter omits empty segments before calling this function.
    """
    order = {name: index for index, name in enumerate(STRUCTURE_ORDER)}
    valid_volumes = []
    for input_index, (name, raw_volume) in enumerate(volumes_mm3.items()):
        try:
            volume_mm3 = float(raw_volume)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(volume_mm3) or volume_mm3 < 0:
            continue
        valid_volumes.append((order.get(name, len(order)), input_index, str(name), volume_mm3))

    rows = tuple(
        SegmentVolumeRow(
            structure=name,
            volume_cc=f"{volume_mm3 / 1000.0:.3f}",
            volume_mm3=f"{volume_mm3:.3f}",
        )
        for _, _, name, volume_mm3 in sorted(valid_volumes)
    )

    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(("Structure", "Volume (cc)", "Volume (mm³)"))
    for row in rows:
        writer.writerow((row.structure, row.volume_cc, row.volume_mm3))
    return SegmentStatisticsReport(rows=rows, csv_text=output.getvalue())
