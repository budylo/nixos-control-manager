{ pkgs, ncmPackage, ncmModule }:

let
  fixtureConfiguration = pkgs.writeText "fixture-configuration.nix" ''
    { ... }:

    {
      imports = [
      ];

      boot.loader.grub.devices = [ "nodev" ];
      fileSystems."/".device = "none";
      fileSystems."/".fsType = "tmpfs";
      system.stateVersion = "26.05";
    }
  '';
  socketPath = "/run/nix-control-manager/helper.sock";
  fixtureRoot = "/srv/ncm-fixture";
  client = "${ncmPackage}/bin/ncm-helper-client --socket ${socketPath} --timeout 300";
  runAs = user: "${pkgs.util-linux}/bin/runuser -u ${user} --";
in
pkgs.testers.runNixOSTest {
  name = "nix-control-manager-helper";

  nodes.machine = { pkgs, ... }: {
    imports = [ ncmModule ];

    virtualisation.memorySize = 2048;
    virtualisation.writableStore = true;
    nix.nixPath = [ "nixpkgs=${pkgs.path}" ];

    users.users.ncm-denied.isNormalUser = true;
    users.users.ncm-authorized.isNormalUser = true;

    environment.systemPackages = [ ncmPackage pkgs.jq ];

    services.nix-control-manager-helper = {
      enable = true;
      inherit fixtureRoot;
      allowedUsers = [ "ncm-denied" "ncm-authorized" ];
      validationTimeout = 300;
    };

    security.polkit.extraConfig = ''
      // Test-only authorization inside the disposable VM.
      polkit.addRule(function(action, subject) {
        if (action.id == "org.nixos.nix-control-manager.apply-validated-plan" &&
            subject.user == "ncm-authorized") {
          return polkit.Result.YES;
        }
      });
    '';

    systemd.services.ncm-fixture-setup = {
      description = "Prepare the disposable NCM integration fixture";
      wantedBy = [ "multi-user.target" ];
      before = [ "nix-control-manager-helper.service" ];
      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
      };
      script = ''
        install -d -m 0755 ${fixtureRoot}
        install -m 0644 ${fixtureConfiguration} ${fixtureRoot}/configuration.nix
        printf '%s\n' 'nix-control-manager-transaction-fixture-v1' \
          > ${fixtureRoot}/.ncm-transaction-fixture
        chmod 0644 ${fixtureRoot}/.ncm-transaction-fixture
      '';
    };

    systemd.services.nix-control-manager-helper = {
      requires = [ "ncm-fixture-setup.service" ];
      after = [ "ncm-fixture-setup.service" ];
    };
  };

  testScript = ''
    from datetime import timedelta
    import json

    long_timeout = timedelta(seconds=300)

    machine.start()
    machine.wait_for_unit("multi-user.target")
    machine.wait_for_unit("ncm-fixture-setup.service")
    machine.wait_for_unit("nix-control-manager-helper.socket")

    machine.succeed("test -S ${socketPath}")
    t.assertEqual(machine.succeed("stat -c %a ${socketPath}").strip(), "660")
    t.assertEqual(machine.succeed("stat -c %G ${socketPath}").strip(), "nix-control-manager")
    machine.succeed("test -e /etc/polkit-1/actions/org.nixos.nix-control-manager.policy")

    capabilities = json.loads(machine.succeed(
        "${runAs "ncm-denied"} ${client} capabilities"
    ))
    t.assertEqual(capabilities["status"], "ok")
    t.assertTrue(capabilities["result"]["targets"][0]["fixtureOnly"])
    t.assertFalse(capabilities["result"]["activationEnabled"])
    machine.wait_for_unit("nix-control-manager-helper.service")

    t.assertEqual(
        machine.succeed(
            "systemctl show nix-control-manager-helper.service -p User --value"
        ).strip(),
        "root",
    )
    t.assertEqual(
        machine.succeed(
            "systemctl show nix-control-manager-helper.service -p ProtectSystem --value"
        ).strip(),
        "strict",
    )

    original_hash = machine.succeed("sha256sum ${fixtureRoot}/configuration.nix").split()[0]
    denied_validation = json.loads(machine.succeed(
        "${runAs "ncm-denied"} ${client} validate-plan "
        "--target fixture --config-root ${fixtureRoot}",
        timeout=long_timeout,
    ))
    t.assertEqual(denied_validation["status"], "ok")
    denied_result = denied_validation["result"]
    denied_command = (
        "${runAs "ncm-denied"} ${client} apply-plan --target fixture "
        f"--plan-fingerprint {denied_result['planFingerprint']} "
        f"--receipt={denied_result['validationReceipt']} > /tmp/denied.json"
    )
    denied_status, _ = machine.execute(denied_command, timeout=long_timeout)
    t.assertEqual(denied_status, 2)
    denied_apply = json.loads(machine.succeed("cat /tmp/denied.json"))
    t.assertEqual(denied_apply["status"], "denied")
    t.assertEqual(
        machine.succeed("sha256sum ${fixtureRoot}/configuration.nix").split()[0],
        original_hash,
    )

    authorized_validation = json.loads(machine.succeed(
        "${runAs "ncm-authorized"} ${client} validate-plan "
        "--target fixture --config-root ${fixtureRoot}",
        timeout=long_timeout,
    ))
    t.assertEqual(authorized_validation["status"], "ok")
    authorized_result = authorized_validation["result"]
    authorized_apply = json.loads(machine.succeed(
        "${runAs "ncm-authorized"} ${client} apply-plan --target fixture "
        f"--plan-fingerprint {authorized_result['planFingerprint']} "
        f"--receipt={authorized_result['validationReceipt']}",
        timeout=long_timeout,
    ))
    t.assertEqual(authorized_apply["status"], "ok")
    t.assertEqual(authorized_apply["result"]["state"], "committed")
    t.assertFalse(authorized_apply["result"]["activationEnabled"])
    t.assertGreater(authorized_apply["result"]["filesWritten"], 0)

    plan = json.loads(machine.succeed(
        "${runAs "ncm-authorized"} ${ncmPackage}/bin/ncm plan-adoption "
        "--config-root ${fixtureRoot} --json"
    ))
    t.assertEqual(plan["status"], "no-changes")
    machine.succeed(
        "grep -R -F '\"state\": \"committed\"' "
        "/var/lib/nix-control-manager/transactions/*/manifest.json"
    )
    machine.succeed("systemctl is-active --quiet nix-control-manager-helper.service")
  '';
}
