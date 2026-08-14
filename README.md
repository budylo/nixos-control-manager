# Nix Control Manager

Nix Control Manager is an approachable graphical control center for NixOS. It
keeps the operating system declarative by generating a small, transparent NixOS
module instead of rewriting a user's configuration.

This repository currently contains the first vertical slice:

- a validated JSON state model;
- deterministic generation of `managed.nix`;
- a unified-diff preview;
- atomic writes with a backup of the previous generated module;
- a local, dependency-free web interface for selecting applications;
- a CLI and a Nix flake;
- a fault-tested journaled transaction engine restricted to marked disposable
  fixtures;
- a versioned helper protocol with exact path allow-lists, UID-bound one-time
  receipts, mock Polkit authorization, and a fixture-workflow backend;
- a real fail-closed `pkcheck` authorizer and an opt-in, sandboxed NixOS
  socket/service module with fixture, live-read-only, and live-test targets;
- direct `/etc/nixos` validation in a disposable copy, with no receipt, write,
  recovery, build, or activation authority for the live target.
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
- a read-only Home Manager inspector for both NixOS-module and standalone
  configurations, with conservative user discovery and a separate versioned
  user-state boundary. Home Manager writes and activation remain disabled.
- a preview-only Home Manager package selector that renders a deterministic
  per-user module and unified diff while preserving existing user options. It
  has no save, source-adoption, flake-input, build, or activation operation.

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
ignored by Git. The Home Manager state is currently read-only and is never
created implicitly.

## CLI

```console
ncm init --state state.json
ncm preview --state state.json --output managed.nix
ncm generate --state state.json --output managed.nix
ncm detect --config-root /etc/nixos --json
ncm detect-home-manager --config-root /etc/nixos --json
ncm preview-home-manager --user alice --integration nixos-module --package firefox --json
ncm migrate-state --state /etc/nixos/ncm/state.json
ncm plan-adoption --config-root /etc/nixos
ncm validate-adoption --config-root /etc/nixos
ncm serve --state state.json --output managed.nix --open
ncm-helper-client capabilities
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

Operational preparation, immediate recovery, TTY diagnostics, and power-loss
handling are documented in
[`docs/live-test-recovery.md`](docs/live-test-recovery.md).

`generate` validates the complete state before writing. An existing output is
copied to `managed.nix.bak`, then the new file is atomically moved into place.

## Safety boundary

The current milestone intentionally does **not** run `sudo`, `pkexec`,
`nixos-rebuild`, apply the adoption plan to an existing `configuration.nix`, or
perform `switch`. Default live-read-only mode stops at dry preview. Separate
experimental live-test mode can select only `test` after a bound receipt and a
pre-armed recovery timer; it never creates a boot generation or `result` link.
The transaction and recovery boundary is specified in
[`docs/apply-protocol.md`](docs/apply-protocol.md). Those capabilities remain
restricted to disposable fixtures. The dedicated live target can validate the
exact locally reconstructed plan and produce a bound dry-activation report,
but still has no configuration-write or permanent activation authority.

The repository already contains the underlying transaction and recovery engine,
but it deliberately has no CLI or HTTP apply endpoint and refuses live
`/etc/nixos` paths. Its success, rollback, crash-recovery, concurrent-edit, and
manual-recovery cases run only against temporary test fixtures.

The fixture workflow also performs a second NixOS evaluation after provisional
commit. The journal reaches `committed` only when that installed snapshot needs
no further generated changes and still matches every candidate digest;
otherwise the transaction is rolled back.

The helper protocol is documented in
[`docs/helper-protocol.md`](docs/helper-protocol.md). Its Unix transport and
fixture backend now exercise the complete validate/authorize/apply/verify path.
Unit tests use a deterministic Polkit mock; the production-shaped authorizer
uses `pkcheck` and fails closed. The NixOS module, helper service, and policy are
not installed on the current system.

The opt-in deployment scaffold and sandbox are described in
[`docs/system-helper.md`](docs/system-helper.md).

An x86_64 NixOS VM integration test boots a disposable guest, starts the real
socket-activated root helper, verifies both denied and explicitly authorized
Polkit paths, and completes the real-Nix fixture transaction. It is included in
`nix flake check` as `checks.x86_64-linux.helper-vm` and is also available as
`packages.x86_64-linux.helper-vm-test`.

A second booted VM runs the unprivileged graphical server against an actual
systemd `live-read-only` helper and disposable VM-only `/etc/nixos`. It performs
the full HTTP-to-Unix validation, verifies the helper mount namespace cannot
write `/etc/nixos`, performs a real offline candidate build into the VM's Nix
store, checks streamed output and cleanup, and proves that apply and recovery
stop before Polkit. It then authorizes the distinct dry-preview action, checks
the exact store-path binding, captures systemd impact, and proves the source
and active generation remain unchanged. It is exposed as
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

System and user ownership remain intentionally separate. System packages and
NixOS options continue to live in `state.local.json` and `managed.local.nix`;
future per-user Home Manager packages and options belong to
`user-state.local.json` and a distinct generated user module. This phase can
render that state and module as candidates, but still has no user-state save
endpoint, source-writing operation, Home Manager build or activation, or
flake-input mutation.

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
