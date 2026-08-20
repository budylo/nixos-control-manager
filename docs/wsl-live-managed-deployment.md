# WSL bounded live-managed deployment

The opt-in `live-managed` helper and graphical client were deployed to the
owner's NixOS-WSL host on 2026-08-15. The physical NVMe NixOS installation was
not mounted, inspected, or changed.

## Immutable source

The channel-compatible module is pinned to the full repository commit:

```text
775f931849308dd8b414ffc4f06bddfb8e1a618b
```

The archive was independently prefetched on NixOS:

```text
https://github.com/budylo/nixos-control-manager/archive/775f931849308dd8b414ffc4f06bddfb8e1a618b.tar.gz
sha256-ExygcGyeq8vYxF4wjEqjMGPtVEgEzEgrFPpzrv08vYM=
```

`/etc/nixos/ncm-helper.nix` selects `mode = "live-managed"`, target
`managed`, and user `nixos`. The already reviewed `./ncm` and
`./ncm-helper.nix` imports were not edited. The comment beside the latter still
describes the previous read-only milestone; retaining the source hash was
preferred over changing an operator-owned entrypoint for a comment-only update.

## Backup and pre-activation build

A complete source backup was created before replacing the helper module:

```text
/var/backups/nix-control-manager/etc-nixos-before-live-managed-775f931
```

The backup is root-only through its parent directory. Hashes of
`configuration.nix`, `ncm-helper.nix`, `ncm/default.nix`, `ncm/state.json`, and
`ncm/packages.nix` matched the live files before the change.

The candidate was first built from a copied configuration root. Its evaluated
mode, service unit, GUI unit, and runtime JSON were inspected before activation.
The candidate exposed exactly:

```text
ReadWritePaths=/etc/nixos/ncm
ReadWritePaths=/var/lib/nix-control-manager/managed-transactions
CapabilityBoundingSet=
--helper-target managed
```

No candidate source was copied into the Nix store through a mutable checkout;
the deployed module uses only the immutable archive above.

## Activation result

The previous active system was:

```text
/nix/store/8bdlpyb6qa28q9k53anlgxyl0iadibb5-nixos-system-nixos-26.05pre-git
```

After the explicit deployment rebuild, the active system is:

```text
/nix/store/adsx872r02cxp3n1pm1gdd35sakhhyal-nixos-system-nixos-26.05pre-git
```

The system socket is active. A real unprivileged helper capability request
reported target `managed`, the exact allow-list
`ncm/packages.nix`/`ncm/state.json`, `managedWriteEnabled = true`, and
`managedRecoveryEnabled = true`. Generic apply/recovery, dry activation, test
activation, Home Manager persistence, arbitrary commands, and permanent
activation all remained disabled.

The GUI user unit now starts with the managed helper socket and target. A live
HTTP probe reported `localWriteEnabled = false` and the same bounded helper
capabilities, so the browser still has no direct filesystem write authority.

## Source integrity after activation

Only the explicitly deployed `ncm-helper.nix` changed. These hashes remained
identical to their pre-deployment values:

```text
db6cd8932bb85fe4df13021938ba1b9f3bfef32d788d1b422819f87e11fe6bc5  configuration.nix
43ee90180e35029e3de470c1313b7b5add60fdfb32fb3e9e72a5c774d973c0f4  ncm/default.nix
04e06c529f524fc7f442eee6ed6b3f46043c6dd5cbcfa6ade14983717049a59f  ncm/state.json
24f351c02a4f7766d64ada5b12510996b1ea1d826977548371a1c935d695609a  ncm/packages.nix
```

The new helper module hash is:

```text
db647d8ae0dbbb3e77e128bf8def4cfb24e0f2cd5bfa0409d621b52303747b87  ncm-helper.nix
```

The managed transaction journal exists as `0700 root:root` and was empty after
deployment. No package-state transaction was performed merely to demonstrate
the feature; the booted VM test already covers the real authorized commit and
rollback boundary without manufacturing a change on the user's host.

## First live package transaction

On 2026-08-21 (Europe/Kyiv), the graphical client performed the first real,
operator-approved managed change on the disposable NixOS-WSL host. `Fastfetch`
was selected in the catalog. The UI displayed the combined diff for only
`ncm/state.json` and `ncm/packages.nix`, validated the exact candidate, and
required the explicit two-file confirmation before requesting authorization.

The first authorization attempt used an additional WSL session-activity check.
Polkit denied it safely: the source hashes and transaction journal remained
unchanged. The successful retry used an ephemeral rule restricted to the exact
action, target, write scope, and validated fingerprint:

```text
action: org.nixos.nix-control-manager.apply-validated-managed-plan
target: managed
write scope: ncm/state.json:ncm/packages.nix
plan fingerprint: 35ed8c7fc45b914c1c4329a1bead354a1f4def76423e805f1f1a7498f61bda8e
```

That rule was removed immediately after the single apply attempt and is absent
from the live system. The helper reported `Записано 2 керовані файли; активацію
не виконано.` The committed root-only journal is transaction
`c88235208dff8ce4150fa388`, kind `managed-state`; both post-write parse and
installed-system evaluation checks passed, and its working copy was removed.
The resulting managed hashes are:

```text
70691c4bff159b026f73275f8ab940f10a3c2dcc018ad44d40aa3a0539f48992  ncm/state.json
90056695d9ee93537a6d6f47c795fc3f7c80dec1972b42c491fc0cb8458deaee  ncm/packages.nix
```

A point-in-time copy of the preceding managed source remains at:

```text
/var/backups/nix-control-manager/ncm-before-first-managed-save-fastfetch
```

The exact candidate was then built without activation. It contained
`fastfetch 2.63.1`, while the active generation did not. Only after that check
was an explicit `nixos-rebuild switch` performed. Generation 12 is now current:

```text
/nix/store/slav2baxhbqj1yv4dk2rxrhhnw2dvghj-nixos-system-nixos-26.05pre-git
```

After activation, `fastfetch` resolves from `/run/current-system/sw/bin`, the
main configuration and NCM import hashes are still unchanged, and the helper
socket is active with the same exact two-file allow-list. Generic apply,
activation, test activation, Home Manager writes, and arbitrary commands remain
disabled. The temporary build result link was removed. The physical NVMe NixOS
installation was not mounted, inspected, or changed.

## Rollback

If the helper deployment must be reverted, restore only the backed-up helper
module and rebuild:

```console
sudo install -m 0644 -o root -g root \
  /var/backups/nix-control-manager/etc-nixos-before-live-managed-775f931/ncm-helper.nix \
  /etc/nixos/ncm-helper.nix
sudo nixos-rebuild switch
```

The previous system generation also remains a boot/runtime recovery reference.
Neither rollback procedure needs to modify the NCM state or generated package
module.
