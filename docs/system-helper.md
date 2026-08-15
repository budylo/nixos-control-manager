# System helper deployment boundary

The repository exports an opt-in NixOS module and a socket-activated
`ncm-helper` executable. It has a transaction-capable fixture mode, a
capability-reduced live-read-only mode, an explicit experimental live-test
mode, and a separate opt-in live Home Manager persistence mode. The module is
not imported or enabled by
the package itself, and this project has not changed the machine's active NixOS
configuration.

## What is implemented

- systemd owns `/run/nix-control-manager/helper.sock` and passes exactly one
  listening descriptor to the helper;
- the socket is `0660`, owned by root and the `nix-control-manager` group;
- the helper derives PID, UID, and GID from Linux `SO_PEERCRED`;
- Polkit checks use `pid,start-time,uid`, read from the kernel-backed `/proc`
  identity, and allow the desktop authentication agent to interact;
- no textual fallback agent, password collection, shell command, or client UID
  field is accepted;
- the service runs as root with a strict systemd filesystem, network, namespace,
  device, capability, address-family, and syscall sandbox;
- fixture mode can write only `fixtureRoot` and its external transaction
  journal;
- live-read-only mode has no `ReadWritePaths`, `StateDirectory`, transaction
  journal, validation receipt, apply, or recovery capability;
- live-read-only mode may expose the separate `preview-activation` capability;
  it accepts only an independently verified candidate store path, runs the
  fixed dry entrypoint, and retains no receipt;
- live-home-manager mode keeps NixOS apply disabled and exposes only one fixed
  Home Manager root plus its external root-only transaction journal for writes;
- the runtime configuration is a strict versioned JSON file generated into the
  Nix store.

The policy actions remain separate for applying a validated plan, recovering
one exact transaction, previewing activation, time-limited test activation, and
manual test recovery. Permanent `switch`, boot, and rollback-generation
operations do not exist.

## NixOS module

Flake consumers can import `nixosModules.default`. The module is disabled by
default. A future disposable test host could opt in with:

```nix
{
  imports = [ inputs.nix-control-manager.nixosModules.default ];

  services.nix-control-manager-helper = {
    enable = true;
    fixtureRoot = "/var/lib/nix-control-manager/fixture";
    allowedUsers = [ "alice" ];
  };
}
```

Channel-style NixOS configurations can import the self-contained
`packaging/channel-module.nix` entrypoint. Pin the complete repository source
to an immutable revision and content hash; do not import a mutable checkout or
an unversioned branch into a live system:

```nix
{ ... }:

let
  ncmSource = builtins.fetchTarball {
    url = "https://example.invalid/nix-control-manager/archive/<commit>.tar.gz";
    sha256 = "sha256-<verified-source-hash>";
  };
in
{
  imports = [ "${ncmSource}/packaging/channel-module.nix" ];

  services.nix-control-manager-helper = {
    enable = true;
    mode = "live-read-only";
    targetId = "live";
    allowedUsers = [ "alice" ];
  };
}
```

The URL and hash above are intentional placeholders. The channel entrypoint
uses the host's `pkgs`, builds NCM from that same pinned source tree, and then
imports the regular hardened helper module. It performs no network lookup of
its own. `nixos-rebuild build` can evaluate this candidate without installing
its units; only a later explicit activation can make the socket available.

The configured root must already contain the exact transaction fixture marker.
The module does not create that marker. Fixture mode cannot target `/etc/nixos`.
Both Nix assertions and the Python runtime reject a journal nested below the
fixture root, unsafe relative paths, and duplicate paths.

The read-only live mode is explicit and always targets `/etc/nixos`:

```nix
services.nix-control-manager-helper = {
  enable = true;
  mode = "live-read-only";
  targetId = "live";
  allowedUsers = [ "alice" ];
};
```

It has no option for a different system root and cannot be upgraded to a
writable NixOS adoption target. Schema version 4 accepts `fixture`,
`live-read-only`, `live-test`, and `live-home-manager`; each live mutation mode
adds only its narrowly scoped journal/capability.

Experimental test activation must be opted into explicitly:

```nix
services.nix-control-manager-helper = {
  enable = true;
  mode = "live-test";
  targetId = "live";
  allowedUsers = [ "alice" ];
  testActivationTimeout = 300;
};
```

It requires a bound dry-preview receipt, arms recovery before activation, and
never writes `/etc/nixos` or the system profile. Timer recovery is runtime-only
and cannot cover a power loss or kernel panic. The operator procedure is in
[`live-test-recovery.md`](live-test-recovery.md).

Live Home Manager source persistence must also be opted into separately:

```nix
services.nix-control-manager-helper = {
  enable = true;
  mode = "live-home-manager";
  targetId = "live-home";
  allowedUsers = [ "alice" ];
  homeManagerRoot = "/etc/nixos";
  homeManagerJournalRoot =
    "/var/lib/nix-control-manager/home-manager-transactions";
};
```

System apply, test activation, permanent switching, and Home Manager activation
remain disabled. The first sandboxed deployment slice excludes `/home` and
`/root`; operational details are in
[`live-home-manager.md`](live-home-manager.md).

## Sandbox highlights

The generated service uses `ProtectSystem=strict`, `ProtectHome`, private
devices, temporary files and networking, `NoNewPrivileges`, namespace and
address-family restrictions, a narrow capability bounding set, and an allow-list
system-call filter. In fixture mode, `ReadWritePaths` contains only the fixture
and transaction journal. In `live-read-only` there are no writable persistent
paths. Experimental `live-test` adds only its root-owned activation journal to
`ReadWritePaths`; `/etc/nixos` stays explicitly read-only in both live modes,
and their capability bounding set is empty. `live-home-manager` exposes only
its configured source root and journal through `ReadWritePaths`, while retaining
the empty capability bounding set.
`/proc` remains visible because safe Polkit process subjects require
the client start time and real UID.

The flake evaluates a complete NixOS configuration and inspects the rendered
socket and service units. A separate Linux integration check runs
`systemd-analyze security --offline=yes` against the rendered service in a
temporary root. Neither check installs or starts a unit.

The x86_64 flake checks also include a full NixOS VM test. The disposable guest:

1. creates a marked configuration fixture and boots the real Polkit daemon;
2. activates the root helper through its group-restricted systemd socket;
3. obtains a validation receipt as an unprivileged user and confirms that the
   default headless Polkit path denies apply without changing any source hash;
4. uses a second user covered by an explicit VM-only Polkit rule to validate and
   apply the same independently rebuilt plan;
5. runs real Nix evaluation before and after the provisional commit;
6. verifies a committed journal, a no-changes installed plan, readable `0755`
   managed directories and `0644` generated files, and disabled activation.

The VM test found and now guards two deployment details: the journal directory
must exist before systemd constructs the mount namespace, and managed
configuration directories must override the service's restrictive `UMask=0077`.
The module creates the journal with mode `0700`; the transaction engine
explicitly finalizes generated configuration directories as `0755`.

A second x86_64 VM check covers the live graphical path. It runs `ncm serve` as
an unprivileged user, activates the actual `live-read-only` helper through
systemd, and validates a disposable VM-only `/etc/nixos` through
`HTTP -> UI adapter -> Unix socket -> root helper -> real Nix evaluation`. The
test enters the helper's mount namespace and confirms that a write probe fails
with a read-only filesystem, while source hashes remain unchanged. It also
checks that no receipt or journal exists and that apply/recovery requests are
rejected before Polkit.

The graphical process, not the root helper, also performs a real candidate
build as its unprivileged service user. The VM pre-registers the equivalent
system closure so this remains deterministic and offline, then verifies the
fixed no-link command, streamed result path, temporary-copy removal, unchanged
source hashes and `/run/current-system`, and the absence of a `result` link.
Production builds may add store paths and therefore consume disk until normal
Nix garbage collection; that is the only intended persistent effect.

The VM then authorizes only the distinct dry-preview action. The helper repeats
candidate validation, resolves the expected derivation output, matches the
built closure, and runs its `switch-to-configuration dry-activate`. The test
captures proposed systemd stops/restarts/starts and rechecks both source hashes
and `/run/current-system`. The live sandbox can cause individual dry-capable
activation snippets to report read-only failures; this is preserved in output
and reinforces that NixOS dry reports are incomplete guidance, not activation
proofs.

This VM check found two additional unit-rendering details now guarded by the
flake: an empty Nix list omits `CapabilityBoundingSet` instead of clearing it,
so live mode emits the explicit empty systemd assignment; and `ProtectHome`
requires an ephemeral `HOME=/tmp` for Nix channel probing. The latter keeps
home directories protected without adding persistent writable state.

A third x86_64 VM check covers the experimental `live-test` recovery path. It
uses a real candidate NixOS toplevel with a VM-only activation hook, while a
minimal previous closure acts as the recovery anchor. The check validates the
plan, captures an exact-output dry-preview receipt, proves the receipt is
single-use and peer-bound, performs the runtime-only `test`, and observes the
pre-armed timer restore the previous closure after 30 seconds. It also verifies
the root-only journal mode and final `recovered` state, unchanged
`/nix/var/nix/profiles/system`, unchanged `/etc/nixos` hashes, and a still-live
helper socket. It is available as `checks.x86_64-linux.live-test-recovery-vm`.

A fourth x86_64 VM check covers live Home Manager source persistence. It checks
the separate capability flags, default Polkit denial, exact allow-list,
pre/post real Nix evaluation, committed live-mode journal, and unchanged
`/run/current-system`. It is available as
`checks.x86_64-linux.live-home-manager-vm`.

`ncm-helper-client` is an unprivileged typed diagnostic client for capabilities,
validation, exact dry-activation preview, receipt-based apply, and exact
transaction recovery. The helper
still independently reconstructs and compares every submitted plan.

## Graphical interface adapter

The loopback UI server can connect to the system socket with `--helper-socket`
and `--helper-target`. Startup does not fail when the helper is absent: the UI
reports it as unavailable and keeps the system-validation button disabled.

Before enabling that button, the adapter requires protocol version 1 and an
exact advertised target with `liveTarget = true`, `readOnly = true`, disabled
apply/recovery/activation, and no arbitrary-command capability. Validation is a
token-protected HTTP POST. The adapter binds the response request ID and plan
fingerprint, rejects any receipt, and exposes only normalized checks and
read-only status to the browser.

`tests/integration_live_read_only_ui.py` exercises the full loopback HTTP to
Unix-socket path with real Nix evaluation and compares all source hashes. The
manual browser-QA server in `tests/manual_live_read_only_ui_server.py` uses the
same backend and never installs a system unit.

## Deliberately not implemented

- live NixOS system-adoption writes (the only `/etc/nixos` exception is an
  explicit Home Manager source plan in `live-home-manager` mode);
- installation on the current WSL or physical NixOS system;
- privileged/helper-mediated build, permanent `switch`, rollback-generation,
  or boot activation (local no-link build, exact dry preview, and opt-in
  time-limited `test` are implemented separately);
- socket access for users not explicitly listed in `allowedUsers`, or silent
  policy overrides;
- a fallback that weakens authorization when Polkit or its session agent is
  unavailable.
