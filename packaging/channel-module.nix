{ lib, pkgs, ... }:

let
  source = lib.cleanSource ../.;
  package = import ./package.nix {
    inherit pkgs source;
  };
in
{
  imports = [
    (import ./nixos-module.nix {
      defaultPackage = _: package;
    })
  ];
}
