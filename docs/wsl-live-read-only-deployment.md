# WSL live-read-only helper deployment

This record covers the activation of the sandboxed Nix Control Manager helper
and declarative read-only GUI client on the owner's NixOS-WSL host on
2026-08-15. The physical NixOS NVMe was not mounted, inspected, or changed.

## Pinned source

The channel module is fetched from the immutable code commit:

```text
https://github.com/budylo/nixos-control-manager/archive/91a7bab8abfef3a85980d66b02e68fd0ac246095.tar.gz
sha256-zYBNmtKS/ewjdse7QV3kjqz9zLdapBsU6bUc408FpZM=
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

The original `configuration.nix` SHA-256 is
`9e6f76aa5bda0b3689827abb432d8fbd00576ab10e816f1b7097b174db8aa3d0`.
The installed files are root-owned, mode `0644`, with these hashes:

```text
db6cd8932bb85fe4df13021938ba1b9f3bfef32d788d1b422819f87e11fe6bc5  /etc/nixos/configuration.nix
429122c945ac79c1d0ef3f6ee69fc57914471152ce9ad24c68fc98ecf4b8f580  /etc/nixos/ncm-helper.nix
```

The exact candidate was first built from a disposable copy, then built again
from the installed live sources. Both resolved to the same system closure:

```text
/nix/store/dasafb5jwzp8fsf4zbkrrqhrnij6rvhf-nixos-system-nixos-26.05pre-git
```

Only after this identity check was that closure activated with
`nixos-rebuild switch`. The previous active closure was:

```text
/nix/store/hk9wz6md0q8grygq8yc5acghpw4wimwl-nixos-system-nixos-26.05pre-git
```

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
launcher in the Nix store. The launcher always supplies `--read-only --open`.
Runtime verification confirmed `localWriteEnabled=false`; an authenticated
`POST /api/save` returned HTTP 400 with the read-only error, and hashes of all
five inspected `/etc/nixos` sources remained identical. No systemd units were
failed. The active system profile is generation 8.

## Rollback

If the helper must be removed, restore the backed-up entrypoint, remove only the
new isolated module, and rebuild:

```console
sudo cp /var/lib/nix-control-manager/deployment-backups/20260815T135339Z/etc-nixos/configuration.nix /etc/nixos/configuration.nix
sudo rm /etc/nixos/ncm-helper.nix
sudo nixos-rebuild switch -I nixos-config=/etc/nixos/configuration.nix
```

To roll back only the GUI-client stage while retaining the original helper,
restore the second backup's `ncm-helper.nix` and rebuild:

```console
sudo cp /var/lib/nix-control-manager/deployment-backups/20260815T141325Z/etc-nixos/ncm-helper.nix /etc/nixos/ncm-helper.nix
sudo nixos-rebuild switch -I nixos-config=/etc/nixos/configuration.nix
```

The previous closure path above remains an additional recovery reference. The
backup is intentionally outside `/etc/nixos` and was not removed after the
successful deployment.
