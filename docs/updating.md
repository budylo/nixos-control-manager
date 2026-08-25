# Update Nix Control Manager

Nix Control Manager has no background updater. A release update is an explicit,
reviewable flake change followed by the ordinary NixOS build/test/switch flow.

The Flakes page can now perform the first, non-mutating part of that review for
any supported direct input. **Check for update** is an explicit network action:
NCM resolves only the selected input in a disposable configuration copy, may
populate `/nix/store`, and displays the exact proposed `flake.lock` diff after
the copy has been removed. It does not save that diff to the real lock file and
does not build or activate the system.

The commands below remain the manual path for actually accepting an update.

## Check the installed release

```console
ncm --version
ncm doctor
```

Read the release notes and replace the pinned tag in `flake.nix`, for example:

```nix
url = "github:budylo/nixos-control-manager/v0.1.0-alpha.1";
```

After changing that URL to the newly published tag, update only this input:

```console
nix flake update nix-control-manager
git diff -- flake.nix flake.lock
```

Do not update every flake input merely to update NCM. Review the exact source
revision and the release notes, then use progressively stronger NixOS actions:

```console
nixos-rebuild build --flake .#HOSTNAME
sudo nixos-rebuild test --flake .#HOSTNAME
ncm doctor
sudo nixos-rebuild switch --flake .#HOSTNAME
```

`build` does not activate the result. `test` activates it without selecting it
for the next boot. `switch` is the final explicit persistence step.

## Cancel or roll back

Before `switch`, restore the previous `flake.nix` and `flake.lock` from Git and
rebuild. After `switch`, select the previous NixOS generation from the boot menu
or use the normal NixOS rollback procedure, then restore the previous lock file.
NCM's journal-bound rollback applies only to a switch performed by its own
tested-output `live-control` workflow; it does not replace system-level recovery.
