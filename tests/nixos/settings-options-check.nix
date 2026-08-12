{ pkgs }:
let
  lib = pkgs.lib;
  catalog = builtins.fromJSON (
    builtins.readFile ../../src/nix_control_manager/data/settings_catalog.json
  );
  evaluated = import (pkgs.path + "/nixos") {
    system = pkgs.stdenv.hostPlatform.system;
    configuration = { ... }: { system.stateVersion = "26.05"; };
  };
  optionExists = definition:
    lib.attrByPath (lib.splitString "." definition.path) null evaluated.options != null;
  missing = map (definition: definition.path) (builtins.filter (definition: !optionExists definition) catalog);
  catalogModule = lib.foldl' lib.recursiveUpdate { } (
    map (definition:
      lib.setAttrByPath (lib.splitString "." definition.path) definition.default
    ) catalog
  );
  configured = import (pkgs.path + "/nixos") {
    system = pkgs.stdenv.hostPlatform.system;
    configuration = { ... }: lib.recursiveUpdate catalogModule {
      system.stateVersion = "26.05";
    };
  };
  mismatched = map (definition: definition.path) (
    builtins.filter (definition:
      lib.attrByPath (lib.splitString "." definition.path) null configured.config
        != definition.default
    ) catalog
  );
in
assert lib.assertMsg (missing == [ ])
  "Nix Control Manager settings catalog contains missing NixOS options: ${lib.concatStringsSep ", " missing}";
assert lib.assertMsg (mismatched == [ ])
  "Nix Control Manager settings defaults fail NixOS type/merge evaluation: ${lib.concatStringsSep ", " mismatched}";
pkgs.runCommand "nix-control-manager-settings-options-check" { } ''
  mkdir -p "$out"
  ${lib.concatMapStringsSep "\n" (definition: "echo ${lib.escapeShellArg definition.path} >> $out/options") catalog}
''
