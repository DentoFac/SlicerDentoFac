# DentoFac

DentoFac is one installable 3D Slicer extension package for curated
dento-maxillo-facial workflows.

[License](LICENSE) · [Third-party notices](THIRD_PARTY_NOTICES.md) · [Contributing](CONTRIBUTING.md)

The package currently contains:

- **DentoFac Hub** — a visible setup, readiness, and diagnostics entry point.
- **DentoFac Segmentator** — the first workflow module. It is presently a
  migration scaffold; the existing segmentation workflow will be ported in
  tested slices.

DentoFacLib is an internal shared Python library. It is packaged with the
Hub module and may be imported by DentoFac workflow modules; it is not an
independently installable extension.

## Approach and attribution

DentoFac curates and integrates dental workflows to give dental clinicians a
more unified, predictable experience in 3D Slicer. Some DentoFac workflows may
redistribute, adapt, or build on existing open-source Slicer extensions and
their associated models.

This work is intended to complement the Slicer extension ecosystem, not to
misrepresent or replace the work of its original developers. For every
upstream project incorporated into DentoFac, we will:

- retain the applicable license, copyright notices, citations, and required
  attribution;
- identify the upstream project and the DentoFac-specific changes in the
  relevant module documentation and release notes;
- keep provenance for bundled models, data, and third-party dependencies;
- contribute fixes and generally useful improvements upstream where practical;
  and
- make clear that DentoFac is maintained and supported by the DentoFac team,
  unless an upstream project explicitly states otherwise.

We welcome conversation with upstream maintainers and will respond promptly to
licensing, attribution, compatibility, or collaboration concerns.

## Licensing and third-party components

DentoFac-owned source code and documentation are licensed under
[Apache License 2.0](LICENSE). DentoFac may also redistribute or adapt
components that have their own licenses, notices, citation requirements, model
terms, or distribution conditions. Those component-specific terms remain in
force and take precedence for the applicable component.

Our [third-party notices](THIRD_PARTY_NOTICES.md) record incorporated
components. Each addition must identify its upstream source, version or commit,
license, required notices, and DentoFac modifications; any required license
texts are kept in [`LICENSES/`](LICENSES/). A component must not be included
until its license and redistribution obligations have been reviewed. See
[CONTRIBUTING.md](CONTRIBUTING.md) for the contribution requirements.

## Development status

This repository is intentionally starting with package structure and import
boundaries. It does not yet ship the clinical segmentation workflow, model
weights, or Python-runtime installer.
