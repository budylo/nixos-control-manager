# Architecture

## Product invariant

Nix Control Manager owns only its state file and generated Nix module. It must
not parse and rewrite arbitrary user-authored Nix expressions. A configuration
adoption flow will add one explicit import after showing the exact diff.

The generated module remains usable without Nix Control Manager.

## Components

1. **Core model** validates versioned state and normalizes package and option
   paths.
2. **Generator** renders deterministic, human-readable Nix. It has no file or
   process side effects.
3. **Storage** performs atomic writes and creates a recoverable backup.
4. **CLI** exposes initialization, preview, generation, and the local UI.
5. **Local UI server** exposes only fixed API operations and fixed state/output
   paths selected when the process starts. It binds to loopback. Its typed
   helper adapter accepts only protocol-v1 live targets that explicitly report
   read-only, apply-disabled, recovery-disabled, activation-disabled, and no
   arbitrary commands.
6. **Transaction engine** exercises locking, atomic replacement, journaling,
   rollback, and crash recovery. NixOS adoption entrypoints remain restricted
   to marked fixtures; Home Manager has distinct fixture and configured-live
   entrypoints with the safety mode recorded in every manifest.
7. **Helper protocol and test service** implement versioned typed operations,
   exact target/path allow-lists, UID-bound one-time validation receipts, mock
   Polkit authorization, and Linux `SO_PEERCRED`. The transaction backend
   rebuilds fixture plans and explicit live Home Manager plans locally. A
   separate live-read-only backend validates an exact `/etc/nixos`
   adoption plan in a disposable copy and cannot issue a write receipt. A
   recording backend remains available for zero-write protocol tests.
8. **System helper scaffold** provides an opt-in NixOS module, systemd-owned
   socket, strict service sandbox, and a real fail-closed `pkcheck` authorizer.
   It routes explicitly marked fixtures and opt-in live Home Manager source
   plans to the transaction backend, while ordinary `/etc/nixos` targets use a
   capability-reduced read-only backend. The module is not installed by default
   and never accepts arbitrary shell commands.
9. **Candidate build manager** owns at most one asynchronous job, materializes
   the exact adoption plan in a temporary directory, invokes one fixed
   channel/flake build argument vector without a shell, streams bounded logs,
   handles timeout/cancellation, and removes the working copy before reporting
   completion. It rejects effective UID 0 and exposes no activation operation.
10. **Activation-impact preview** first runs a fixed unprivileged closure diff.
    Its optional system-level report is a separate typed helper operation with
    its own Polkit action. The helper reconstructs the exact candidate, resolves
    its derivation output, matches the submitted store path, and invokes only
    `switch-to-configuration dry-activate` inside the no-write live sandbox.
11. **Time-limited test activation** is available only in an explicit live-test
    target. A dry-preview-issued one-time receipt binds UID, fingerprint, and
    exact output. The helper journals the prior profile closure and arms a
    systemd recovery timer before invoking only `switch-to-configuration test`.
    Permanent `switch` and configuration writes remain unavailable.
12. **Home Manager inspector** performs a bounded static scan of selected NixOS
    and standalone configuration roots. It identifies known integration forms,
    statically named users, and the status of a separate versioned user-state.
    Its API explicitly advertises that writes and activation are disabled.
13. **Home Manager preview generator** projects catalog package selections for
    one exactly detected user/integration pair. It preserves unrelated profiles
    and existing user options, renders a portable Home Manager module, and
    computes a unified diff against a fixed per-user path without writing it.
14. **Home Manager connection planner** creates integration-specific candidate
    imports. NixOS-module mode uses an isolated NixOS wiring module that extends
    `home-manager.users.<name>.imports`; standalone mode adds one import to a
    conservative `home.nix` module body. A validator materializes the plan only
    in a disposable copy, parses every changed Nix file, and evaluates an
    available NixOS or standalone-flake derivation without building it.
15. **Home Manager candidate build manager** independently reconstructs the
    selected plan, repeats disposable validation, and requires the exact
    client-supplied SHA-256 plan fingerprint. It then builds only the fixed
    standalone or NixOS-module `activationPackage` target without a result link
    or lock-file update. The worker streams bounded logs, supports cancellation
    and timeout, rejects effective UID 0, and never invokes activation.
16. **Home Manager transaction workflow** reuses the shared atomic
    replacement, journal, rollback, and crash-recovery engine under a distinct
    transaction kind. It accepts only a marked disposable root, a matching
    validation fingerprint and digest set, and a successful evaluation check.
    The exact file set includes canonical `ncm/user-state.json`. After
    provisional commit it reconstructs a no-changes plan and evaluates the
    installed root before finalization. It is available to marked fixtures and
    the explicitly configured `live-home-manager` root.
17. **Home Manager UI persistence boundary** holds helper receipts only in
    server memory behind opaque, expiring, single-use intent IDs. The browser
    receives the exact fingerprint but not the receipt, requires a separate
    confirmation checkbox, and submits only that intent and fingerprint. The
    server consumes the intent before asking the helper to invoke the dedicated
    Polkit action. All responses require activation and switching to remain
    false.

The read-only system inspector identifies NixOS, channel/flake entrypoints, an
existing managed-module import, and state compatibility. Detection is
conservative and never grants permission to adopt or rewrite a configuration.
Legacy state normalization is preview-first and reports skipped or ignored data.

## Apply pipeline

```text
UI state
  -> validate
  -> render candidate module
  -> show source diff
  -> copy configuration to a disposable workspace
  -> parse changed Nix files
  -> evaluate the candidate system derivation without building
  -> discard the workspace
  -> optionally materialize a fresh disposable copy and build without privilege (implemented)
  -> stream logs and allow cancellation (implemented)
  -> discard the build workspace; retain only normal Nix-store outputs
  -> compare candidate closure with /run/current-system without privilege (implemented)
  -> optionally authorize an exact, sandboxed dry-activation report (implemented)
  -> authorize and save atomically (fixture helper path implemented)
  -> mark the transaction awaiting-verification
  -> evaluate an unchanged copy of the installed files (fixture workflow implemented)
  -> finalize or roll back (fixture workflow implemented)
  -> show activation impact (closure and incomplete dry report implemented)
  -> optional receipt-bound test with timer-first runtime recovery (implemented)
  -> permanent switch (not implemented)
  -> record boot generation and result (not implemented)
```

`test` is the recommended first activation and is implemented as an
experimental runtime-only operation. `switch` and boot-generation rollback will
be separate future operations.

Candidate validation is implemented and never writes to the target root. The
live privileged write transaction remains disabled. Its digest, journaling, rollback,
and Git-flake rules are specified in [apply-protocol.md](apply-protocol.md). A
successful result includes candidate SHA-256 values and a stable plan
fingerprint for the future authorization boundary.

The adoption drawer offers two visibly separate validation paths. Local
validation invokes the unprivileged disposable-copy evaluator directly. System
validation sends the exact plan through the Unix helper and displays its
checks, but the HTTP adapter rejects protocol/version mismatches, unexpected
fingerprints, writable capabilities, and any validation receipt.

After successful validation, the same drawer may start the candidate build
manager. The token-protected HTTP API starts, polls, and cancels only typed job
IDs. The browser resumes the latest job by cursor after reload. The server caps
retained events and line length, never accepts a command from the client, and
publishes explicit false flags for configuration writes, activation, `test`,
and `switch`.

The dry report does not grant activation authority. Its request carries the
complete typed candidate set, plan fingerprint, and one top-level Nix store
path—not a command line. The backend re-evaluates the exact plan and resolves
the derivation output before invoking the fixed entrypoint. It snapshots the
configuration tree and `/run/current-system` before and after. NixOS itself
states that dry-activation changes may be incomplete, and the UI preserves
that warning.

The fixture apply workflow joins these pieces into
`validate -> provisional commit -> validate installed copy -> finalize/rollback`.
An interruption before finalize is treated as an incomplete transaction and is
rolled back by journal recovery.

## Configuration ownership

Options have three conceptual states:

- unmanaged/inherited;
- managed by Nix Control Manager;
- shared with another module (which may or may not be a conflict).

The GUI queries evaluated catalog values, definition locations, and declaration
locations through a fixed read-only Nix expression. It labels definitions from
the generated NCM module as managed, definitions from other modules as
inherited, and a mixture as shared. A shared source is not automatically called
a conflict. The evaluator reads `highestPrio` and active
`definitionsWithLocations` after Nix has applied `mkOverride` filtering. Lower
numeric priorities are stronger. The GUI can therefore explain list
concatenation, repeated equal scalar values, and differing active scalar values,
but does not claim visibility into weaker definitions that Nix has already
discarded. An evaluation failure with differing active scalar values is marked
as a conflict; other failures remain conservatively labelled as evaluation
errors. The GUI must not silently use `lib.mkForce`. List options such as
`environment.systemPackages` normally merge, while scalar options can conflict.

Catalog dependency rules are evaluated against the projected managed state
first and the read-only effective state second. Known contradictions block
preview and save, while an unavailable effective parent remains an explicit
unknown instead of being guessed. A repair action may add the typed parent value
only after the user selects it. The Python state model separately rejects
contradictions where both sides are already owned by NCM.

## State and generated source

The JSON state is versioned and convenient for the UI. The generated `.nix`
file is the portable configuration consumed by NixOS. Both can be committed to
the user's configuration repository. A header marks generated files and warns
against direct editing.

System state and Home Manager user-state are different ownership domains. The
system schema drives `managed.nix`; user-state schema version 1 contains a map
of user profiles, each with an explicit `nixos-module` or `standalone`
integration, package attribute paths, and typed option values. The latter is
stored canonically as `ncm/user-state.json` in the selected configuration root.
A token-protected HTTP request may carry one package candidate, but its preview
response remains read-only. A separate fingerprint-bound workflow may validate
the resulting adoption plan in a disposable copy and build its fixed
`activationPackage` into `/nix/store`; no live storage call, source adoption,
flake-input edit, or Home Manager activation path is connected to it.

The generated user source has the portable Home Manager module shape
`{ pkgs, ... }: { home.packages = [ ... ]; }`. It deliberately does not encode
the NixOS-module or standalone wiring, so a later adoption plan can show the
appropriate import separately. The output path is derived from the validated
user name and canonical state directory inside the selected root; clients
cannot submit a path.

Home Manager adoption plans expose `safeToValidate`, never `safeToApply`.
Existing files under the future `ncm/` directory must carry the generated NCM
header before they can appear as modification candidates. Entry-point editing
accepts only a simple multiline imports block, plus the standard standalone
module body when a new imports block is required. All other shapes stop for
manual review. Candidate paths are reconstructed beneath the selected root and
checked for symlinks before temporary materialization.

The Home Manager build-preview API is a separate ownership domain from the
NixOS system build. A request contains the detected user, integration, package
selection, and the exact fingerprint returned by validation. The worker
reconstructs and revalidates that plan before materializing a fresh disposable
copy. Its result deliberately sets configuration write, activation, test,
switch, flake-input mutation, and lock-file write capabilities to false; the
only expected mutation is ordinary unprivileged Nix store population.

The transaction workflow does not weaken that public contract. Fixture
writes require the exact transaction marker and reject `/etc/nixos`,
`/etc/home-manager`, and the resolved default `~/.config/home-manager`. The
journal is outside the configuration root and records
`transactionKind = "home-manager-adoption"`; the dedicated helper recovery
operation verifies that kind before restoring an interrupted provisional
commit. Its validation/apply receipt store and Polkit actions are separate from
system adoption. The legacy external state is never deleted or edited;
its compatible profiles are migration input only when canonical state is
missing them.

An explicit `live-home-manager` helper target reuses the exact-plan transaction
only after a second capability gate. Its Home Manager root and journal are
daemon configuration, not request fields; the system apply flag remains false.
The service mount namespace exposes only those two paths as writable, records
the live safety mode in every manifest, re-evaluates the installed sources, and
never invokes `home-manager switch` or another activation entrypoint.

An explicit `live-managed` target owns a still smaller system domain: the
canonical `ncm/state.json` and generated `ncm/packages.nix` pair. It reconstructs
their contents from typed state, uses a distinct receipt and Polkit action,
records `transactionKind = "managed-state"`, and repeats NixOS evaluation after
the provisional commit. The service may write only `/etc/nixos/ncm` and its
external journal; it cannot edit the operator-owned import, any flake file, the
system profile, or an activation entrypoint.

Home Manager detection does not evaluate arbitrary source and does not infer
dynamic attribute names. It recognizes a narrow set of documented static forms
and reports uncertainty instead of rewriting a configuration. This keeps the
future adoption decision separate from read-only discovery.

## Privilege boundary

The GUI remains unprivileged. The helper boundary:

- use Polkit for interactive authorization;
- write only configured Nix Control Manager paths;
- invoke only an allow-list of rebuild/activation operations;
- never accept a command line to evaluate through a shell;
- never store a sudo password.

The current test boundary and wire format are documented in
[helper-protocol.md](helper-protocol.md). Its Polkit policy is a template and is
installed only when the opt-in NixOS module is explicitly enabled. Deployment
and sandbox details are in [system-helper.md](system-helper.md).
