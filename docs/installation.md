# Install the alpha release

The supported `v0.1.0-alpha.1` installation path is an x86_64 NixOS flake. The
application remains declarative: installation adds a pinned flake input and a
NixOS module. No curl-to-shell installer edits `/etc/nixos`.

## Try without installing

From a NixOS terminal with flakes enabled:

```console
nix run github:budylo/nixos-control-manager/v0.1.0-alpha.1 -- serve --read-only --open
```

This starts only the loopback web application. `--read-only` disables local
state/module persistence, and no system helper or activation authority is
installed.

## Install the graphical client

Before editing the system flake, commit or back up its current working state.
Add the pinned input:

```nix
inputs.nix-control-manager = {
  url = "github:budylo/nixos-control-manager/v0.1.0-alpha.1";
  inputs.nixpkgs.follows = "nixpkgs";
};
```

Pass the module to the intended `nixosSystem` and enable the client:

```nix
modules = [
  nix-control-manager.nixosModules.default
  ({ ... }: {
    programs.nix-control-manager.enable = true;
  })
];
```

Replace `nix-control-manager` above with the exact input argument name used by
your flake outputs. Then evaluate before activating:

```console
nixos-rebuild build --flake .#HOSTNAME
sudo nixos-rebuild switch --flake .#HOSTNAME
ncm --version
ncm doctor
```

Launch **Nix Control Manager** from the desktop menu or run:

```console
ncm-gui --open
```

The client alone runs read-only. It can inspect the configuration and create
disposable previews, but cannot ask a privileged helper to write or activate
anything.

## Optional read-only system helper

After the client works, the lowest-authority helper mode may be enabled
separately. Replace `alice` with the existing desktop user:

```nix
services.nix-control-manager-helper = {
  enable = true;
  mode = "live-read-only";
  targetId = "live";
  allowedUsers = [ "alice" ];
};
```

Build and inspect the diff before switching again. This mode can validate a
disposable candidate through the root service, but cannot write `/etc/nixos`,
create apply receipts, run test activation or select a generation. The
`live-managed`, `live-test`, `live-home-manager`, and `live-control` modes are
advanced explicit capabilities and are not part of the first-install path.

## Remove the alpha

Disable `programs.nix-control-manager`, disable the helper if enabled, remove
the module and input, update the lock file, and rebuild the system normally.
Managed files under `/etc/nixos/ncm` are user configuration data and are not
silently deleted by package removal.

See [updating.md](updating.md) for the controlled release update procedure.
