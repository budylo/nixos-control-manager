# Changelog

All notable user-visible changes are documented here. Versions use the public
release name; Python packaging may normalize prereleases to PEP 440 spelling.

## Unreleased

### Added

- read-only Flakes control center for `flake.nix`, `flake.lock`, direct locked
  inputs, available `nixosConfigurations`, and active-target verification;
- fail-closed Flake inspection: missing or invalid lock files prevent Nix
  evaluation, while valid configurations are evaluated offline without lock
  writes, input updates, network access, or import-from-derivation;
- read-only package compatibility inspection against the `pkgs` instance of the
  selected NixOS configuration;
- per-package explanations for missing attributes, unsupported platforms,
  broken packages, evaluator rejection, and unfree licenses;
- compatibility summary and smart filters in the graphical catalog, with
  fail-open behavior when the target cannot be inspected;
- curated compatible alternatives, companion-package suggestions, and
  recommendations matched to the target desktop, enabled features, form
  factor, GPU, virtualization support, or NixOS-WSL;
- explicit-confirmation recommendation cards: catalog guidance never changes
  the draft, saves configuration, or activates the system by itself.
- dedicated Services control center with 23 curated NixOS services across
  desktop, hardware, connectivity, security, virtualization, and maintenance;
- service-specific risk, runtime mode, network exposure, and NixOS/WSL
  suitability labels, backed by the evaluated effective value and definition
  provenance;
- separate managed, effective-enabled, and pending-change service summaries;
  service actions reuse the existing preview, validation, build, and activation
  safety boundaries instead of mutating the running system directly;
- dedicated Drivers page with six typed AMD, Intel, NVIDIA, gaming-graphics,
  and firmware profiles backed by evaluated configuration and read-only PCI
  context;
- fail-closed hardware guidance: unknown GPUs block vendor-specific profiles,
  hybrid GPUs require manual review, and NixOS-WSL blocks every physical driver
  profile because Windows owns the device driver;
- exact proposed/current option values, risk notes, profile filtering, and
  draft-only profile application through the existing build, test, switch, and
  rollback gates.

## [0.1.0-alpha.1] - 2026-08-21

First public alpha release.

### Included

- local Ukrainian graphical control center and dependency-free Python CLI;
- more than 130 curated NixOS/Home Manager packages, search tags, eight additive
  presets, and portable versioned profile import/export;
- typed NixOS settings with effective-value and definition provenance;
- deterministic managed modules, exact diffs, disposable validation and build
  previews;
- opt-in sandboxed helper modes for read-only validation, bounded managed
  source persistence, timed test activation, tested-output switch and rollback;
- Home Manager discovery, preview, build and separately gated persistence;
- read-only generation history;
- `ncm --version` and the non-mutating `ncm doctor` installation diagnostic;
- x86_64 NixOS VM coverage for the complete safety-critical workflows.

### Alpha limitations

- only NixOS flake installation on x86_64 is the supported public alpha path;
- the GUI is a local browser application rather than a native desktop shell;
- automatic PRIME/hybrid-GPU setup, legacy GPU branch selection, Plasma
  Manager, and multi-host adaptation are not implemented;
- Home Manager activation remains intentionally unavailable;
- the Flakes page is inspection-only; input update previews and confirmed
  lock-file changes are not implemented yet;
- release updates, when implemented, will be explicit flake-input updates and
  will never run in the background.
