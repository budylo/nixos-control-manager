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
- apply the approved plan atomically (transaction engine implemented for marked
  fixtures; privileged live apply remains disabled);
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
- live-target helper (read-only validation implemented; Polkit-backed writes
  remain unimplemented);
- opt-in exact-output `test` activation with a UID-bound receipt, root-only
  journal, timer-first automatic runtime recovery, and separate manual recovery
  (implemented experimentally; permanent `switch` remains disabled);
- green end-to-end recovery regression in a disposable NixOS VM, including
  receipt replay rejection, unchanged profile/source proofs, and timer-driven
  restoration of the previous runtime closure (implemented and part of flake
  checks), with TTY, manual, power-loss, and failed-recovery operator guidance
  (implemented);
- `switch`, generation history, and boot-generation rollback.

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
  canonical per-root path (implemented; live writes remain disabled);
- deterministic per-user Home Manager module and diff preview, restricted to
  an exactly detected user/integration and with all writes disabled
  (implemented);
- read-only, integration-specific source adoption plans with exact diffs and
  disposable parse/evaluation (implemented; live apply remains disabled);
- atomic Home Manager module/import persistence with fingerprint, journal,
  post-commit evaluation, rollback, and crash recovery (implemented only for
  explicitly marked disposable fixtures; typed diagnostic helper path
  implemented, with no HTTP/GUI/live endpoint);
- separate Home Manager fixture validation/apply/recovery operations, UID-bound
  single-use receipts, exact allow-lists, and Polkit actions (implemented);
- atomic canonical user-state persistence in the same marked-fixture
  transaction as modules/imports (implemented; legacy source remains read-only);
- Home Manager live managed-module and user-state persistence (not implemented);
- user/system package scope (separate catalog selection and preview implemented;
  persistence remains);
- profiles and reusable presets.

## Later

- safe flake input management;
- driver workflows with hardware-aware warnings;
- Plasma Manager;
- native desktop shell;
- import/export and multi-host configuration.
