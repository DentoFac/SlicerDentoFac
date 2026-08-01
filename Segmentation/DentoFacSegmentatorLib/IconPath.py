# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2024, Gauthier DOT
# Adapted by DentoFac from SlicerDentalSegmentator commit 476043f00009c372f0653dc759d69e2e559ed0f4; modified from upstream.

from pathlib import Path

import qt


def iconPath(icon_name) -> str:
    return Path(__file__).parent.joinpath("..", "Resources", "Icons", icon_name).as_posix()


def icon(icon_name) -> "qt.QIcon":
    return qt.QIcon(iconPath(icon_name))
