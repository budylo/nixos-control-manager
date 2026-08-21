{ pkgs }:

let
  catalog = builtins.fromJSON (builtins.readFile ../../src/nix_control_manager/data/catalog.json);
  usable = item:
    let
      path = pkgs.lib.splitString "." item.attribute;
      available = builtins.tryEval (
        pkgs.lib.meta.availableOn pkgs.stdenv.hostPlatform
          (pkgs.lib.getAttrFromPath path pkgs)
      );
    in
    pkgs.lib.hasAttrByPath path pkgs
    && (pkgs.stdenv.hostPlatform.system != "x86_64-linux"
      || (available.success && available.value));
  missing = builtins.filter (item: !(usable item))
    catalog;
  missingNames = map (item: item.attribute) missing;
in
assert pkgs.lib.assertMsg (missing == [ ])
  "Package catalog contains unknown or unavailable nixpkgs attributes: ${builtins.concatStringsSep ", " missingNames}";
pkgs.runCommand "nix-control-manager-package-catalog-check" { } ''
  touch "$out"
''
