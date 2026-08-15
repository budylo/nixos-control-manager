# WSL live-read-only helper deployment

This record covers the first activation of the sandboxed Nix Control Manager
helper on the owner's NixOS-WSL host on 2026-08-15. The physical NixOS NVMe was
not mounted, inspected, or changed.

## Pinned source

The channel module is fetched from the immutable code commit:

```text
https://github.com/budylo/nixos-control-manager/archive/3a8c6c9650f5394c891571d37548baad9cd5e57a.tar.gz
sha256-sAXQ3YlgxYn4UkiZdBNhR9htEpyiByBA+6M5szWPXXM=
```

The new `/etc/nixos/ncm-helper.nix` imports only
`packaging/channel-module.nix` from that source and enables target `live` in
`live-read-only` mode for user `nixos`. The existing generated `ncm/` module is
unchanged. `configuration.nix` gained one isolated import of
`./ncm-helper.nix`.

## Backup and exact build

A complete pre-deployment configuration backup is retained at:

```text
/var/lib/nix-control-manager/deployment-backups/20260815T135339Z/etc-nixos
```

The original `configuration.nix` SHA-256 is
`9e6f76aa5bda0b3689827abb432d8fbd00576ab10e816f1b7097b174db8aa3d0`.
The installed files are root-owned, mode `0644`, with these hashes:

```text
db6cd8932bb85fe4df13021938ba1b9f3bfef32d788d1b422819f87e11fe6bc5  /etc/nixos/configuration.nix
c4a9f11ee9bc1bf95dd9e5f6ce86308014a01cd5f5aec5d418e4b957027c20c7  /etc/nixos/ncm-helper.nix
```

The exact candidate was first built from a disposable copy, then built again
from the installed live sources. Both resolved to the same system closure:

```text
/nix/store/hk9wz6md0q8grygq8yc5acghpw4wimwl-nixos-system-nixos-26.05pre-git
```

Only after this identity check was that closure activated with
`nixos-rebuild switch`. The previous active closure was:

```text
/nix/store/4kzkshxv3133kzrl31bx2jh3gmjdh77y-nixos-system-nixos-26.05pre-git
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

## Rollback

If the helper must be removed, restore the backed-up entrypoint, remove only the
new isolated module, and rebuild:

```console
sudo cp /var/lib/nix-control-manager/deployment-backups/20260815T135339Z/etc-nixos/configuration.nix /etc/nixos/configuration.nix
sudo rm /etc/nixos/ncm-helper.nix
sudo nixos-rebuild switch -I nixos-config=/etc/nixos/configuration.nix
```

The previous closure path above remains an additional recovery reference. The
backup is intentionally outside `/etc/nixos` and was not removed after the
successful deployment.
