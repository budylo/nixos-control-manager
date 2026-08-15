# Bounded live managed-source persistence

`live-managed` is the explicit opt-in helper mode for persisting the system
state owned by Nix Control Manager. It is intentionally much narrower than a
general `/etc/nixos` writer.

The mode can create or replace exactly these two files:

- `/etc/nixos/ncm/state.json`;
- `/etc/nixos/ncm/packages.nix`.

The allow-list is fixed in the NixOS module, daemon configuration, protocol
dispatcher, backend, and transaction engine. A request cannot supply another
path. In particular, the mode cannot edit `configuration.nix`, `flake.nix`,
`flake.lock`, imports, hardware configuration, Home Manager sources, or any
file outside `/etc/nixos/ncm`.

## Enabling the mode

The main configuration must already import the NCM directory through an
operator-reviewed bootstrap such as `imports = [ ./ncm ];`. NCM never creates
or changes that import. Then the helper and graphical client may be enabled:

```nix
{
  services.nix-control-manager-helper = {
    enable = true;
    mode = "live-managed";
    targetId = "managed";
    allowedUsers = [ "alice" ];
  };

  programs.nix-control-manager = {
    enable = true;
    openBrowser = true;
  };
}
```

The graphical user service remains `--read-only` for ordinary local storage.
When it detects the exact managed capability, its Save action instead prepares
a helper transaction. Therefore the browser process never gains direct write
access to `/etc/nixos`.

## Save sequence

1. The application derives canonical `state.json` and `packages.nix` content
   from the typed in-memory state.
2. The root helper independently reconstructs the same candidates and rejects
   any content, path, digest, or fingerprint mismatch.
3. The candidate is parsed and the NixOS derivation is evaluated in a disposable
   copy. The live source tree is unchanged.
4. The UI displays the combined diff. The user must select a separate
   confirmation checkbox.
5. A one-shot, UID-bound receipt kept on the local server is consumed and the
   dedicated Polkit action requests authorization.
6. The helper makes journaled backups, atomically installs only the changed
   allow-listed files, fsyncs them, and repeats canonical comparison plus NixOS
   evaluation against the installed snapshot.
7. The journal reaches `committed` only after post-commit validation. A failure
   rolls the provisional write back.

The browser receives only an opaque intent and fingerprint, never the helper
receipt. Changing the proposal invalidates that intent. Receipts are
short-lived, single-use, and bound to the kernel-derived peer UID.

## Sandbox and journal

The service has an empty Linux capability bounding set and uses
`ProtectSystem=strict`. Its only persistent writable paths are:

- `/etc/nixos/ncm`;
- `/var/lib/nix-control-manager/managed-transactions` by default.

The journal is root-owned and records `transactionKind = "managed-state"`.
Recovery accepts one exact 24-character transaction ID, verifies the journal
kind and target, and has a separate Polkit action. The journal root can be
changed declaratively with `managedJournalRoot`, but must stay outside the
configuration root.

Systemd grants write access at directory granularity, so the repeated
application-layer allow-list is security-critical. The VM integration test
therefore proves both the rendered sandbox and rejection/acceptance behavior
through the real Unix socket and Polkit daemon.

## Deliberately absent authority

`live-managed` has no operation for:

- `nixos-rebuild`, `switch`, `boot`, or `test` activation;
- changing the system or boot profile;
- running an arbitrary command or accepting shell text;
- adding flake inputs or changing a lock file;
- adopting or rewriting the main NixOS configuration;
- Home Manager persistence or activation.

A successful Save means only that the two declarative source files were
validated and committed. A later system rebuild remains a separate operator
decision.

## Integration proof

`checks.x86_64-linux.live-managed-vm` boots a disposable NixOS guest with a
real systemd socket and Polkit daemon. It verifies default denial, an explicitly
authorized commit, pre/post real Nix evaluation, a committed root-only journal,
the exact two-file write scope, and unchanged hashes for `configuration.nix`
and `ncm/default.nix`. It also proves `/run/current-system` does not change.
