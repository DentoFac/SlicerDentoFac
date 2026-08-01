# DentoFac third-party notices

DentoFac-owned source code and documentation are licensed under Apache License
2.0. This file records components distributed with DentoFac that are subject to
different terms.

## Distributed components

### SlicerDentalSegmentator workflow source

- **Purpose:** The DentoFac Segmentator clinical workflow, including its module,
  workflow-specific Python library, and regression tests.
- **Source:** https://github.com/gaudot/SlicerDentalSegmentator
- **Pinned source:** commit `476043f00009c372f0653dc759d69e2e559ed0f4`.
- **License:** Apache License 2.0. The full upstream license text is retained at
  [`LICENSES/SlicerDentalSegmentator-Apache-2.0.txt`](LICENSES/SlicerDentalSegmentator-Apache-2.0.txt).
- **Copyright:** Copyright (c) 2024, Gauthier DOT.
- **Modifications:** Imported into `Segmentation/` under the DentoFac module and
  package names. Every imported Python file carries an SPDX identifier, copyright
  notice, source revision, and modification notice.
- **Acknowledgements:** Original contributors include Gauthier DOT (AP-HP),
  Laurent GAJNY (ENSAM), Roman FENIOUX (KITWARE SAS), and Thibault PELLETIER
  (KITWARE SAS). The module acknowledgement UI and its model-download provenance
  retain links to the upstream project.

### Asset inventory and exclusions

| Asset | Source/provenance | Distribution status | Notes |
|---|---|---|---|
| Five module icons | Replaced by DentoFac-owned assets in `Segmentation/Resources/Icons/` | Distributed | No upstream binary icons were copied because the pinned source provides no asset-specific terms. |
| `PostDentalSurgery_Segmentation*.nii.gz` | Pinned upstream test data | Excluded | No redistribution, citation, or de-identification record was available. Data-dependent Slicer tests are explicitly skipped pending an approved replacement fixture. |
| nnU-Net model weights | Upstream GitHub release; related DOI `10.5281/zenodo.10829674` | Not distributed | Download-only. The initial workflow keeps the upstream host as model provenance and does not imply DentoFac ownership. |

## Required record for each future component

Before incorporating an extension, model, dataset, dependency, or other
third-party asset, add an entry containing:

- component name and purpose;
- upstream project or source URL;
- exact version, release, commit, or content hash used;
- applicable license and the path to its copied license text in `LICENSES/`;
- copyright notices, citation requests, trademark restrictions, and any
  redistribution conditions; and
- a concise description of DentoFac modifications and the locations of the
  modified files.

If the component's terms conflict with the intended DentoFac distribution,
resolve the conflict before shipping it. The component's own terms govern that
component; this repository's Apache License does not supersede them.
