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
  pkgs = evaluated.pkgs;
  lib = pkgs.lib;
  catalog = builtins.fromJSON (builtins.readFile catalogPath);
  inspect = definition:
    let
      path = lib.splitString "." definition.attribute;
      exists = lib.hasAttrByPath path pkgs;
      packageAttempt = builtins.tryEval (
        if exists then lib.getAttrFromPath path pkgs else null
      );
      package = if packageAttempt.success then packageAttempt.value else null;
      platformAttempt = builtins.tryEval (
        package != null && lib.meta.availableOn pkgs.stdenv.hostPlatform package
      );
      brokenAttempt = builtins.tryEval (
        package != null && (package.meta.broken or false)
      );
      outputAttempt = builtins.tryEval (
        if package != null then builtins.toString package else ""
      );
      rawLicense =
        if package != null && package ? meta && package.meta ? license then
          package.meta.license
        else
          [ ];
      licenses = if builtins.isList rawLicense then rawLicense else [ rawLicense ];
      unfreeAttempt = builtins.tryEval (
        builtins.any (license:
          builtins.isAttrs license && license ? free && license.free == false
        ) licenses
      );
      licenseNamesAttempt = builtins.tryEval (
        builtins.filter (name: name != "") (map (license:
          if builtins.isAttrs license then
            license.shortName or (license.fullName or "")
          else if builtins.isString license then
            license
          else
            ""
        ) licenses)
      );
      platformAvailable = platformAttempt.success && platformAttempt.value;
      broken = brokenAttempt.success && brokenAttempt.value;
      evaluable = outputAttempt.success;
      compatible = exists && packageAttempt.success && platformAvailable && !broken && evaluable;
      reason =
        if !exists then "missing-attribute"
        else if !packageAttempt.success then "evaluation-rejected"
        else if !platformAvailable then "unsupported-platform"
        else if broken then "broken-package"
        else if !evaluable then "evaluation-rejected"
        else "available";
    in
    {
      attribute = definition.attribute;
      status = if compatible then "compatible" else "incompatible";
      inherit reason;
      unfree = unfreeAttempt.success && unfreeAttempt.value;
      license =
        if licenseNamesAttempt.success then
          lib.concatStringsSep ", " licenseNamesAttempt.value
        else
          "";
    };
in
{
  system = pkgs.stdenv.hostPlatform.system;
  packages = map inspect catalog;
}
