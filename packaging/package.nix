{ pkgs, source }:

pkgs.python3Packages.buildPythonApplication {
  pname = "nix-control-manager";
  version = "0.1.0-alpha.1";
  pyproject = true;
  src = source;
  build-system = [ pkgs.python3Packages.setuptools ];
  meta = {
    description = "A user-friendly control center for declarative NixOS configuration";
    mainProgram = "ncm";
    platforms = [ "x86_64-linux" "aarch64-linux" ];
  };
}
