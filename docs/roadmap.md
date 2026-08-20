# Roadmap

## Milestone 1 — Safe generated module

- application catalog and search;
- package-only recipes limited to attributes that can be safely added to
  `environment.systemPackages` (applications such as Steam that require a
  dedicated NixOS option belong to the typed-options milestone);
- versioned state;
- deterministic Nix generation;
- diff preview and atomic save;
- local UI and CLI;
- unit tests.

## Milestone 2 — Adopt a NixOS configuration

- detect channel and flake configurations (implemented);
- select a `nixosConfigurations.<host>` target;
- show the one-time import/migration diff (implemented);
- apply an approved plan atomically (general adoption remains fixture-only;
  bounded persistence of the two NCM-owned system files is implemented through
  the explicit `live-managed` mode);
- handle Git flakes and optionally stage only files owned by the application;
- evaluate the candidate configuration in a disposable workspace (implemented);
- implement digest checks, journaling, rollback, and crash recovery (implemented
  and fault-tested on disposable fixtures; privileged apply remains disabled).
- re-evaluate installed fixture files before finalize and roll back on failure
  (implemented with real NixOS evaluation; privileged apply remains disabled).
- connect the helper protocol to that complete workflow and exercise it through
  a Unix socket on a copied real NixOS configuration (implemented; fixture-only).
- validate an exact live `/etc/nixos` plan through the Unix helper without a
  receipt or write/recovery authority, and prove source hashes remain unchanged
  (implemented; read-only).
- expose helper availability and live read-only validation in the graphical
  adoption drawer, including real-browser and HTTP-to-Unix integration checks
  (implemented; no apply control is exposed).
- boot the unprivileged graphical server with the real systemd live-read-only
  helper, run full NixOS evaluation, and prove the helper mount namespace cannot
  write `/etc/nixos` (implemented as an x86_64 flake VM check).

## Milestone 3 — Build and activation

- versioned helper protocol, exact allow-lists, UID-bound validation receipts,
  Linux peer credentials, mock Polkit policy, and fixture-workflow adapter
  (implemented; production service installation remains disabled);
- opt-in NixOS module, systemd socket activation, strict service sandbox, and
  real race-resistant `pkcheck` authorizer (implemented for fixture targets;
  not enabled on a machine);
- booted NixOS VM integration covering real socket activation, default Polkit
  denial, VM-scoped authorization, real Nix pre/post validation, commit, file
  permissions, and journal finalization (implemented and part of flake checks);
- unprivileged `build` preview in a disposable candidate copy, with fixed
  channel/flake commands, streamed bounded logs, cancellation, timeout, and no
  output link (implemented in the graphical adoption flow);
- offline VM proof that the real build leaves `/etc/nixos` and
  `/run/current-system` unchanged (implemented);
- unprivileged closure diff plus Polkit-authorized `dry-activate` report bound
  to the exact validated build output, with explicit incomplete-report warning
  and VM proof of unchanged source/current generation (implemented);
- live-target helper (read-only validation, exact NCM-owned state/module writes,
  and separate Home Manager writes implemented as distinct modes; general
  NixOS adoption remains unavailable);
- opt-in exact-output `test` activation with a UID-bound receipt, root-only
  journal, timer-first automatic runtime recovery, and separate manual recovery
  (implemented experimentally);
- green end-to-end recovery regression in a disposable NixOS VM, including
  receipt replay rejection, unchanged profile/source proofs, and timer-driven
  restoration of the previous runtime closure (implemented and part of flake
  checks), with TTY, manual, power-loss, and failed-recovery operator guidance
  (implemented);
- exact tested-output `switch`, read-only generation history, and journal-bound
  rollback to the immediately previous closure (implemented in the separate
  `live-control` mode); arbitrary generation selection and bootloader editing
  remain future work.

## Milestone 4 — Typed NixOS options

- curated first catalog with checked option paths, descriptions, NixOS types,
  defaults, suggestions, and impact labels (implemented for 32 options; dynamic
  nixpkgs metadata/provenance ingestion remains);
- render booleans, enums, strings, integers, and string/integer lists with
  browser and server validation (implemented); numbers beyond integers and
  attribute-set editors remain;
- display effective values and definition provenance (implemented for the
  catalog through read-only channels/flake evaluation, including active
  override priority, list merge, equal scalar, and conflict explanations);
- model typed dependencies between settings, resolve them against projected and
  inherited effective values, block known contradictions, and offer explicit
  one-click parent-setting repair without hidden mutations (implemented for
  PipeWire/PulseAudio, Bluetooth features, NetworkManager Wi-Fi backend,
  firewall TCP/UDP ports, and zram sizing);
- curated settings for common desktop, network, locale, sound, hardware,
  service, gaming, boot, maintenance, compatibility, and virtualization tasks
  (two vertical slices implemented).

## Milestone 5 — User configuration

- read-only discovery of Home Manager in NixOS-module and standalone modes,
  including statically identifiable users and source files (implemented);
- separate versioned user-state model with explicit integration per user and a
  canonical per-root path (implemented; live persistence requires the explicit
  helper mode);
- deterministic per-user Home Manager module and diff preview, restricted to
  an exactly detected user/integration and with all writes disabled
  (implemented);
- preview-first, integration-specific source adoption plans with exact diffs
  and disposable parse/evaluation (implemented; graphical live persistence is
  available only through the opt-in helper mode);
- fingerprint-bound, unprivileged build-preview for the exact Home Manager
  `activationPackage`, with streamed logs, cancellation, timeout, disposable
  cleanup, and no activation (implemented; legacy standalone remains unavailable);
- booted offline VM proof of the full Home Manager HTTP flow from detection and
  adoption planning through validation and a real Nix store build, including
  unchanged source, canonical state, result link, and user profile guarantees
  (implemented as part of the live read-only UI flake check);
- atomic Home Manager module/import persistence with fingerprint, journal,
  post-commit evaluation, rollback, and crash recovery (implemented for marked
  fixtures and the explicit `live-home-manager` helper mode, including the
  confirmation-gated local HTTP/GUI path);
- separate Home Manager fixture validation/apply/recovery operations, UID-bound
  single-use receipts, exact allow-lists, and Polkit actions (implemented);
- atomic canonical user-state persistence in the same marked-fixture
  transaction as modules/imports (implemented; legacy source remains read-only);
- Home Manager live managed-module and user-state persistence (implemented as
  an opt-in typed helper/CLI/UI vertical slice; activation remains
  unimplemented by design);
- user/system package scope (separate catalog selection and preview implemented;
  system persistence is available through `live-managed`; user persistence is
  available through `live-home-manager`);
- profiles and reusable presets.

## Later

- safe flake input management;
- driver workflows with hardware-aware warnings;
- Plasma Manager;
- native desktop shell;
- import/export and multi-host configuration.
