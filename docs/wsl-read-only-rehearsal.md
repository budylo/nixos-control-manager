# WSL read-only deployment rehearsal

This record covers the first run of the packaged application against the
owner's real NixOS-WSL configuration on 2026-08-15. It was deliberately limited
to inspection, an uninstalled Nix store build, and HTTP GET requests. The
separate physical NixOS installation was not mounted, inspected, or changed.

## Observed host

- NixOS: `26.05pre-git` (`system.stateVersion = "26.05"`)
- kernel: `6.18.33.2-microsoft-standard-WSL2`
- configuration mode: channels, with `configuration.nix` as the sole entrypoint
- active generation:
  `/nix/store/4kzkshxv3133kzrl31bx2jh3gmjdh77y-nixos-system-nixos-26.05pre-git`
- existing NCM module: `/etc/nixos/ncm`, imported by `configuration.nix`
- Home Manager: not detected
- system helper units: not installed
- helper socket and port 8765: absent

The existing managed state used the legacy package-map representation and also
contained the obsolete metadata fields `generatedAt` and `nixosRelease`.
Inspection correctly reported `migration-available`; no migration was applied.

## Immutable baseline

The following SHA-256 values were captured before the rehearsal and were
identical after the server stopped:

```text
9e6f76aa5bda0b3689827abb432d8fbd00576ab10e816f1b7097b174db8aa3d0  /etc/nixos/configuration.nix
43ee90180e35029e3de470c1313b7b5add60fdfb32fb3e9e72a5c774d973c0f4  /etc/nixos/ncm/default.nix
24f351c02a4f7766d64ada5b12510996b1ea1d826977548371a1c935d695609a  /etc/nixos/ncm/packages.nix
04e06c529f524fc7f442eee6ed6b3f46043c6dd5cbcfa6ade14983717049a59f  /etc/nixos/ncm/state.json
```

`/run/current-system` also resolved to the same generation before and after.

## Commands and results

The package was built without installing it or creating a result symlink:

```console
nix build .#default --no-link --print-out-paths
```

The packaged read-only inspectors detected the connected channel configuration
and no Home Manager integration:

```console
nix run . -- detect --config-root /etc/nixos --json
nix run . -- detect-home-manager --config-root /etc/nixos --json
```

The local server used the real configuration only as an inspection target. All
potential output paths were redirected to `/tmp`:

```console
nix run . -- serve \
  --state /etc/nixos/ncm/state.json \
  --user-state /tmp/ncm-wsl-rehearsal-user-state.json \
  --output /tmp/ncm-wsl-rehearsal-managed.nix \
  --config-root /etc/nixos \
  --port 8877
```

Only the root page and GET endpoints for state, preview, system, adoption,
helper status, and Home Manager were requested. No token-protected mutation,
helper operation, Polkit request, candidate activation, or rebuild was invoked.
The redirected output files were never created.

The first run found that strict UI state loading rejected the recognized legacy
file even though the adoption inspector could preview its migration. The server
now normalizes current or legacy state in memory for the GET state and preview
endpoints. It does not rewrite the source. The repeated packaged run returned
HTTP 200 for both endpoints while continuing to report
`migration-available` through system inspection.

## Next deployment boundary

The helper must not be imported into the live system from the Windows checkout
or from an unpinned network reference. This host uses a channel-style
configuration. The repository now provides
`packaging/channel-module.nix`, which builds the package from the same source
snapshot and imports the regular hardened module. A flake check evaluates this
entrypoint in `live-read-only` mode and builds both `ncm` executables.

After that entrypoint is tested, deployment should remain split into distinct
checkpoints:

1. Add a pinned source and the NCM module in a candidate copy.
2. Evaluate and build the candidate without activation.
3. Compare the candidate closure and generated systemd units.
4. With separate approval, install only `mode = "live-read-only"` for user
   `nixos`.
5. Verify the socket and GUI capabilities while confirming that apply,
   recovery, test activation, Home Manager persistence, and permanent switch
   remain disabled.

`live-test` and `live-home-manager` are separate opt-ins and are outside this
deployment step. A permanent NixOS switch capability does not exist in the
helper.

## Channel candidate build

The channel entrypoint was subsequently tested on this WSL host with a
temporary wrapper that imported the current `configuration.nix` and enabled
only `mode = "live-read-only"` for user `nixos`. The command was run from a
fresh `/tmp` directory:

```console
nixos-rebuild build -I nixos-config=<temporary-candidate.nix>
```

It completed without activation and produced:

```text
/nix/store/jqrdqg1qiq7rk8kkjffzh6ddnx1vdwra-nixos-system-nixos-26.05pre-git
```

The generated service clears all Linux capabilities, sets
`ProtectSystem=strict`, `PrivateNetwork=true`, and `ReadOnlyPaths=/etc/nixos`,
and contains no `ReadWritePaths`. Its schema-4 runtime document names one
`live-read-only` target with no system, test, or Home Manager journal.

After the build, all four source hashes and `/run/current-system` still matched
the immutable baseline above. The live system had no NCM unit or helper socket.
The temporary candidate file and result link were removed after inspection;
the build outputs remain ordinary garbage-collectable Nix store objects.

## Published immutable source

The tested channel entrypoint is publicly available at commit
`3a8c6c9650f5394c891571d37548baad9cd5e57a`:

```text
https://github.com/budylo/nixos-control-manager
```

Nix independently prefetched the commit archive with recursive unpacking and
reported this SRI source hash:

```text
sha256-sAXQ3YlgxYn4UkiZdBNhR9htEpyiByBA+6M5szWPXXM=
```

A second channel-style evaluation used the exact URL and hash, not the local
checkout. It reproduced the NCM package and confirmed the empty capability
set, no `ReadWritePaths`, `/etc/nixos` as read-only, socket mode `0660`, and the
configured socket-group membership. The live WSL configuration was not part of
that evaluation and remained unchanged.
