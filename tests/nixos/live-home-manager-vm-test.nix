{ pkgs, ncmPackage, ncmModule }:

let
  socketPath = "/run/nix-control-manager/helper.sock";
  journalRoot = "/var/lib/nix-control-manager/home-manager-transactions";
  client = "${ncmPackage}/bin/ncm-helper-client --socket ${socketPath} --timeout 300";
  runAs = user: "${pkgs.util-linux}/bin/runuser -u ${user} --";
in
pkgs.testers.runNixOSTest {
  name = "nix-control-manager-live-home-manager";

  nodes.machine = { pkgs, ... }: {
    imports = [ ncmModule ];

    virtualisation.memorySize = 2048;
    virtualisation.writableStore = true;
    nix.nixPath = [ "nixpkgs=${pkgs.path}" ];

    users.users.hm-denied.isNormalUser = true;
    users.users.hm-authorized.isNormalUser = true;
    environment.systemPackages = [ ncmPackage pkgs.jq ];

    services.nix-control-manager-helper = {
      enable = true;
      mode = "live-home-manager";
      targetId = "live-home";
      homeManagerRoot = "/etc/nixos";
      homeManagerJournalRoot = journalRoot;
      allowedRelativePaths = [
        "home.nix"
        "ncm/managed-home-hm-authorized.nix"
        "ncm/user-state.json"
      ];
      allowedUsers = [ "hm-denied" "hm-authorized" ];
      validationTimeout = 300;
    };

    security.polkit.extraConfig = ''
      // Test-only authorization inside the disposable VM.
      polkit.addRule(function(action, subject) {
        if (action.id == "org.nixos.nix-control-manager.apply-validated-home-manager-plan" &&
            subject.user == "hm-authorized") {
          return polkit.Result.YES;
        }
      });
    '';

    systemd.services.ncm-live-home-setup = {
      description = "Prepare disposable live Home Manager sources";
      wantedBy = [ "multi-user.target" ];
      before = [ "nix-control-manager-helper.service" ];
      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
      };
      script = ''
        install -d -m 0755 /etc/nixos
        cat > /etc/nixos/home.nix <<'EOF'
        { pkgs, ... }:
        {
          home.username = "hm-authorized";
        }
        EOF
        cat > /etc/nixos/flake.nix <<'EOF'
        {
          outputs = { ... }:
            let
              pkgs = { git = "git-package-sentinel"; };
              home = import ./home.nix { inherit pkgs; config = { }; };
              managed = import (builtins.head home.imports) { inherit pkgs; };
              activationPackage = assert managed.home.packages == [ pkgs.git ]; {
                drvPath = "/nix/store/ncm-live-home-manager.drv";
              };
            in { homeConfigurations.hm-authorized = { inherit activationPackage; }; };
        }
        EOF
        chmod 0644 /etc/nixos/home.nix /etc/nixos/flake.nix
      '';
    };

    systemd.services.nix-control-manager-helper = {
      requires = [ "ncm-live-home-setup.service" ];
      after = [ "ncm-live-home-setup.service" ];
    };
  };

  testScript = ''
    from datetime import timedelta
    import json

    timeout = timedelta(seconds=300)

    machine.start()
    machine.wait_for_unit("multi-user.target")
    machine.wait_for_unit("ncm-live-home-setup.service")
    machine.wait_for_unit("nix-control-manager-helper.socket")

    capabilities = json.loads(machine.succeed(
        "${runAs "hm-denied"} ${client} capabilities"
    ))
    target = capabilities["result"]["targets"][0]
    t.assertFalse(target["fixtureOnly"])
    t.assertFalse(target["applyEnabled"])
    t.assertFalse(target["recoveryEnabled"])
    t.assertTrue(target["homeManagerApplyEnabled"])
    t.assertTrue(target["homeManagerLiveWriteEnabled"])
    t.assertFalse(target["dryActivatePreviewEnabled"])
    t.assertFalse(capabilities["result"]["activationEnabled"])

    machine.wait_for_unit("nix-control-manager-helper.service")
    rw_paths = machine.succeed(
        "systemctl show nix-control-manager-helper.service -p ReadWritePaths --value"
    )
    t.assertIn("/etc/nixos", rw_paths)
    t.assertIn("${journalRoot}", rw_paths)
    t.assertEqual(
        machine.succeed(
            "systemctl show nix-control-manager-helper.service -p CapabilityBoundingSet --value"
        ).strip(),
        "",
    )

    current_before = machine.succeed("readlink -f /run/current-system").strip()
    original_hash = machine.succeed("sha256sum /etc/nixos/home.nix").split()[0]

    denied_validation = json.loads(machine.succeed(
        "${runAs "hm-denied"} ${client} validate-home-manager-plan "
        "--target live-home --config-root /etc/nixos --user hm-authorized "
        "--integration standalone --package git",
        timeout=timeout,
    ))
    denied_result = denied_validation["result"]
    denied_command = (
        "${runAs "hm-denied"} ${client} apply-home-manager-plan --target live-home "
        f"--plan-fingerprint {denied_result['planFingerprint']} "
        f"--receipt {denied_result['validationReceipt']} > /tmp/hm-denied.json"
    )
    denied_status, _ = machine.execute(denied_command, timeout=timeout)
    t.assertEqual(denied_status, 2)
    t.assertEqual(json.loads(machine.succeed("cat /tmp/hm-denied.json"))["status"], "denied")
    t.assertEqual(
        machine.succeed("sha256sum /etc/nixos/home.nix").split()[0],
        original_hash,
    )
    machine.fail("test -e /etc/nixos/ncm")

    validation = json.loads(machine.succeed(
        "${runAs "hm-authorized"} ${client} validate-home-manager-plan "
        "--target live-home --config-root /etc/nixos --user hm-authorized "
        "--integration standalone --package git",
        timeout=timeout,
    ))
    result = validation["result"]
    applied = json.loads(machine.succeed(
        "${runAs "hm-authorized"} ${client} apply-home-manager-plan --target live-home "
        f"--plan-fingerprint {result['planFingerprint']} "
        f"--receipt {result['validationReceipt']}",
        timeout=timeout,
    ))
    t.assertEqual(applied["status"], "ok")
    t.assertEqual(applied["result"]["state"], "committed")
    t.assertFalse(applied["result"]["fixtureOnly"])
    t.assertTrue(applied["result"]["liveWriteEnabled"])
    t.assertFalse(applied["result"]["activationEnabled"])
    machine.succeed("test -f /etc/nixos/ncm/user-state.json")
    machine.succeed("grep -F 'pkgs.git' /etc/nixos/ncm/managed-home-hm-authorized.nix")
    t.assertEqual(machine.succeed("readlink -f /run/current-system").strip(), current_before)
    machine.succeed("grep -R -F '\"fixtureOnly\": false' ${journalRoot}/*/manifest.json")
  '';
}
