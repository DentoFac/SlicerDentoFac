# DentoFac

DentoFac is one installable 3D Slicer extension package for curated
dento-maxillo-facial workflows.

[License](LICENSE) · [Third-party notices](THIRD_PARTY_NOTICES.md) · [Contributing](CONTRIBUTING.md)

The package currently contains:

- **DentoFac Hub** — a visible setup, readiness, and diagnostics entry point.
- **DentoFac Segmentator** — an automatic nnU-Net workflow for dental CT and
  CBCT segmentation, including result review, measurements, quality flags,
  exports, activity logs, and support diagnostics.

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

## Using DentoFac Segmentator

Use **DentoFac Hub** to inspect shared runtime readiness and to initiate the
user-controlled setup actions. Open **DentoFac Segmentator** to select a dental
CT/CBCT volume and run the clinical workflow.

The extension requires the Slicer **NNUNet** extension (`SlicerNNUNet` module).
When NNUNet is installed, the Hub and Segmentator provide explicit actions for
installing its Python requirements and downloading the Segmentator model. These
actions are never started merely by opening a module. Downloaded model files are
stored in DentoFac application data, not in the installed extension; model
weights are not distributed with this package.

The initial supported baseline is **3D Slicer 5.12.3** with the NNUNet extension
available from its configured Extensions Index. The model download retains the
upstream SlicerDentalSegmentator release as provenance; DentoFac support and
issue reporting are routed to the DentoFac project.

## Development and validation

The blocking plain-Python regression tier and the local Slicer test tiers are
documented in [`Segmentation/Testing/README.md`](Segmentation/Testing/README.md).
Before a release, also configure/package against the supported Slicer developer
build, run CTest from that build, inspect the installed extension tree, and run
the clean-install, offline-cache, dependency/model recovery, device, and
clinical smoke checks described in the controller release plan.
