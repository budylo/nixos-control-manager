# Changelog

All notable user-visible changes are documented here. Versions use the public
release name; Python packaging may normalize prereleases to PEP 440 spelling.

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
- driver workflows, service-focused UI, Plasma Manager and multi-host
  adaptation are not implemented;
- Home Manager activation remains intentionally unavailable;
- release updates are explicit flake-input updates and never run in the
  background.
