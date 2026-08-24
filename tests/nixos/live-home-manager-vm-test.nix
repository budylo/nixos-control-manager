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
    environment.systemPackages = [ ncmPackage pkgs.curl pkgs.jq ];

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

    systemd.services.ncm-live-home-ui = {
      description = "Nix Control Manager live Home Manager UI test server";
      path = [ pkgs.nix ];
      wantedBy = [ "multi-user.target" ];
      requires = [
        "ncm-live-home-setup.service"
        "nix-control-manager-helper.socket"
      ];
      after = [
        "ncm-live-home-setup.service"
        "nix-control-manager-helper.socket"
      ];
      environment.PYTHONUNBUFFERED = "1";
      serviceConfig = {
        User = "hm-authorized";
        RuntimeDirectory = "ncm-live-home-ui";
        WorkingDirectory = "/run/ncm-live-home-ui";
        ExecStart = ''
          ${ncmPackage}/bin/ncm serve \
            --state /run/ncm-live-home-ui/state.json \
            --user-state /run/ncm-live-home-ui/user-state.local.json \
            --output /run/ncm-live-home-ui/managed.nix \
            --config-root /etc/nixos \
            --home-manager-root /etc/nixos \
            --helper-socket ${socketPath} \
            --helper-target live-home \
            --validation-timeout 300 \
            --port 8765
        '';
      };
    };
  };

  testScript = ''
    from datetime import timedelta
    import json
    import shlex

    timeout = timedelta(seconds=300)

    machine.start()
    machine.wait_for_unit("multi-user.target")
    machine.wait_for_unit("ncm-live-home-setup.service")
    machine.wait_for_unit("nix-control-manager-helper.socket")
    machine.wait_for_unit("ncm-live-home-ui.service")
    machine.wait_for_open_port(8765)

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
        f"--receipt={denied_result['validationReceipt']} > /tmp/hm-denied.json"
    )
    denied_status, _ = machine.execute(denied_command, timeout=timeout)
    t.assertEqual(denied_status, 2)
    t.assertEqual(json.loads(machine.succeed("cat /tmp/hm-denied.json"))["status"], "denied")
    t.assertEqual(
        machine.succeed("sha256sum /etc/nixos/home.nix").split()[0],
        original_hash,
    )
    machine.fail("test -e /etc/nixos/ncm")

    token = json.loads(machine.succeed(
        "curl --fail --silent http://127.0.0.1:8765/api/config"
    ))["token"]

    def ui_post(path, payload):
        return json.loads(machine.succeed(
            "curl --fail-with-body --silent --show-error "
            f"-H {shlex.quote('X-NCM-Token: ' + token)} "
            "-H 'Content-Type: application/json' "
            f"--data {shlex.quote(json.dumps(payload))} "
            f"http://127.0.0.1:8765{path}",
            timeout=timeout,
        ))

    candidate = {
        "username": "hm-authorized",
        "integration": "standalone",
        "packages": ["git"],
    }
    plan = ui_post("/api/home-manager/adoption-plan", candidate)
    t.assertEqual(plan["status"], "ready")
    t.assertIn("ncm/managed-home-hm-authorized.nix", plan["combinedDiff"])

    local_validation = ui_post("/api/home-manager/validate-adoption", candidate)
    t.assertEqual(local_validation["status"], "passed")
    t.assertTrue(local_validation["workingCopyRemoved"])

    prepared = ui_post("/api/helper/home-manager/validate", candidate)
    t.assertEqual(prepared["status"], "passed")
    t.assertTrue(prepared["confirmationRequired"])
    t.assertTrue(prepared["liveWriteEnabled"])
    t.assertFalse(prepared["activationEnabled"])
    t.assertNotIn("validationReceipt", prepared)

    applied = ui_post("/api/helper/home-manager/apply", {
        "intentId": prepared["intentId"],
        "planFingerprint": prepared["planFingerprint"],
        "confirmed": True,
    })
    t.assertEqual(applied["state"], "committed")
    t.assertFalse(applied["fixtureOnly"])
    t.assertTrue(applied["liveWriteEnabled"])
    t.assertTrue(applied["authorizedByPolkit"])
    t.assertFalse(applied["activationEnabled"])
    t.assertFalse(applied["homeManagerActivationEnabled"])
    t.assertFalse(applied["switchEnabled"])
    machine.succeed("test -f /etc/nixos/ncm/user-state.json")
    machine.succeed("grep -F 'pkgs.git' /etc/nixos/ncm/managed-home-hm-authorized.nix")
    t.assertEqual(machine.succeed("readlink -f /run/current-system").strip(), current_before)
    machine.succeed("grep -R -F '\"fixtureOnly\": false' ${journalRoot}/*/manifest.json")
  '';
}
