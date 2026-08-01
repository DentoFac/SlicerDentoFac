# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2024, Gauthier DOT
# Adapted by DentoFac from SlicerDentalSegmentator commit 476043f00009c372f0653dc759d69e2e559ed0f4; modified from upstream.

"""Shared headless stub bootstrap for the pure (non-Slicer) test suites.

These test files (`ExportManagerTestCase`, `PythonDependencyCheckerTestCase`) run under plain
Python in CI where the Slicer application — and its C++ modules `slicer`, `qt`, `ctk`,
`SegmentEditorEffects` — is absent. They import `DentoFacSegmentatorLib`, whose package
``__init__`` eagerly imports `SegmentationWidget` (which pulls in `SegmentEditorEffects`/`ctk`),
so lightweight stubs must be registered in ``sys.modules`` *before* that import runs.

Centralizing the stubs here (rather than duplicating them per test file) keeps a single source
of truth and makes the setup order-independent: pytest imports every test module during
collection before running any test, so whichever file is collected first would otherwise
install its own partial stub and leave the next file running against it. `install()` is:

* **Headless-gated** via a real Slicer-only probe (`import ctk`), not by "is `slicer` in
  ``sys.modules``" — the latter cannot tell a sibling test's stub from a real Slicer module,
  which is exactly what made the per-file setup order-dependent.
* **Additive / idempotent** — every module and attribute is created only when missing, so
  calling it from multiple files (in any order) composes, and under real Slicer it is a no-op
  because every attribute already exists.

Usable under both ``pytest`` and ``python -m unittest`` / Slicer's self-test runner because it
is a normal importable module, not a ``conftest.py`` (which only ``pytest`` loads).
"""

import sys
import types
from pathlib import Path


def is_headless():
    """True when running outside a Slicer application (Slicer-only ``ctk`` unavailable)."""
    try:
        import ctk  # noqa: F401
        return False
    except ImportError:
        return True


def _ensure_module(name):
    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
        sys.modules[name] = module
    return module


def _ensure_attr(obj, name, factory):
    # Add the attribute only when missing, so we augment (never clobber) a stub another
    # headless test already installed, and stay idempotent across pytest collection.
    if not hasattr(obj, name):
        setattr(obj, name, factory())


class _StubQMessageBox:
    Yes = 1
    No = 2

    @classmethod
    def question(cls, parent, title, text):
        return cls.No


class _FakeSubjectHierarchyNode:
    @staticmethod
    def GetSubjectHierarchyNode(scene):
        return _FakeSubjectHierarchyNode()

    def GetItemByDataNode(self, node):
        return "dummy_item"


class _FakeSegmentationWidget:
    # Mirrors the real SegmentationWidget's static entry points that the pure suites patch or
    # call. PythonDependencyCheckerTestCase does
    # ``mock.patch("...SegmentationWidget.SegmentationWidget.isNNUNetModuleInstalled")``, which
    # requires the attribute to exist on this fake.
    @staticmethod
    def nnUnetFolder():
        return Path(".")

    @staticmethod
    def isNNUNetModuleInstalled():
        return True


class _StubExportFormat:
    pass


def _make_segmentations_logic():
    module = types.ModuleType("slicer.vtkSlicerSegmentationsModuleLogic")
    module.ExportSegmentsClosedSurfaceRepresentationToFiles = lambda *args: None
    module.ExportSegmentsBinaryLabelmapRepresentationToFiles = lambda *args: None
    return module


def _make_subject_hierarchy():
    module = types.ModuleType("slicer.vtkMRMLSubjectHierarchyNode")
    module.GetSubjectHierarchyNode = _FakeSubjectHierarchyNode.GetSubjectHierarchyNode
    return module


def install():
    """Install the union of headless ``qt``/``slicer``/``DentoFacSegmentatorLib`` stubs.

    No-op under a real Slicer. Safe to call from every pure test module, in any order.
    """
    if not is_headless():
        return

    stub_qt = _ensure_module("qt")
    _ensure_attr(stub_qt, "QMessageBox", lambda: _StubQMessageBox)

    stub_segment_editor_effects = _ensure_module("SegmentEditorEffects")
    _ensure_attr(stub_segment_editor_effects, "KEEP_LARGEST_ISLAND", lambda: "KEEP_LARGEST_ISLAND")
    _ensure_attr(stub_segment_editor_effects, "REMOVE_SMALL_ISLANDS", lambda: "REMOVE_SMALL_ISLANDS")

    stub_slicer = _ensure_module("slicer")
    stub_slicer_util = _ensure_module("slicer.util")
    _ensure_attr(stub_slicer, "util", lambda: stub_slicer_util)
    _ensure_attr(stub_slicer_util, "errorDisplay", lambda: (lambda *args, **kwargs: None))
    _ensure_attr(stub_slicer, "app", lambda: types.ModuleType("slicer.app"))
    _ensure_attr(stub_slicer, "mrmlScene", lambda: "dummy_scene")
    _ensure_attr(stub_slicer, "vtkSlicerSegmentationsModuleLogic", _make_segmentations_logic)
    _ensure_attr(stub_slicer, "vtkMRMLSubjectHierarchyNode", _make_subject_hierarchy)

    # Stub the SegmentationWidget submodule so DentoFacSegmentatorLib/__init__'s eager
    # ``from .SegmentationWidget import SegmentationWidget, ExportFormat`` resolves without
    # importing the Slicer-only UI dependencies it pulls in. The real ExportFormat is still
    # imported directly from DentoFacSegmentatorLib.ExportManager by the tests that need it.
    if "DentoFacSegmentatorLib.SegmentationWidget" not in sys.modules:
        stub_seg_widget = types.ModuleType("DentoFacSegmentatorLib.SegmentationWidget")
        stub_seg_widget.SegmentationWidget = _FakeSegmentationWidget
        stub_seg_widget.ExportFormat = _StubExportFormat
        sys.modules["DentoFacSegmentatorLib.SegmentationWidget"] = stub_seg_widget
