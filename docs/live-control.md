# Exact tested-system control

`mode = "live-control"` is the explicit opt-in boundary for making a tested
NixOS closure permanent. It is deliberately narrower than `nixos-rebuild
switch`: the client cannot submit a command, choose an arbitrary generation, or
replace the closure recorded by the helper.

## Required sequence

1. NCM validates the current `/etc/nixos` source in a disposable copy.
2. The unprivileged build produces one exact system closure.
3. The helper independently re-evaluates the source and requires that exact
   derivation output.
4. A Polkit-authorized dry preview issues a short-lived receipt.
5. `test` records the current profile closure, arms automatic recovery, and
   activates only the verified candidate.
6. After explicit confirmation, commit revalidates the same source/output and
   binds the request to the active session and peer UID.
7. A root transient service stops the recovery timer, sets the system profile
   to the tested closure, invokes its fixed `switch` entrypoint, and verifies
   both `/run/current-system` and `/nix/var/nix/profiles/system`.

The browser receives no reusable Polkit receipt and never supplies a command or
profile path.

## Rollback

The generations page shows read-only current, booted, and profile state. The
rollback button for a committed NCM session restores only the exact previous
closure stored in its root-owned journal. It does not accept a generation
number or path from the browser. Rollback has its own Polkit action and verifies
both runtime and profile links after switching.

If commit fails after partially changing state, the transition first attempts
to restore the previous profile and runtime. If rollback fails, it attempts to
restore the committed candidate. A failed compensation remains visibly marked
`recovery-required` or `rollback-required`; it is never reported as success.

## Enabling

```nix
services.nix-control-manager-helper = {
  enable = true;
  mode = "live-control";
  targetId = "control";
  allowedUsers = [ "alice" ];
  testActivationTimeout = 300;
};
```

Keep console access and a known-good boot generation. Automatic test recovery
is runtime-only and cannot protect against power loss, kernel failure, or a
broken bootloader. The mode does not garbage-collect previous closures.

## Verification

The `checks.x86_64-linux.live-control-vm` flake check boots a disposable NixOS
VM and exercises the real Unix socket, peer credentials, Polkit rules, exact
candidate evaluation, test activation, asynchronous commit, session status,
and rollback. It also proves that `/etc/nixos` source hashes remain unchanged.
