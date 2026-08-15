# Privileged helper protocol

Protocol version 1 is implemented with recording, fixture-workflow, and
live backends. The daemon configuration schema is version 5; this is
separate from the stable wire-protocol version. The service remains opt-in.

## Transport and identity

The transport uses one UTF-8 JSON request and response per Unix-socket
connection. Requests are capped at 2 MB. On Linux the helper obtains PID, UID,
and GID from `SO_PEERCRED`; a client-supplied identity is never accepted. Local
test sockets are mode `0600`. The opt-in system service adopts exactly one
systemd-owned socket descriptor; its socket is `0660` and group-restricted.

## Operations

- `capabilities` — read-only and unprivileged;
- `validate-plan` — accepts typed candidate files for one configured target and
  checks exact paths, digests, and locally reconstructed content. Fixture
  targets return a short-lived opaque receipt. Live-read-only targets never
  return a receipt;
- `apply-validated-plan` — accepts only target ID, plan fingerprint, and receipt;
  it cannot resubmit file content;
- `validate-home-manager-plan` — marked fixture or explicit
  `live-home-manager` targets only; accepts one detected user,
  an explicit integration, at most 500 typed package attribute paths, and the
  exact candidate files. The helper independently reconstructs and evaluates
  the same plan before issuing a workflow-specific receipt;
- `apply-validated-home-manager-plan` — accepts only the
  target, fingerprint, and Home Manager validation receipt;
- `recover-home-manager-transaction` — recovers one exact
  24-character transaction ID only when its journal kind is
  `home-manager-adoption`;
- `validate-managed-plan` — explicit `live-managed` targets only; accepts the
  canonical typed state plus exact candidates for `ncm/state.json` and/or
  `ncm/packages.nix`, then independently reconstructs and evaluates them;
- `apply-validated-managed-plan` — accepts only target, fingerprint, and the
  short-lived managed validation receipt;
- `recover-managed-transaction` — recovers one exact transaction ID only when
  its journal kind is `managed-state`;
- `preview-activation` — live modes only; accepts the same exact typed
  candidate set plus one top-level Nix store path, requires its own Polkit
  action, independently resolves the validated derivation output, and invokes
  only that closure's `switch-to-configuration dry-activate`;
- `test-activation` and `recover-test-activation` — explicit live-test mode
  only; consume a dry-preview receipt or one exact recovery session ID;
- `recover-transaction` — requests recovery of one 24-character transaction ID.

There is no operation for an arbitrary command, arbitrary absolute path,
rebuild mode, shell source, sudo password, `switch`, or permanent activation.
The opt-in test operation accepts only typed identity fields and a receipt. The
only accepted absolute payload is a strictly formatted top-level `/nix/store`
system path whose identity is independently proven by the helper.

## Request envelope

```json
{
  "schemaVersion": 1,
  "requestId": "request-0001",
  "operation": "apply-validated-plan",
  "payload": {
    "targetId": "system",
    "planFingerprint": "<lowercase SHA-256>",
    "validationReceipt": "<opaque receipt>"
  }
}
```

Unknown or missing fields are rejected. Candidate plans are limited to 16
files, 1 MB per file, valid UTF-8 without NUL, and exact relative paths from the
helper target's allow-list.

## Receipt binding

A receipt is stored inside the helper and binds:

- the complete validated candidate content;
- target ID and plan fingerprint;
- kernel-derived peer UID;
- expiration time;
- workflow kind; Home Manager receipts additionally bind user, integration, and
  the normalized package selection through the fingerprint and stored payload.

It is consumed before the apply backend is invoked and cannot be replayed.
A denied Polkit prompt does not consume it, allowing an intentional retry.

## Polkit actions

- `org.nixos.nix-control-manager.apply-validated-plan`;
- `org.nixos.nix-control-manager.recover-transaction`;
- `org.nixos.nix-control-manager.apply-validated-home-manager-plan`;
- `org.nixos.nix-control-manager.recover-home-manager-transaction`;
- `org.nixos.nix-control-manager.apply-validated-managed-plan`;
- `org.nixos.nix-control-manager.recover-managed-transaction`;
- `org.nixos.nix-control-manager.preview-activation`;
- `org.nixos.nix-control-manager.test-activation`;
- `org.nixos.nix-control-manager.recover-test-activation`.

The policy in `packaging/polkit` requires `auth_admin` for an active session and
denies inactive and unspecified sessions. Unit tests use a deterministic mock.
The system authorizer invokes `pkcheck` without a shell, using the peer's
`pid,start-time,uid`, and fails closed on missing process identity, unavailable
agent, dismissal, timeout, malformed details, or any nonzero result. The policy
is installed only when the NixOS module is explicitly enabled.

## Transaction backend boundary

The fixture backend independently rebuilds the local adoption plan and requires
the submitted fingerprint, digests, paths, actions, and complete candidate
content to match it exactly. It retains that prepared plan only for the receipt
owner. After authorization it runs provisional commit, installed-copy Nix
evaluation, and finalize/rollback through the journaled transaction engine.
Recovery is scoped to one exact transaction ID.

Home Manager fixture operations use a separate in-memory pending-plan store,
receipt namespace, apply action, and recovery action. A receipt issued by
`validate-plan` cannot authorize Home Manager apply, nor can a Home Manager
receipt authorize system adoption. The backend re-detects the exact user and
integration from the configured root, reconstructs canonical
`ncm/user-state.json` and all Nix candidates, and compares their complete
content before retaining the plan. Generic system recovery rejects a Home
Manager journal and vice versa.

The configuration root is helper-owned. For this fixture diagnostic path the
only legacy migration input is the fixed
`<configurationRoot>/user-state.local.json`; no request may submit a state path
or another standalone root.

Fixture targets require the exact fixture marker and still hard-refuse
`/etc/nixos`. The Linux integration script copies a real configuration into a
temporary directory, runs the protocol over a Unix socket with real Nix
evaluation, compares all source hashes, and removes the copy. Production
service sandboxing and real Polkit integration are implemented for fixtures.

Schema 4 adds one deliberately separate exception: `mode: "live-home-manager"`.
It keeps system `applyEnabled` and `recoveryEnabled` false while advertising
`homeManagerApplyEnabled` and `homeManagerLiveWriteEnabled`. Its configured
`homeManagerRoot` and external `homeManagerJournalRoot` are fixed at daemon
startup; neither comes from a wire request. The same exact-plan engine is used
with `fixtureOnly: false` recorded in the journal and result. System apply,
test/switch activation, arbitrary paths, and Home Manager activation remain
unavailable.

The local HTTP adapter does not relay `validationReceipt` to the browser. It
stores the receipt in memory with the helper TTL and returns an opaque intent
plus the exact plan fingerprint. Applying requires the token-protected endpoint,
an explicit boolean confirmation, the matching fingerprint, and consumption of
that one-time intent before the typed helper request is sent. This browser-side
protocol does not add any helper operation or authorization action.

A second Linux integration creates a standalone Home Manager fixture, carries
the exact three-file plan through a real Unix socket and kernel peer UID, and
performs both pre-commit and post-commit real Nix evaluations.

## Live-read-only backend boundary

A live target is configured with `mode: "live-read-only"`, `journalRoot: null`,
and `applyEnabled: false` internally. It independently reconstructs the plan
from `/etc/nixos`, requires an exact fingerprint/content match, materializes the
candidate only in a temporary directory, parses changed Nix, and evaluates the
candidate system derivation without building it.

After the unprivileged UI build, `preview-activation` repeats that exact match,
extracts the evaluated derivation path, queries its single output, and requires
it to equal the submitted store path. Only then does it run the fixed NixOS
dry-activation entrypoint as root. `/etc/nixos` remains read-only, the helper
has no writable persistent path or Linux capabilities, and before/after hashes
plus `/run/current-system` are compared. The response keeps
`activationEnabled`, `testEnabled`, and `switchEnabled` false and marks the
report incomplete.

Successful validation returns `readOnly: true` and `applyEnabled: false` but no
`validationReceipt`. Apply and recovery requests are rejected as
`operation-disabled` before receipt lookup, Polkit, or any backend write method.
Capabilities publish `liveTarget`, `readOnly`, `applyEnabled`, and
`recoveryEnabled` for every configured target, plus
`homeManagerFixtureEnabled` only for writable marked fixtures. Capabilities
publish the separate Home Manager apply/live-write flags. Ordinary live modes
return `operation-disabled` before receipt lookup, backend dispatch, or Polkit;
only `live-home-manager` enters the Home Manager transaction backend.

The booted NixOS VM check additionally exercises the installed policy, real
systemd socket activation, one denied user and one VM-authorized user, and the
complete committed fixture workflow. The diagnostic `ncm-helper-client` emits
only typed protocol requests; it has no arbitrary-command operation.

A separate booted VM check drives live validation through the unprivileged HTTP
UI and the socket-activated helper, then verifies the empty capability set,
read-only `/etc/nixos` mount, unchanged hashes, absent journal/receipt,
pre-Polkit rejection of apply/recovery, and a separately authorized real
dry-activation report for the exact built closure.

## Live-managed backend boundary

`mode: "live-managed"` is a separate capability domain. Its fixed allow-list is
`ncm/state.json` and `ncm/packages.nix`; it cannot reuse generic adoption or
Home Manager receipts, actions, journals, or recovery operations. The helper
regenerates both candidates from the typed state, validates them in a disposable
copy, and retains a UID-bound receipt only after an exact content and
fingerprint match.

Apply consumes the receipt before the backend runs, requires the dedicated
Polkit action, and writes through an external journal whose transaction kind is
`managed-state`. Installed content is regenerated, compared, and evaluated
again before finalization; failure rolls back. The service sandbox exposes only
`/etc/nixos/ncm` and the journal as writable. Activation, system/boot profiles,
main imports, flake inputs, arbitrary commands, and Home Manager remain outside
this mode.

## Live-test backend boundary

Protocol version 1 also defines `test-activation` and
`recover-test-activation`; neither accepts a command line. `mode: "live-test"`
is an explicit opt-in extension of the read-only target. It still has
`applyEnabled: false`, cannot write `/etc/nixos`, and exposes no `switch`. Only
a successful exact dry preview may create a short-lived, single-use test
receipt bound to UID, target, fingerprint, and store output.

Immediately before activation the backend revalidates the derivation/output.
It records the current system profile closure in a root-owned `0700` journal and
schedules automatic recovery before invoking only the candidate's
`switch-to-configuration test`. Unfinished sessions block another activation.
Recovery invokes only the recorded previous closure's equivalent `test`
entrypoint and verifies `/run/current-system`; a mismatch leaves
`recovery-required` instead of reporting success.

The system profile and boot generation are not changed. Runtime timers cannot
cover power loss or kernel panic and do not replace normal boot recovery.
