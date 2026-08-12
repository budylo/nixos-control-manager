# Live-test recovery runbook

This runbook applies only to the explicitly enabled experimental
`mode = "live-test"`. That mode invokes `switch-to-configuration test`; it does
not write `/etc/nixos`, update `/nix/var/nix/profiles/system`, create a boot
generation, or provide permanent `switch` authority.

The safest expectation is still that a test activation may interrupt the
desktop, network, or login session. Keep a local TTY or physical console
available and retain a bootable previous generation. Do not garbage-collect the
Nix store while a test session is active: recovery requires the exact previous
closure recorded in the root-only journal.

## Normal automatic recovery

Before activation, the helper creates a journal entry under
`/var/lib/nix-control-manager/test-activations` and schedules
`ncm-test-rollback-<session-id>.timer`. The timer is armed before the candidate
is activated. At the configured deadline it runs the recorded previous
closure's exact `bin/switch-to-configuration test` and verifies that
`/run/current-system` resolves to that closure.

The UI reports the session ID, recovery deadline, and timer unit. From a TTY,
the same state can be inspected without modifying it:

```console
sudo systemctl list-timers --all 'ncm-test-rollback-*'
sudo ls -l /var/lib/nix-control-manager/test-activations
sudo cat /var/lib/nix-control-manager/test-activations/<session-id>.json
readlink -f /run/current-system
readlink -f /nix/var/nix/profiles/system
```

A completed journal has `"state": "recovered"`, `"recoveryExitCode": 0`, and
its `previousSystemPath` equals the resolved `/run/current-system`. Journal files
must remain owned by root and mode `0600`; never edit or delete them to bypass an
unfinished-session check.

## Recover immediately

If the graphical interface still works, use its **Recover now** action. This is
the preferred early-recovery path because the helper checks the session's peer
UID and target and requests the dedicated Polkit action.

The equivalent diagnostic client command, when the installed package is in
`PATH`, is:

```console
ncm-helper-client \
  --socket /run/nix-control-manager/helper.sock \
  recover-test-activation \
  --target live \
  --session-id <session-id>
```

Replace `live` with the module's configured `targetId`. The operation is
idempotent: requesting recovery for an already recovered matching session
returns its recovered state.

If the desktop or Polkit agent is unavailable, sign in on a local TTY as an
administrator. The already armed transient service is the narrowest emergency
path because its command and journal location were fixed before activation:

```console
SESSION=<24-hex-character-session-id>
sudo systemctl start "ncm-test-rollback-${SESSION}.service"
sudo systemctl status --no-pager "ncm-test-rollback-${SESSION}.service"
sudo cat "/var/lib/nix-control-manager/test-activations/${SESSION}.json"
readlink -f /run/current-system
```

Enter the session ID shown by the UI, timer name, or journal filename. Do not
construct it from untrusted text. A valid ID is exactly 24 lowercase hexadecimal
characters.

## If automatic recovery reports `recovery-required`

Do not start a new test activation. Preserve the journal and collect these
read-only diagnostics from a TTY or console:

```console
sudo systemctl status --no-pager 'ncm-test-rollback-*.service'
sudo journalctl -b --no-pager -u 'ncm-test-rollback-*.service'
sudo cat /var/lib/nix-control-manager/test-activations/<session-id>.json
readlink -f /run/current-system
readlink -f /nix/var/nix/profiles/system
```

Confirm that the journal's `previousSystemPath` still exists and contains an
executable `bin/switch-to-configuration`. If it is missing, do not improvise a
symlink and do not edit the journal. Reboot and select a known-good generation
from the bootloader, or use the NixOS installation/rescue environment.

If the previous closure exists but the transient service is unavailable, an
experienced administrator may execute that journal-recorded closure's exact
`bin/switch-to-configuration test` from the console. Verify the absolute
`/nix/store/...` path carefully first. This is a last-resort action; preserve the
journal and logs because the helper must still reconcile the unfinished session.

## Power loss, kernel panic, or unreachable host

The timer is runtime-only and cannot execute while the machine is powered off
or the kernel is unavailable. Because live-test does not update the system
profile or boot generation, a normal reboot should return to the persistent
generation that was active before the test. If it does not, choose the previous
known-good NixOS generation in the bootloader.

Remote-only use remains unsafe: a candidate can break networking before any
remote recovery command reaches the host. Do not rely on this feature without
an independent console or out-of-band recovery path.

## Post-recovery checks

After recovery, verify all of the following before starting another test:

1. `/run/current-system` equals the journal's `previousSystemPath`.
2. The journal state is `recovered` and `recoveryExitCode` is `0`.
3. `/nix/var/nix/profiles/system` still points to the original persistent
   generation.
4. The helper socket is healthy:
   `systemctl is-active nix-control-manager-helper.socket`.
5. Network, login, display-manager, and other affected services work normally.

If any check fails, keep the journal and logs intact and recover from a known-good
boot generation before attempting another activation.
