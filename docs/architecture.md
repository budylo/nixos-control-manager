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
6. **Fixture transaction engine** exercises locking, atomic replacement,
   journaling, rollback, and crash recovery only in marked temporary roots. It
   rejects `/etc/nixos` and is not exposed by the CLI or server.
7. **Helper protocol and test service** implement versioned typed operations,
   exact target/path allow-lists, UID-bound one-time validation receipts, mock
   Polkit authorization, and Linux `SO_PEERCRED`. A fixture-only backend rebuilds
   the plan locally and connects the protocol to the complete transaction
   workflow. A separate live-read-only backend validates an exact `/etc/nixos`
   adoption plan in a disposable copy and cannot issue a write receipt. A
   recording backend remains available for zero-write protocol tests.
8. **System helper scaffold** provides an opt-in NixOS module, systemd-owned
   socket, strict service sandbox, and a real fail-closed `pkcheck` authorizer.
   It routes explicitly marked fixtures to the transaction backend and
   `/etc/nixos` to a capability-reduced read-only backend. The module is not
   installed by default and never accepts arbitrary shell commands.
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

## Privilege boundary

The GUI remains unprivileged. The planned helper will:

- use Polkit for interactive authorization;
- write only configured Nix Control Manager paths;
- invoke only an allow-list of rebuild/activation operations;
- never accept a command line to evaluate through a shell;
- never store a sudo password.

The current test boundary and wire format are documented in
[helper-protocol.md](helper-protocol.md). Its Polkit policy is a template and is
installed only when the opt-in NixOS module is explicitly enabled. Deployment
and sandbox details are in [system-helper.md](system-helper.md).
