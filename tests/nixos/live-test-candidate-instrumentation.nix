{ lib, pkgs, ... }:

{
  # VM-only instrumentation: preserve a real NixOS toplevel derivation but
  # prevent the disposable candidate from changing the test-driver units.
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
    echo "$1" > /run/ncm-live-test-candidate
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
