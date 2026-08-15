# Live Home Manager source persistence

`live-home-manager` is an explicit helper mode for atomically persisting one
validated Home Manager source plan. It is not a general writable NixOS target.
System `applyEnabled`, system recovery, test activation, permanent switching,
boot changes, and Home Manager activation all remain disabled.

## Supported first deployment

The NixOS module defaults `homeManagerRoot` to `/etc/nixos`, which covers Home
Manager's NixOS-module integration. The systemd sandbox uses `ProtectHome=true`,
so `/home` and `/root` are intentionally rejected in this first slice. A
standalone configuration can be tested only when its complete root is outside
protected home directories and is configured explicitly.

The helper never accepts either root from a client request. Schema 4 stores:

- the fixed Home Manager root;
- an external root-only journal;
- at most 16 exact relative paths;
- an optional fixed flake target;
- a stable target ID and the users allowed to reach its Unix socket.

For a detected NixOS-module user named `alice`, an example opt-in is:

```nix
{
  imports = [ inputs.nix-control-manager.nixosModules.default ];

  services.nix-control-manager-helper = {
    enable = true;
    mode = "live-home-manager";
    targetId = "live-home";
    allowedUsers = [ "alice" ];
    homeManagerRoot = "/etc/nixos";
    homeManagerJournalRoot =
      "/var/lib/nix-control-manager/home-manager-transactions";
    allowedRelativePaths = [
      "configuration.nix"
      "ncm/home-manager-alice.nix"
      "ncm/managed-home-alice.nix"
      "ncm/user-state.json"
    ];
  };
}
```

Changing the detected user or integration requires reviewing and updating this
allow-list through the ordinary NixOS configuration. The helper cannot widen it.

## Graphical flow

The Home Manager connection-plan drawer exposes live persistence only when the
configured helper target advertises both `homeManagerApplyEnabled` and
`homeManagerLiveWriteEnabled`. The user must:

1. inspect the exact source diff;
2. run disposable local validation;
3. ask the helper to reconstruct and validate the same fingerprint;
4. explicitly tick the confirmation for that fingerprint;
5. authorize the dedicated Home Manager Polkit action.

The helper receipt never reaches browser JavaScript. The local server retains
it in memory behind an opaque intent ID for at most the helper TTL. The intent
is consumed before the apply request, so a denial, network error, or repeated
click requires a fresh validation. A successful UI result is accepted only when
the transaction and its nested result report `committed`, `fixtureOnly = false`,
and activation/switch remain false.

## Diagnostic CLI flow

The typed diagnostic client remains available for recovery and troubleshooting.
It can validate and then submit the returned fingerprint and receipt directly:

```console
ncm-helper-client validate-home-manager-plan \
  --target live-home \
  --config-root /etc/nixos \
  --user alice \
  --integration nixos-module \
  --package firefox > validation.json

fingerprint=$(jq -r .result.planFingerprint validation.json)
receipt=$(jq -r .result.validationReceipt validation.json)

ncm-helper-client apply-home-manager-plan \
  --target live-home \
  --plan-fingerprint "$fingerprint" \
  --receipt "$receipt"
```

The helper independently reconstructs the plan from its configured root,
compares every path, action, digest, and candidate byte, evaluates a disposable
copy, binds a short-lived receipt to the kernel-derived peer UID, and asks
Polkit only for the dedicated Home Manager apply action.

After provisional atomic replacement it reconstructs a no-changes plan from
the installed sources and evaluates them again. Only then is the journal marked
`committed`; otherwise the files are rolled back. No activation command is
present in this workflow.

## Recovery

An interruption can leave a manifest in `awaiting-verification`, `committing`,
or `recovery-required`. Recovery is explicit, transaction-ID scoped, and uses a
different Polkit action:

```console
ncm-helper-client recover-home-manager-transaction \
  --target live-home \
  --transaction-id 0123456789abcdef01234567
```

Recovery verifies the configured root, `fixtureOnly = false`, and
`transactionKind = "home-manager-adoption"` before restoring backups. It
refuses to overwrite a target that was externally edited after the recorded
commit.

## Remaining boundary

This mode does not install itself, add Home Manager flake inputs, stage Git
files, run `home-manager switch`, or run `nixos-rebuild`. The VM regression
proves default Polkit denial, exact-source commit after authorization, real
pre/post evaluation, root-only journaling, and an unchanged
`/run/current-system`. The local HTTP/UI boundary adds exact confirmation but
does not widen helper authority.
