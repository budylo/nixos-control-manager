{ pkgs, ncmPackage }:

pkgs.runCommand "nix-control-manager-release-smoke-check" {
  nativeBuildInputs = [ ncmPackage pkgs.jq pkgs.nix ];
} ''
  mkdir -p fixture
  cat > fixture/flake.nix <<'EOF'
  {
    outputs = { self }: {
      nixosConfigurations.alpha = { };
    };
  }
  EOF

  test "$(ncm --version)" = "ncm 0.1.0-alpha.1"
  ncm doctor \
    --config-root "$PWD/fixture" \
    --helper-socket "$PWD/missing-helper.sock" \
    --json > doctor.json
  jq -e '
    .schemaVersion == 1 and
    .application == "nix-control-manager" and
    .version == "0.1.0-alpha.1" and
    .releaseChannel == "alpha" and
    .readOnly == true and
    (.checks | map(.id) | index("configuration") != null)
  ' doctor.json >/dev/null

  mkdir -p "$out"
  cp doctor.json "$out/doctor.json"
''
