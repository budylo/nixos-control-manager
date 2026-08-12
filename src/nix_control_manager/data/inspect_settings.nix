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
      optionExists = option != null;
      encoded = builtins.tryEval (
        builtins.toJSON (lib.attrByPath parts null evaluated.config)
      );
      inspectDefinition = item:
        let
          definitionEncoded = builtins.tryEval (builtins.toJSON item.value);
        in
        {
          file = builtins.toString item.file;
          valueAvailable = definitionEncoded.success;
          value =
            if definitionEncoded.success then
              builtins.fromJSON definitionEncoded.value
            else
              null;
        };
    in
    {
      path = definition.path;
      inherit optionExists;
      available = optionExists && encoded.success;
      value =
        if optionExists && encoded.success then
          builtins.fromJSON encoded.value
        else
          null;
      activePriority =
        if optionExists && option ? highestPrio then option.highestPrio else null;
      optionType =
        if optionExists then
          {
            name = option.type.name or "";
            description = option.type.description or "";
          }
        else
          null;
      definitions =
        if optionExists then
          map inspectDefinition option.definitionsWithLocations
        else
          [ ];
      declarationFiles =
        if optionExists then
          map builtins.toString option.declarations
        else
          [ ];
    };
in
{
  settings = map inspect catalog;
}
