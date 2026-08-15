# WSL live-read-only helper deployment

This deployment has since been superseded by the bounded write deployment in
[`wsl-live-managed-deployment.md`](wsl-live-managed-deployment.md). The record
below remains the audit trail for the earlier read-only milestone.

This record covers the activation of the sandboxed Nix Control Manager helper
and declarative read-only GUI client on the owner's NixOS-WSL host on
2026-08-15. The physical NixOS NVMe was not mounted, inspected, or changed.

## Pinned source

The channel module is fetched from the immutable code commit:

```text
https://github.com/budylo/nixos-control-manager/archive/ca2da1cb06ee2628242049f23fcb7d2e2c1cee28.tar.gz
sha256-+2TT1dSZEvhOxqMjXU5FKlfwvORVg0geU6YB2nA2028=
```

The new `/etc/nixos/ncm-helper.nix` imports only
`packaging/channel-module.nix` from that source, enables target `live` in
`live-read-only` mode for user `nixos`, and enables the declarative graphical
client on loopback port `8765`. The existing generated `ncm/` module is
unchanged. `configuration.nix` retains its one isolated import of
`./ncm-helper.nix`.

## Backup and exact build

A complete pre-deployment configuration backup is retained at:

```text
/var/lib/nix-control-manager/deployment-backups/20260815T135339Z/etc-nixos
```

A second root-private (`0700`) full backup immediately before installing the
GUI client is retained at:

```text
/var/lib/nix-control-manager/deployment-backups/20260815T141325Z/etc-nixos
```

The on-demand lifecycle deployment and its immediate clean-shutdown correction
also have root-private full backups:

```text
/var/lib/nix-control-manager/deployment-backups/20260815T145533Z/etc-nixos
/var/lib/nix-control-manager/deployment-backups/20260815T145949Z/etc-nixos
```

The original `configuration.nix` SHA-256 is
`9e6f76aa5bda0b3689827abb432d8fbd00576ab10e816f1b7097b174db8aa3d0`.
The installed files are root-owned, mode `0644`, with these hashes:

```text
db6cd8932bb85fe4df13021938ba1b9f3bfef32d788d1b422819f87e11fe6bc5  /etc/nixos/configuration.nix
c23a5dcdd4b0dcdf10d672e819d7012fc12a07ef08530e32cfda12f3a1d15c5a  /etc/nixos/ncm-helper.nix
```

The exact candidate was first built from a disposable copy, then built again
from the installed live sources. Both resolved to the same system closure:

```text
/nix/store/8bdlpyb6qa28q9k53anlgxyl0iadibb5-nixos-system-nixos-26.05pre-git
```

Only after this identity check was that closure activated with
`nixos-rebuild switch`. The previous stable closure was:

```text
/nix/store/dasafb5jwzp8fsf4zbkrrqhrnij6rvhf-nixos-system-nixos-26.05pre-git
```

An intermediate lifecycle candidate exposed that caught `SIGINT` returned exit
status 1. Its stop command terminated the server but left the user unit failed.
That generation was immediately superseded after adding a regression test and
making KeyboardInterrupt a successful CLI shutdown; it is not a recommended
rollback target.

## Installed boundary

The rendered helper service has:

- `ProtectSystem=strict` and `ReadOnlyPaths=/etc/nixos`;
- no `ReadWritePaths` or state journal;
- an empty `CapabilityBoundingSet`;
- `PrivateNetwork=true`, `NoNewPrivileges=true`, and `ProtectHome=true`;
- only `AF_UNIX` in `RestrictAddressFamilies`;
- a systemd-owned socket at `/run/nix-control-manager/helper.sock`, mode
  `0660`, owner `root:nix-control-manager`.

A fresh WSL process reports user `nixos` in the `nix-control-manager` group.
The socket is enabled and active; the service starts only when a client connects.

The live capability response reports:

```text
readOnly=true
applyEnabled=false
recoveryEnabled=false
activationEnabled=false
testActivationEnabled=false
homeManagerApplyEnabled=false
homeManagerLiveWriteEnabled=false
dryActivatePreviewEnabled=true
```

The advertised dry preview is the separately Polkit-authorized fixed
`dry-activate` report. It is not `test`, `switch`, a boot change, or write
authority.

## Runtime verification

The installed helper validated the current migration plan in a disposable
copy. Nix parsing and system-derivation evaluation passed, the temporary copy
was removed, and no validation receipt was issued. Before/after hashes of all
five inspected source files were identical.

Typed dummy requests for system apply, transaction recovery, test activation,
and Home Manager apply each returned `operation-disabled`. The active generation
and configuration hashes remained unchanged after every denial.

The packaged GUI then reported HTTP 200 for its root and read-only state APIs.
`/api/helper` found the real socket while preserving every disabled capability
above. The legacy package-map state remains reported as `migration-available`;
this deployment did not migrate or rewrite it.

The installed system environment now contains `ncm`, `ncm-gui`, and
`nix-control-manager.desktop`. The desktop entry resolves to the immutable
launcher in the Nix store. The launcher manages the on-demand, static (not
login-enabled) `nix-control-manager-gui.service`; the service always supplies
`--read-only`, while the launcher optionally opens the loopback URL.

Runtime verification covered stopped status, first start, repeated reuse,
status, stop, restart, and a second stop. Reuse retained the same PID and API
token; restart created a new PID. Both stops finished with `Result=success` and
`ExecMainStatus=0`, removed the listener, and left the unit inactive. The API
reported the expected application identity, API version 1, and
`localWriteEnabled=false`. An authenticated `POST /api/save` returned HTTP 400
with the read-only error, and hashes of all five inspected `/etc/nixos` sources
remained identical. No system or user units were failed. The active system
profile is generation 10, and the GUI user service is intentionally stopped
after verification.

## Rollback

If the helper must be removed, restore the backed-up entrypoint, remove only the
new isolated module, and rebuild:

```console
sudo cp /var/lib/nix-control-manager/deployment-backups/20260815T135339Z/etc-nixos/configuration.nix /etc/nixos/configuration.nix
sudo rm /etc/nixos/ncm-helper.nix
sudo nixos-rebuild switch -I nixos-config=/etc/nixos/configuration.nix
```

To remove the GUI client while retaining the original helper, restore the
second backup's `ncm-helper.nix` and rebuild:

```console
sudo cp /var/lib/nix-control-manager/deployment-backups/20260815T141325Z/etc-nixos/ncm-helper.nix /etc/nixos/ncm-helper.nix
sudo nixos-rebuild switch -I nixos-config=/etc/nixos/configuration.nix
```

To roll back only the lifecycle-service stage and return to the foreground GUI
launcher, restore its pre-deployment pin and rebuild:

```console
sudo cp /var/lib/nix-control-manager/deployment-backups/20260815T145533Z/etc-nixos/ncm-helper.nix /etc/nixos/ncm-helper.nix
sudo nixos-rebuild switch -I nixos-config=/etc/nixos/configuration.nix
```

The previous closure path above remains an additional recovery reference. The
backup is intentionally outside `/etc/nixos` and was not removed after the
successful deployment.
