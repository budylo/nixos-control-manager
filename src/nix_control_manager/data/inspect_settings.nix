let
  configRoot = builtins.getEnv "NCM_INSPECT_CONFIG_ROOT";
  catalogPath = builtins.getEnv "NCM_INSPECT_CATALOG_PATH";
  mode = builtins.getEnv "NCM_INSPECT_MODE";
  flakeTarget = builtins.getEnv "NCM_INSPECT_FLAKE_TARGET";
  root = builtins.toPath configRoot;
  evaluated =
    if mode == "flake" then
      let
        flake = builtins.getFlake configRoot;
      in
      builtins.getAttr flakeTarget flake.nixosConfigurations
    else
      import <nixpkgs/nixos> {
        configuration = root + "/configuration.nix";
      };
  lib = evaluated.pkgs.lib;
  catalog = builtins.fromJSON (builtins.readFile catalogPath);
  inspect = definition:
    let
      parts = lib.splitString "." definition.path;
      option = lib.attrByPath parts null evaluated.options;
      encoded = builtins.tryEval (
        builtins.toJSON (lib.attrByPath parts null evaluated.config)
      );
    in
    {
      path = definition.path;
      available = option != null && encoded.success;
      value =
        if option != null && encoded.success then
          builtins.fromJSON encoded.value
        else
          null;
      definitionFiles =
        if option == null then [ ] else
        map (item: builtins.toString item.file) option.definitionsWithLocations;
      declarationFiles =
        if option == null then [ ] else
        map builtins.toString option.declarations;
    };
in
{
  settings = map inspect catalog;
}
