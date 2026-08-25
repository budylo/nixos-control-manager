let
  configRoot = builtins.getEnv "NCM_INSPECT_CONFIG_ROOT";
  flake = builtins.getFlake configRoot;
  directInputs = builtins.filter (name: name != "self") (builtins.attrNames flake.inputs);
  configurations = if flake ? nixosConfigurations then flake.nixosConfigurations else { };
in
{
  inputs = directInputs;
  nixosConfigurations = builtins.attrNames configurations;
}
