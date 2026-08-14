# Atomic apply and recovery protocol

This document specifies the future privileged write boundary. The journaled
transaction core and helper adapter are implemented only for explicitly marked
disposable fixtures. They have no CLI or HTTP endpoint and reject the standard
live NixOS and Home Manager roots; the current application still cannot apply
an adoption plan to the live system or activate a generation. The separate
local build-preview API can build the
same candidate as an unprivileged user into `/nix/store`, with no output link;
it grants no write or activation authority to this protocol.

## Implemented fixture transaction core

The test-only engine currently provides:

- an exact fixture marker and an additional hard refusal for paths shaped like
  `/etc/nixos`, `/etc/home-manager`, or the resolved default
  `~/.config/home-manager`;
- validation-fingerprint and candidate-digest matching;
- source digest checks before preparation and again immediately before every
  atomic replacement;
- an advisory process lock that is released by the operating system after a
  process crash;
- same-filesystem staged files, verified backups, and an fsynced JSON journal;
- reverse-order rollback after an injected partial failure;
- journal recovery after an injected process crash;
- a provisional `awaiting-verification` state followed by a second Nix
  evaluation of the installed fixture;
- no low-level path that can mark a provisional write `committed`; only the
  verification-aware finalize operation performs that transition;
- finalization only when post-commit evaluation proposes no additional files
  and all installed candidate digests still match;
- automatic rollback when post-commit Nix is unavailable or evaluation fails;
- `recovery-required` escalation instead of overwriting a file edited after the
  crash.

This is infrastructure for the future helper, not permission to connect it to a
live configuration.

The same core now supports a distinct `home-manager-adoption` journal kind for
both NixOS-module and standalone plans. It requires a successful full evaluation
in addition to parse checks, binds the exact root, user, integration, candidate
state, target and file digests into the fingerprint, and performs a second
evaluation after provisional commit. This path remains internal and
fixture-only; Home Manager user-state persistence is not part of the
transaction yet.

The fixture helper receives a short-lived UID-bound validation receipt through
the versioned Unix-socket protocol. It reconstructs the adoption plan from its
configured root, compares the entire submitted candidate set, and then invokes
this transaction core only after mock-Polkit authorization. The integration
suite also runs this path with real Nix evaluation on a temporary copy of
`/etc/nixos`.

## Safety invariants

- The GUI remains unprivileged and never receives or stores a sudo password.
- A helper accepts typed requests and an allow-list of paths and operations; it
  never accepts shell source or an arbitrary command line.
- Only files present in an approved adoption plan may be written.
- The helper verifies the SHA-256 digest of every source file immediately before
  writing. A concurrent edit aborts the whole operation.
- A successful disposable-candidate evaluation is required and is tied to the
  exact candidate content digests.
- Activation is a later, separate authorization. Applying files never implies
  `nixos-rebuild switch`.

## Transaction phases

1. **Plan** — record target root, relative paths, original digests, candidate
   digests, and the exact source diff.
2. **Validate** — materialize a private temporary copy, parse each changed Nix
   file, and evaluate the NixOS system derivation without building it.
3. **Authorize** — show the validated digest set and request one Polkit action
   scoped to writing those exact files.
4. **Prepare** — lock the NCM transaction directory, recheck original digests,
   create same-filesystem temporary files, flush them, and create recoverable
   backups of existing targets. Implemented for fixtures.
5. **Commit** — replace files atomically one at a time and flush their parent
   directories. Update a journal after every replacement. Implemented for
   fixtures.
6. **Verify** — while the journal is `awaiting-verification`, copy the installed
   fixture and rerun evaluation without proposing any additional changes. No
   activation is performed. Implemented for fixtures.
7. **Finish** — recheck installed candidate digests, mark the journal committed,
   and retain the manifest and backups according to the recovery policy.
   Implemented for fixtures.

## Failure and recovery

- Failure before commit removes temporary files and leaves the target untouched.
- Failure during commit restores already replaced files from the journal in
  reverse order. Newly created files are removed only when their recorded
  original state was “absent”.
- Failure after commit but before verification leaves an explicit
  `awaiting-verification` journal; the next launch restores it before any new
  operation.
- Backups are never inferred by filename scanning. Recovery uses only the
  transaction manifest and verifies backup digests before restoration.
- A symbolic link in the target path, journal root, fixture marker, or journal
  entry is rejected rather than followed.

## Git-backed flakes

The write transaction does not run a broad `git add`. If evaluation requires new
flake files to be visible, a separate unprivileged step may stage only the exact
NCM-owned relative paths displayed in the approved plan. Existing index entries
must be preserved, and no commit or push is automatic.

## Activation boundary

The local unprivileged `build` and closure preview are distinct from the
Polkit-authorized, exact-path `dry-activate` report. Experimental live-test mode
adds a separate receipt-bound `test` operation. It writes only a root-only
activation journal, arms automatic runtime recovery before activation, and
leaves the system profile and boot generation unchanged. File adoption and
permanent `switch` stay disabled. The dry report is incomplete, and timer
recovery is not a substitute for console access or a bootable prior generation.
