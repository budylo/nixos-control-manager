# Nix Control Manager

Nix Control Manager is an approachable graphical control center for NixOS. It
keeps the operating system declarative by generating a small, transparent NixOS
module instead of rewriting a user's configuration.

Source repository: https://github.com/budylo/nixos-control-manager

This repository currently contains the first vertical slice:

- a validated JSON state model;
- deterministic generation of `managed.nix`;
- a unified-diff preview;
- atomic writes with a backup of the previous generated module;
- a local, dependency-free web interface for selecting applications;
- a CLI and a Nix flake;
- a channel-compatible NixOS module entrypoint that builds the package from the
  same pinned source snapshot;
- an opt-in `programs.nix-control-manager` module that installs `ncm`, an
  on-demand read-only GUI user service, an idempotent `ncm-gui` lifecycle
  launcher, and a desktop entry without granting privileged write authority;
- a fault-tested journaled transaction engine restricted to marked disposable
  fixtures;
- a versioned helper protocol with exact path allow-lists, UID-bound one-time
  receipts, mock Polkit authorization, and a fixture-workflow backend;
- a real fail-closed `pkcheck` authorizer and an opt-in, sandboxed NixOS
  socket/service module with fixture, live-read-only, live-managed, live-test,
  live-control, and live-home-manager targets;
- direct `/etc/nixos` validation in a disposable copy, with no receipt, write,
  recovery, build, or activation authority for the live target.
- a separate opt-in `live-managed` path that can atomically persist only
  `ncm/state.json` and `ncm/packages.nix` after disposable validation, an exact
  diff, explicit confirmation, and Polkit authorization. It cannot change the
  main configuration, flake inputs, system profile, or active generation;
- a local UI adapter that detects the configured Unix helper, exposes its
  read-only capabilities, and can run the exact live validation plan from the
  adoption drawer;
- an unprivileged candidate-build preview with streamed logs, cancellation,
  timeout, and automatic removal of its disposable configuration copy. It may
  populate `/nix/store`, but cannot write `/etc/nixos`, activate, test, or
  switch a generation;
- an unprivileged closure diff plus a separately Polkit-authorized, sandboxed
  NixOS dry-activation report bound to the exact validated build output. The
  report is explicitly incomplete;
- an experimental opt-in, time-limited `test` activation for the exact verified
  output. A root-only journal is created and automatic recovery is armed before
  the fixed `switch-to-configuration test` entrypoint runs. It never selects
  `switch` or changes the boot profile.
- an explicit `live-control` mode that can permanently select only the exact
  closure that successfully completed the bound dry-preview and test flow. It
  journals the previous closure, changes the system profile without rebuilding,
  verifies runtime/profile convergence, and exposes an exact one-step rollback;
- a read-only generations page that distinguishes current, booted, and profile
  generations without accepting arbitrary paths or commands;
- a preview-first Home Manager inspector for both NixOS-module and standalone
  configurations, with conservative user discovery and a separate versioned
  user-state boundary. Writes require the separate opt-in helper mode; Home
  Manager activation remains disabled.
- a Home Manager package selector that renders a deterministic
  per-user module and unified diff while preserving existing user options. It
  has no flake-input or activation operation;
- a read-only Home Manager connection plan for conservative NixOS-module and
  standalone imports, plus disposable-copy parse/evaluation;
- an unprivileged Home Manager build-preview bound to the exact validation
  fingerprint. It builds only the selected user's `activationPackage`, streams
  logs, supports cancellation and timeout, and never writes configuration or
  runs activation / `home-manager switch`;
- a fault-tested Home Manager transaction workflow that can persist the exact
  validated module/import set and canonical `ncm/user-state.json` either in a
  marked fixture or in the separate opt-in `live-home-manager` target. Live
  writes require their own UID-bound receipt, Polkit action, root-only journal,
  allow-list, post-commit evaluation, rollback, and recovery. The GUI keeps the
  receipt server-side, requires an exact one-time confirmation, and then asks
  Polkit to persist only those sources. Every Home Manager activation operation
  remains absent.

## Try it

With Python 3.11 or newer:

```console
python -m nix_control_manager serve --open
```

When running directly from a checkout without installing the package:

```console
$env:PYTHONPATH = "src" # PowerShell
python -m nix_control_manager serve --open
```

On NixOS, from this repository:

```console
nix run . -- serve --open
```

Validate and build the pinned flake:

```console
nix flake check --no-build
nix build
```

The server listens only on `127.0.0.1`. By default it stores the system UI state
in `state.local.json`, inspects the separate `user-state.local.json`, and
generates `managed.local.nix` in the current directory. These local files are
ignored by Git. The external Home Manager state remains a read-only legacy
migration source; no live state file is created implicitly.

## CLI

```console
ncm init --state state.json
ncm preview --state state.json --output managed.nix
ncm generate --state state.json --output managed.nix
ncm detect --config-root /etc/nixos --json
ncm detect-home-manager --config-root /etc/nixos --json
ncm preview-home-manager --user alice --integration nixos-module --package firefox --json
ncm plan-home-manager-adoption --user alice --integration nixos-module --package firefox --json
ncm validate-home-manager-adoption --user alice --integration nixos-module --package firefox --json
ncm migrate-state --state /etc/nixos/ncm/state.json
ncm plan-adoption --config-root /etc/nixos
ncm validate-adoption --config-root /etc/nixos
ncm serve --state state.json --output managed.nix --open
ncm serve --state state.json --output managed.nix --read-only --open
ncm-helper-client capabilities
ncm-helper-client validate-home-manager-plan --target home-fixture --config-root ./fixture --user alice --integration standalone --package firefox
```

`detect-home-manager` performs a bounded static inspection of Nix files. It
recognizes `home-manager.nixosModules.home-manager`, legacy
`<home-manager/nixos>` imports, `home-manager.users.<name>`, flake
`homeConfigurations.<name>`, and a standalone `~/.config/home-manager`
configuration. Detection is deliberately conservative: dynamic user names may
require manual confirmation in a future adoption flow. The command and UI do
not add flake inputs, create or edit `home.nix`, write user-state, or activate a
Home Manager generation.

On NixOS, `ncm serve` looks for the helper at
`/run/nix-control-manager/helper.sock` and target `live`. Override these with
`--helper-socket`, `--helper-target`, `NCM_HELPER_SOCKET`, or
`NCM_HELPER_TARGET`. An absent or unsafe helper leaves the system-validation
button disabled; local disposable-copy validation remains available.

`ncm serve --read-only` disables `/api/save`, so the browser cannot persist the
local state or generated Nix module. Inspection, diff preview, disposable-copy
validation, unprivileged builds, and capability-gated helper reports remain
available. The NixOS `programs.nix-control-manager` launcher always selects
this mode; the installed helper independently determines which privileged
operations exist.

With `programs.nix-control-manager.enable = true`, `ncm-gui` manages one
on-demand `nix-control-manager-gui.service` instance per logged-in user. The
service is not enabled at login. Repeated desktop launches reuse the healthy
server after verifying the application name, API version, and read-only flag:

```console
ncm-gui --no-open  # start or reuse, but only print the URL
ncm-gui --status
ncm-gui --open     # start or reuse and ask the desktop to open the URL
ncm-gui --stop
journalctl --user -u nix-control-manager-gui.service
```

The server receives `SIGINT` on stop so that its HTTP socket is closed through
the normal shutdown path. A process on the configured port that does not expose
the expected NCM identity is rejected rather than reused.

`detect` is read-only. `migrate-state` also defaults to a JSON preview and does
not change its input. Pass `--output <path>` explicitly to write normalized
state; an existing output receives a `.bak` backup.

`plan-adoption` produces exact file operations and unified diffs. It is also
read-only: the live-target helper deliberately exposes no adoption-write
authority.

`validate-adoption` copies the target configuration to a disposable workspace,
applies the planned candidates there, parses changed Nix files, and evaluates
the system derivation. It does not build, activate, or write to the target. For
a flake whose host key differs from the machine hostname, pass
`--flake-target <name>`.

After a successful validation, the adoption drawer can start a **Build
preview**. Channels use a fixed `nix-build ... --no-out-link` argument vector;
flakes use a fixed `nix build ... --no-link --no-write-lock-file` vector. Logs
are streamed to the drawer and the job can be cancelled. The build runs without
`sudo` in a disposable configuration copy and refuses effective UID 0. Nix is
still expected to write build outputs to `/nix/store`; the active system and
source configuration remain untouched.

The completed build is also compared with `/run/current-system` through the
fixed unprivileged `nix store diff-closures` command. If the opt-in live helper
advertises `dryActivatePreviewEnabled`, a separate button asks Polkit to run
only `<verified-system>/bin/switch-to-configuration dry-activate`. The helper
independently reconstructs the candidate, resolves its derivation output, and
requires that exact store path before execution. NixOS documents dry-activation
output as potentially incomplete, so it is guidance rather than a proof that a
future activation will succeed.

With an explicitly configured `mode = "live-test"`, a successful dry preview
also issues a short-lived, single-use test receipt bound to the peer UID, plan
fingerprint, and exact output. The helper records the current system profile and
arms a systemd recovery timer before test activation. Manual recovery has a
separate Polkit action. This remains runtime-only: `/etc/nixos`, `switch`, and
the boot generation are untouched. Timer recovery cannot cover power loss or a
kernel panic, so console access and a bootable previous generation remain
necessary safeguards.

The separate `mode = "live-control"` extends that same receipt-bound flow with
an explicitly confirmed permanent switch. It never rebuilds during commit:
the helper sets the system profile to the already tested exact closure, runs
that closure's fixed `switch` entrypoint, and verifies both links. The previous
closure remains journaled for the dedicated rollback operation. See
[`docs/live-control.md`](docs/live-control.md).

Operational preparation, immediate recovery, TTY diagnostics, and power-loss
handling are documented in
[`docs/live-test-recovery.md`](docs/live-test-recovery.md).

`generate` validates the complete state before writing. An existing output is
copied to `managed.nix.bak`, then the new file is atomically moved into place.

## Safety boundary

The current milestone intentionally does **not** collect sudo passwords, accept
shell commands, run a client-selected `nixos-rebuild`, or apply a general NixOS
system-adoption plan.
Default live-read-only mode stops at dry preview. Separate
experimental live-test mode can select only `test` after a bound receipt and a
pre-armed recovery timer; it never creates a boot generation or `result` link.
Only the separate `live-control` mode can select `switch`, and only for the
exact closure already validated and tested in the same UID-bound session. Its
rollback target also comes solely from the root-owned journal.
The transaction and recovery boundary is specified in
[`docs/apply-protocol.md`](docs/apply-protocol.md). Those capabilities remain
restricted to disposable fixtures for NixOS system adoption. The dedicated
`live-home-manager` mode can persist only the exact validated Home Manager
source plan; system apply and all permanent activation authority remain false.
The separate `live-managed` mode can persist only the canonical NCM-owned
`ncm/state.json` and `ncm/packages.nix` pair. Its receipt, Polkit actions,
journal kind, and recovery operation are separate, and it never edits an import
or activates the result. See [`docs/live-managed.md`](docs/live-managed.md).

The diagnostic CLI can also exercise explicitly configured live Home Manager
persistence. This is not a generic live transaction engine: daemon schema 5
must name the Home Manager root and external journal, the NixOS module exposes
only those paths to the service, and the submitted files must match both the
locally reconstructed plan and the exact allow-list. The service sandbox keeps
home directories unavailable in this first deployment slice. The local HTTP/UI
flow exposes only exact helper validation and a one-time confirmed apply intent;
the helper receipt is never returned to browser JavaScript.

The fixture workflow also performs a second NixOS evaluation after provisional
commit. The journal reaches `committed` only when that installed snapshot needs
no further generated changes and still matches every candidate digest;
otherwise the transaction is rolled back.

The same journal engine now has a separate Home Manager transaction kind. It
requires a fingerprint-bound validation with a successful evaluation check,
commits only the exact planned NixOS-module or standalone files, including
canonical `ncm/user-state.json`, reconstructs a no-changes plan from the
installed root, and evaluates it again before finalization. The state file
participates in the same fingerprint, commit, and rollback as the Nix files;
neither commit nor recovery activates a Home Manager generation.

The helper exposes Home Manager transactions through distinct
`validate-home-manager-plan`, `apply-validated-home-manager-plan`, and
`recover-home-manager-transaction` operations. Their receipts and Polkit
actions cannot be reused by the NixOS adoption workflow. The helper reconstructs
the plan locally and enforces its exact path allow-list. Ordinary live-read-only
and live-test targets reject all three write operations; only an explicit
`live-home-manager` target may issue the dedicated receipt.

The helper protocol is documented in
[`docs/helper-protocol.md`](docs/helper-protocol.md). Its Unix transport and
fixture backend now exercise the complete validate/authorize/apply/verify path.
Unit tests use a deterministic Polkit mock; the production-shaped authorizer
uses `pkcheck` and fails closed. The NixOS module, helper service, and policy are
not installed on the current system.

The opt-in deployment scaffold and sandbox are described in
[`docs/system-helper.md`](docs/system-helper.md).

The first non-mutating run against the real NixOS-WSL host, including its
before/after hashes and the next channel-compatible deployment boundary, is
recorded in
[`docs/wsl-read-only-rehearsal.md`](docs/wsl-read-only-rehearsal.md).

The subsequent pinned `live-read-only` WSL deployment, verified capability
denials, backup, and rollback procedure are recorded in
[`docs/wsl-live-read-only-deployment.md`](docs/wsl-live-read-only-deployment.md).

The successor pinned `live-managed` WSL deployment, exact two-file capability,
source-integrity proof, backup, and rollback procedure are recorded in
[`docs/wsl-live-managed-deployment.md`](docs/wsl-live-managed-deployment.md).

An x86_64 NixOS VM integration test boots a disposable guest, starts the real
socket-activated root helper, verifies both denied and explicitly authorized
Polkit paths, and completes the real-Nix fixture transaction. It is included in
`nix flake check` as `checks.x86_64-linux.helper-vm` and is also available as
`packages.x86_64-linux.helper-vm-test`.

A second booted VM runs the unprivileged graphical server against an actual
systemd `live-read-only` helper and disposable VM-only `/etc/nixos`. It performs
the full HTTP-to-Unix validation, verifies the helper mount namespace cannot
write `/etc/nixos`, performs a real offline candidate build into the VM's Nix
store, checks streamed output and cleanup, and exercises Home Manager detection,
adoption planning, validation, and a real fingerprint-bound `activationPackage`
build through the HTTP API. It proves both configuration trees, canonical state,
the Home Manager profile, and the active system generation remain unchanged;
apply and recovery also stop before Polkit. It then authorizes the distinct
system dry-preview action, checks the exact store-path binding, and captures
systemd impact. The test is exposed as
`checks.x86_64-linux.live-read-only-ui-vm` and
`packages.x86_64-linux.live-read-only-ui-vm-test`.

A third disposable VM exercises the explicitly opted-in `live-test` boundary
end to end. It obtains a UID-bound single-use preview receipt, performs only the
candidate closure's `test` activation, verifies that the system profile and
configuration sources stay unchanged, rejects receipt replay, and observes the
pre-armed systemd timer restore the previous runtime closure. The root-only
recovery journal must finish in `recovered` state. This regression is exposed as
`checks.x86_64-linux.live-test-recovery-vm` and
`packages.x86_64-linux.live-test-recovery-vm-test`.

A fourth disposable VM exercises `live-home-manager`: it proves default Polkit
denial leaves `/etc/nixos` unchanged, authorizes one exact source plan, performs
real pre/post Nix evaluation, commits the root-only live journal, and verifies
that `/run/current-system` never changes. It is exposed as
`checks.x86_64-linux.live-home-manager-vm` and
`packages.x86_64-linux.live-home-manager-vm-test`. Deployment details are in
[`docs/live-home-manager.md`](docs/live-home-manager.md).

A fifth disposable VM exercises `live-managed`: it denies the unprivileged
write path by default, authorizes one exact two-file transaction, performs real
NixOS evaluation before and after commit, and proves the main configuration and
active generation are unchanged. It is exposed as
`checks.x86_64-linux.live-managed-vm` and
`packages.x86_64-linux.live-managed-vm-test`. Deployment and recovery details
are in [`docs/live-managed.md`](docs/live-managed.md).

## Typed system settings

The graphical interface now includes a typed NixOS settings catalog. Thirty-two
curated options cover locale and time, Plasma/SDDM, sound, Bluetooth, power and
zram, NetworkManager, TCP/UDP firewall ports, SSH, Tailscale, printing,
Flatpak, Steam, Docker/libvirt, firmware and SSD maintenance, Nix garbage
collection, nix-ld compatibility, and the boot menu timeout. Boolean, enum,
string, integer, and list editors expose the exact option path, NixOS type,
curated default, and impact level.

Settings are opt-in individually: an untouched catalog default is not emitted.
Known values are validated independently in the browser and Python model;
invalid input disables preview and save. Existing options outside the current
catalog remain preserved and visible read-only instead of being silently
discarded. `checks.<system>.settings-options` also evaluates every catalog path
and default against the pinned nixpkgs NixOS module system.

The settings page evaluates the selected live `configuration.nix` or flake
target in read-only mode and shows the effective value plus every contributing
definition file. This inspection never builds or activates a system and never
writes a lock file. If Nix is unavailable or the current configuration cannot
evaluate, the editor remains usable but labels the live value as unavailable.
When management is enabled for an option, a compatible live value is adopted as
the initial proposal to avoid an accidental change.

Catalog entries can declare typed dependencies on other settings. Dependency
analysis uses the projected managed values first and then the effective
read-only system values. A known contradiction blocks preview and save; an
unavailable effective value is reported as a warning without inventing a
result. NCM never changes the required parent option silently: the interface
offers an explicit repair action that adds the parent setting with the required
typed value. The Python model independently rejects contradictions that are
fully present in the managed state.

For each active definition the interface also reports the Nix override priority
and its value. Lower numeric priorities win in the Nix module system. List
options are labelled as concatenated, repeated equal scalar definitions are
distinguished from conflicts, and `mkForce`-strength priorities receive a
warning. Only definitions that remain active after Nix override filtering are
shown; discarded weaker definitions are intentionally not presented as if they
were still contributing. Options whose current scalar definitions conflict or
cannot evaluate require manual review before NCM can start managing them.

## Home Manager foundation

The Home Manager page reports whether the existing configuration uses the
NixOS module, standalone mode, or both, and lists only users that can be
identified safely from static source. It also reports whether a separate
version-1 user-state is missing, readable, or invalid.

For an exactly detected user/integration pair, the graphical catalog can now
project package choices in memory and request a token-protected preview. The
server preserves unrelated profiles and existing options, validates the entire
candidate user-state, then renders an integration-agnostic module containing
`home.packages`. Its fixed future name is `managed-home-<user>.nix`, but the
preview only reads that path to build a diff and never creates or changes it.

The connection-plan drawer shows how this module would be wired. In
NixOS-module mode NCM proposes a separate `ncm/home-manager-<user>.nix` module
that extends `home-manager.users.<user>.imports`, followed by one conservative
top-level import. In standalone mode it proposes one import from a standard
`home.nix`. Existing non-NCM files are never replaced, and unfamiliar or inline
module layouts stop at manual review.

The same exact plan includes a deterministic `ncm/user-state.json` beside the
managed modules. If the canonical file is absent, compatible profiles from the
legacy external `user-state.local.json` are copied into the candidate while the
legacy source remains untouched. A valid canonical file is authoritative;
conflicting canonical files across separate roots fail closed.

Validation copies the selected configuration root to a temporary directory,
materializes the exact candidates there, parses every changed Nix file, and
evaluates the NixOS system or standalone flake derivation when the corresponding
entrypoint is available. Legacy standalone configurations receive syntax-only
validation. The temporary directory is removed afterwards; activation, source
writes, lock-file writes, and flake-input changes remain disabled.

After successful validation, the drawer can start a separate unprivileged
build-preview for the same fingerprint. Flake integrations build the exact
standalone or NixOS-module `activationPackage`; legacy standalone configurations
remain unavailable because they do not expose a fixed safe build target. The
build may populate `/nix/store`, but it never executes the result and removes
its disposable source copy on success, failure, cancellation, or timeout.

When the configured target explicitly advertises `live-home-manager`, the same
drawer adds a persistence step after disposable validation. The server and
helper independently reconstruct the displayed plan and compare its complete
fingerprint. A short-lived UID-bound receipt stays in server memory behind an
opaque, single-use intent. The browser displays the fingerprint, requires a
separate confirmation checkbox, and only then triggers the dedicated Polkit
action. A successful response means the atomic transaction and post-commit
evaluation both reached `committed`; it does not mean activation ran.

System and user ownership remain intentionally separate. System packages and
NixOS options continue to live in `state.local.json` and `managed.local.nix`;
per-user Home Manager packages and options belong to the selected configuration
root's `ncm/user-state.json` and distinct generated user modules. The opt-in
helper can commit them atomically through the confirmed live source-writing
flow. The application still has no Home Manager activation or flake-input
mutation operation.

See [docs/architecture.md](docs/architecture.md) and
[docs/roadmap.md](docs/roadmap.md).

## Development checks

```console
PYTHONPATH=src python -m unittest discover -s tests -v
python -m compileall -q src tests
node --check src/nix_control_manager/web/app.js
```

On Linux, a manual integration check copies `/etc/nixos` to a temporary fixture,
runs the complete helper protocol with real Nix evaluation, verifies source
hashes, and deletes the fixture:

```console
PYTHONPATH=src python tests/integration_fixture_helper_real_nix.py /etc/nixos
```

The live-read-only integration instead targets `/etc/nixos` directly, validates
only in a disposable copy, proves that no receipt was issued, rejects apply and
recovery before Polkit, and compares every source-file hash:

```console
PYTHONPATH=src python tests/integration_live_read_only_helper.py /etc/nixos
```

The complete graphical API path can also be checked end to end:

```console
PYTHONPATH=src python tests/integration_live_read_only_ui.py /etc/nixos
```

This runs `local HTTP API -> typed UI adapter -> Unix helper -> real Nix`,
requires the per-launch UI token, and confirms that no receipt or Polkit call
was produced.

The real candidate-build integration must be run as a normal user. It checks
the source hashes and `/run/current-system` before and after the build:

```console
PYTHONPATH=src python tests/integration_build_preview_real_nix.py /etc/nixos
```
