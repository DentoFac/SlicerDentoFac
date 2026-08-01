# DentoFac Segmentator test tiers

Run the blocking plain-Python regression tier from the extension root:

```bash
python -m compileall -q DentoFac Segmentation
PYTHONPATH=DentoFac:Segmentation python -m pytest -q \
  DentoFac/Testing/SharedServicesTestCase.py \
  Segmentation/Testing/PythonDependencyCheckerTestCase.py \
  Segmentation/Testing/ExportManagerTestCase.py \
  Segmentation/Testing/SegmentationResultProcessorTestCase.py \
  Segmentation/Testing/ModuleSettingsTestCase.py
```

The three commands above are the required local pre-commit sequence for every
later DentoFac Segmentator slice. The GitHub Actions workflow runs the same
syntax and headless suite on pull requests and `main` pushes.

- Headless tier: `DentoFac/Testing/SharedServicesTestCase`, `PythonDependencyCheckerTestCase`,
  `SegmentationResultProcessorTestCase`, `InferenceProgressTestCase`, and
  `ModuleSettingsTestCase` (including settings migration).
- Dual tier: `ExportManagerTestCase` runs in blocking headless CI and Slicer;
  six real-Slicer monkey-patch failures are the named reference-baseline
  quarantine.
- Slicer tier: `DentoFacSegmentatorWidgetTestCase`,
  `SegmentStatisticsReportTestCase`, `SegmentationWidgetTestCase`, and
  `SupportDiagnosticsTestCase`.
- Slicer-only slow tier: `IntegrationTestCase`.

For the local Slicer runtime gate, include `-m "not slow and not
baseline_slicer_runtime_quarantine"`. The named quarantine preserves the six
`ExportManagerTestCase` assertions that monkey-patch immutable Slicer/Qt
bindings and three `PythonDependencyCheckerTestCase` model-path assertions
that deliberately expect the headless fallback. The two data-dependent widget
export tests are expected-skipped with their class, bringing the originally
observed eleven baseline failures under explicit tracking rather than silently
weakening any assertion.

`SegmentationWidgetTestCase` depends on excluded upstream NIfTI fixtures and
is expected-skipped until a replacement fixture has documented redistribution,
citation, and de-identification approval. Its result loading, measurements,
and export parity remain a Phase 5 gate.
