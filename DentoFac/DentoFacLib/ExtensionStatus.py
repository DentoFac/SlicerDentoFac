"""Required Slicer extension manifest and status evaluation for the DentoFac Hub."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Optional, Sequence


@dataclass(frozen=True)
class ExpectedExtension:
    """One extension required by a DentoFac workflow.

    ``require_accepted_revision=False`` is the deliberate per-extension
    present-only gate.  Keep the default exact pin: Slicer extension revisions
    are Git SHAs and are not semver values that can safely be ordered.
    """

    name: str
    expected_version: str
    accepted_scmrevisions: Sequence[str]
    require_accepted_revision: bool = True


# The manifest is intentionally owned here rather than by the Hub UI.  Adding a
# future workflow extension is a declarative change to this list.
EXPECTED_EXTENSIONS = [
    ExpectedExtension(
        name="NNUNet",
        expected_version="0cb736d",
        accepted_scmrevisions=["0cb736d"],
    ),
]


MINIMUM_GIT_SHA_PREFIX_LENGTH = 7


@dataclass(frozen=True)
class ExtensionStatusRow:
    name: str
    expected_version: str
    detected_version: Optional[str]
    status: str  # present_ok, version_mismatch, or missing


@dataclass(frozen=True)
class ExtensionStatusReport:
    rows: tuple[ExtensionStatusRow, ...]
    all_ok: bool

    @property
    def problem_count(self) -> int:
        return sum(row.status != "present_ok" for row in self.rows)


def _revisions_match(detected_revision: str, accepted_revision: str) -> bool:
    """Return whether two short or full Git SHAs identify the same revision."""
    detected = detected_revision.strip().lower()
    accepted = accepted_revision.strip().lower()
    if not detected or not accepted:
        return False
    if not all(character in "0123456789abcdef" for character in detected + accepted):
        return False
    shorter, longer = sorted((detected, accepted), key=len)
    return len(shorter) >= MINIMUM_GIT_SHA_PREFIX_LENGTH and longer.startswith(shorter)


def evaluate_required_extensions(
    manifest: Iterable[ExpectedExtension], detected_revisions: Mapping[str, Optional[str]],
) -> ExtensionStatusReport:
    """Evaluate extension metadata without importing Qt or Slicer.

    ``detected_revisions`` maps an installed extension name to its ``scmrevision``;
    ``None`` means it is not installed.  This narrow contract keeps the gate
    independently unit-testable in a plain Python process.
    """

    rows = []
    for expected in manifest:
        detected = detected_revisions.get(expected.name)
        if detected is None:
            status = "missing"
        elif not expected.require_accepted_revision or any(
            _revisions_match(detected, accepted) for accepted in expected.accepted_scmrevisions
        ):
            status = "present_ok"
        else:
            status = "version_mismatch"
        rows.append(ExtensionStatusRow(expected.name, expected.expected_version, detected, status))
    return ExtensionStatusReport(tuple(rows), all(row.status == "present_ok" for row in rows))


def collect_installed_extension_revisions(
    manifest: Iterable[ExpectedExtension] = EXPECTED_EXTENSIONS,
) -> dict[str, Optional[str]]:
    """Read required extension revisions from Slicer's extensions manager.

    The manager API has changed across Slicer releases, so every access is
    guarded.  A manager failure is represented as unavailable/not installed;
    the Hub remains usable and reports that the requirement needs attention.
    """

    entries = tuple(manifest)
    detected = {entry.name: None for entry in entries}
    try:
        import slicer

        manager_factory = getattr(getattr(slicer, "app", None), "extensionsManagerModel", None)
        manager = manager_factory() if callable(manager_factory) else manager_factory
        if manager is None:
            return detected

        installed_extensions = getattr(manager, "installedExtensions", ())
        installed_extensions = installed_extensions() if callable(installed_extensions) else installed_extensions
        installed_names = set(installed_extensions or ())
        is_installed = getattr(manager, "isExtensionInstalled", None)
        metadata_for = getattr(manager, "extensionMetadata", None)

        for entry in entries:
            try:
                installed = bool(is_installed(entry.name)) if callable(is_installed) else entry.name in installed_names
                if not installed:
                    continue
                metadata = metadata_for(entry.name) if callable(metadata_for) else {}
                revision = metadata.get("scmrevision") if hasattr(metadata, "get") else None
                # An installed extension without metadata is a version mismatch,
                # not a false "not installed" result.
                detected[entry.name] = revision or "unknown"
            except (AttributeError, RuntimeError, TypeError):
                continue
    except (ImportError, AttributeError, RuntimeError, TypeError):
        pass
    return detected
