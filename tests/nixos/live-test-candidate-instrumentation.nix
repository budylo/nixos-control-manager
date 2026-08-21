{ lib, pkgs, ... }:

{
  # VM-only instrumentation: preserve a real NixOS toplevel derivation and
  # exercise the systemd dependency edge that matters to live activation,
  # while preventing the disposable candidate from replacing test-driver
  # units and cutting off the VM harness.
  system.systemBuilderCommands = lib.mkAfter ''
    cat > "$out/bin/switch-to-configuration" <<'SCRIPT'
#!${pkgs.runtimeShell}
set -eu

case "$1" in
  dry-activate)
    echo "NCM disposable candidate dry activation"
    ;;
  test|switch)
    candidate="$(${pkgs.coreutils}/bin/dirname "$(${pkgs.coreutils}/bin/dirname "$0")")"
    ${pkgs.coreutils}/bin/ln -sfn "$candidate" /run/current-system
    # A normal NixOS generation change can restart polkit when its rules or
    # unit change.  This used to stop the request-owning helper through a hard
    # Requires= dependency and strand the activation transaction.
    ${pkgs.systemd}/bin/systemctl restart polkit.service
    ${pkgs.systemd}/bin/systemctl is-active --quiet polkit.service
    echo "$1" >> /run/ncm-live-test-candidate
    ;;
  *)
    echo "unsupported VM-only activation mode: $1" >&2
    exit 64
    ;;
esac
SCRIPT
    chmod 0755 "$out/bin/switch-to-configuration"
  '';
}
