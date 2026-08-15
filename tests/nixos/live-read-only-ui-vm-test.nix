{ pkgs, ncmPackage, ncmModule }:

let
  liveConfigurationModule = { ... }: {
    imports = [ ];
    boot.loader.grub.devices = [ "nodev" ];
    fileSystems."/".device = "none";
    fileSystems."/".fsType = "tmpfs";
    networking.hostName = "ncm-live-ui-vm";
    system.stateVersion = "26.05";
  };
  liveConfiguration = pkgs.writeText "live-configuration.nix" ''
    { ... }:

    {
      imports = [
      ];

      boot.loader.grub.devices = [ "nodev" ];
      fileSystems."/".device = "none";
      fileSystems."/".fsType = "tmpfs";
      networking.hostName = "ncm-live-ui-vm";
      system.stateVersion = "26.05";
    }
  '';
  # Pre-register the semantically equivalent system closure in the offline
  # guest store. The runtime candidate only adds an empty managed module, so
  # any remaining top-level derivation is small while all build inputs are
  # already available without weakening VM network isolation.
  candidateSystem = (import (pkgs.path + "/nixos") {
    configuration = liveConfigurationModule;
    system = pkgs.stdenv.hostPlatform.system;
  }).system;
  homeManagerHome = pkgs.writeText "ncm-ui-home.nix" ''
    { ... }:

    {
      home.username = "ncm-ui";
      home.stateVersion = "26.05";
    }
  '';
  # Reattach only direct store-path context inside the copied fixture. Using
  # derivation context here would pull complete Bash/Coreutils build closures
  # into the offline guest merely to create a tiny activationPackage directory.
  homeManagerRuntime = builtins.unsafeDiscardStringContext pkgs.bash.outPath;
  homeManagerCoreutils = builtins.unsafeDiscardStringContext pkgs.coreutils.outPath;
  homeManagerFlake = pkgs.writeText "ncm-ui-home-flake.nix" ''
    {
      outputs = { self }:
        let
          pkgs = {
            git = "fixture-git";
          };
          home = import ./home.nix { inherit pkgs; config = { }; };
          managed = import (builtins.head home.imports) { inherit pkgs; };
          runtime = builtins.appendContext "${homeManagerRuntime}" {
            "${homeManagerRuntime}" = { path = true; };
          };
          coreutils = builtins.appendContext "${homeManagerCoreutils}" {
            "${homeManagerCoreutils}" = { path = true; };
          };
          activationPackage =
            assert managed.home.packages == [ pkgs.git ];
            builtins.derivation {
              name = "ncm-home-ui-preview";
              system = "${pkgs.stdenv.hostPlatform.system}";
              builder = "''${runtime}/bin/sh";
              args = [ "-c" "''${coreutils}/bin/mkdir -p \"$out\"; echo 'Home Manager build-preview only' > \"$out/marker\"" ];
              preferLocalBuild = true;
              allowSubstitutes = false;
            };
        in
        {
          homeConfigurations.ncm-ui = { inherit activationPackage; };
        };
    }
  '';
  homeManagerRoot = "/var/lib/ncm-ui/.config/home-manager";
  socketPath = "/run/nix-control-manager/helper.sock";
  uiPort = 8765;
  client = "${ncmPackage}/bin/ncm-helper-client --socket ${socketPath} --timeout 300";
  runAsUi = "${pkgs.util-linux}/bin/runuser -u ncm-ui --";
  curl = "${pkgs.curl}/bin/curl";
  jq = "${pkgs.jq}/bin/jq";
in
pkgs.testers.runNixOSTest {
  name = "nix-control-manager-live-read-only-ui";

  nodes.machine = { pkgs, ... }: {
    imports = [ ncmModule ];

    virtualisation.memorySize = 2048;
    virtualisation.diskSize = 4096;
    virtualisation.writableStore = true;
    virtualisation.additionalPaths = [ candidateSystem ];
    nix.nixPath = [ "nixpkgs=${pkgs.path}" ];

    users.groups.ncm-ui = { };
    users.users.ncm-ui = {
      isSystemUser = true;
      group = "ncm-ui";
    };

    environment.systemPackages = [ ncmPackage pkgs.curl pkgs.jq pkgs.util-linux ];

    services.nix-control-manager-helper = {
      enable = true;
      mode = "live-read-only";
      targetId = "live";
      allowedUsers = [ "ncm-ui" ];
      validationTimeout = 300;
    };

    security.polkit.extraConfig = ''
      // Any appearance of this marker means a read-only operation crossed the
      // dispatcher boundary and incorrectly reached Polkit.
      polkit.addRule(function(action, subject) {
        if (action.id == "org.nixos.nix-control-manager.preview-activation"
            && subject.user == "ncm-ui") {
          return polkit.Result.YES;
        }
        if (action.id.indexOf("org.nixos.nix-control-manager.") == 0) {
          polkit.log("NCM_LIVE_READ_ONLY_REACHED_POLKIT");
          return polkit.Result.NO;
        }
      });
    '';

    systemd.services.ncm-live-configuration-setup = {
      description = "Prepare disposable live /etc/nixos for NCM VM testing";
      wantedBy = [ "multi-user.target" ];
      before = [ "nix-control-manager-helper.service" "ncm-ui.service" ];
      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
      };
      script = ''
        install -d -m 0755 /etc/nixos
        install -m 0644 ${liveConfiguration} /etc/nixos/configuration.nix
        install -d -m 0755 -o ncm-ui -g ncm-ui ${homeManagerRoot}
        install -m 0644 ${homeManagerHome} ${homeManagerRoot}/home.nix
        install -m 0644 ${homeManagerFlake} ${homeManagerRoot}/flake.nix
      '';
    };

    systemd.services.nix-control-manager-helper = {
      requires = [ "ncm-live-configuration-setup.service" ];
      after = [ "ncm-live-configuration-setup.service" ];
    };

    systemd.services.ncm-ui = {
      description = "Unprivileged Nix Control Manager UI test service";
      wantedBy = [ "multi-user.target" ];
      requires = [
        "ncm-live-configuration-setup.service"
        "nix-control-manager-helper.socket"
      ];
      after = [
        "ncm-live-configuration-setup.service"
        "nix-control-manager-helper.socket"
      ];
      environment = {
        PYTHONUNBUFFERED = "1";
        HOME = "/var/lib/ncm-ui";
        NIX_PATH = "nixpkgs=${pkgs.path}";
      };
      path = [ pkgs.nix ];
      serviceConfig = {
        Type = "simple";
        User = "ncm-ui";
        Group = "ncm-ui";
        StateDirectory = "ncm-ui";
        StateDirectoryMode = "0700";
        WorkingDirectory = "/var/lib/ncm-ui";
        ExecStart = "${ncmPackage}/bin/ncm serve --state /var/lib/ncm-ui/state.json --user-state /var/lib/ncm-ui/user-state.json --output /var/lib/ncm-ui/managed.nix --config-root /etc/nixos --home-manager-root ${homeManagerRoot} --port ${toString uiPort} --helper-socket ${socketPath} --helper-target live --validation-timeout 300 --build-timeout 300";
        Restart = "on-failure";
        RestartSec = "1s";
        NoNewPrivileges = true;
        PrivateTmp = true;
        ProtectHome = true;
      };
    };
  };

  testScript = ''
    from datetime import timedelta
    import json
    import time

    long_timeout = timedelta(seconds=300)
    base_url = "http://127.0.0.1:${toString uiPort}"
    fake_fingerprint = "1" * 64
    fake_receipt = "A" * 32

    machine.start()
    machine.wait_for_unit("multi-user.target")
    machine.wait_for_unit("ncm-live-configuration-setup.service")
    machine.wait_for_unit("nix-control-manager-helper.socket")
    machine.wait_for_unit("ncm-ui.service")
    machine.wait_for_open_port(${toString uiPort})
    machine.succeed(
        "systemctl show ncm-ui.service -p ExecStart --value | "
        "grep -F -- '--state /var/lib/ncm-ui/state.json'"
    )
    machine.succeed(
        "systemctl show ncm-ui.service -p ExecStart --value | "
        "grep -F -- '--output /var/lib/ncm-ui/managed.nix'"
    )
    machine.succeed(
        "systemctl show ncm-ui.service -p ExecStart --value | "
        "grep -F -- '--build-timeout 300'"
    )
    machine.succeed(
        "systemctl show ncm-ui.service -p ExecStart --value | "
        "grep -F -- '--home-manager-root ${homeManagerRoot}'"
    )

    machine.succeed("test -S ${socketPath}")
    machine.succeed("test -f /etc/nixos/configuration.nix")
    machine.fail("test -e /etc/nixos/.ncm-transaction-fixture")
    machine.succeed("grep -F 'id=\"validateHelperButton\"' <(${curl} -fsS " + base_url + "/)")
    machine.succeed("grep -F 'id=\"startBuildPreviewButton\"' <(${curl} -fsS " + base_url + "/)")
    machine.succeed("grep -F 'id=\"cancelBuildPreviewButton\"' <(${curl} -fsS " + base_url + "/)")
    machine.succeed("grep -F 'id=\"startHomeBuildPreviewButton\"' <(${curl} -fsS " + base_url + "/)")
    machine.succeed("grep -F 'id=\"cancelHomeBuildPreviewButton\"' <(${curl} -fsS " + base_url + "/)")
    machine.succeed("grep -F 'id=\"runActivationPreviewButton\"' <(${curl} -fsS " + base_url + "/)")
    machine.fail("grep -F 'id=\"applyHelperButton\"' <(${curl} -fsS " + base_url + "/)")

    helper_status = json.loads(machine.succeed("${curl} -fsS " + base_url + "/api/helper"))
    t.assertTrue(helper_status["available"])
    t.assertTrue(helper_status["readOnly"])
    t.assertFalse(helper_status["applyEnabled"])
    t.assertFalse(helper_status["recoveryEnabled"])
    t.assertFalse(helper_status["activationEnabled"])
    t.assertTrue(helper_status["dryActivatePreviewEnabled"])
    t.assertEqual(helper_status["targetId"], "live")
    machine.wait_for_unit("nix-control-manager-helper.service")

    t.assertEqual(
        machine.succeed(
            "systemctl show nix-control-manager-helper.service -p ReadWritePaths --value"
        ).strip(),
        "",
    )
    t.assertEqual(
        machine.succeed(
            "systemctl show nix-control-manager-helper.service -p StateDirectory --value"
        ).strip(),
        "",
    )
    t.assertIn(
        "/etc/nixos",
        machine.succeed(
            "systemctl show nix-control-manager-helper.service -p ReadOnlyPaths --value"
        ),
    )
    t.assertEqual(
        machine.succeed(
            "systemctl show nix-control-manager-helper.service -p CapabilityBoundingSet --value"
        ).strip(),
        "",
    )
    machine.succeed(
        "systemctl show nix-control-manager-helper.service -p Environment --value | "
        "grep -F 'HOME=/tmp'"
    )

    helper_pid = machine.succeed(
        "systemctl show nix-control-manager-helper.service -p MainPID --value"
    ).strip()
    machine.fail(
        f"${pkgs.util-linux}/bin/nsenter -t {helper_pid} -m -- "
        "/run/current-system/sw/bin/touch /etc/nixos/write-probe"
    )
    machine.fail("test -e /etc/nixos/write-probe")

    original_hashes = machine.succeed(
        "find /etc/nixos -type f -print0 | sort -z | xargs -0 sha256sum"
    )
    token = machine.succeed(
        "${curl} -fsS " + base_url + "/api/config | ${jq} -r .token"
    ).strip()
    unauthorized_code = machine.succeed(
        "${curl} -sS -o /tmp/unauthorized.json -w '%{http_code}' "
        "-X POST " + base_url + "/api/helper/validate-adoption"
    ).strip()
    t.assertEqual(unauthorized_code, "403")

    home_inspection = json.loads(machine.succeed(
        "${curl} -fsS " + base_url + "/api/home-manager"
    ))
    t.assertEqual(home_inspection["status"], "detected")
    t.assertIn("standalone", home_inspection["integrations"])
    t.assertTrue(any(
        user["name"] == "ncm-ui" and user["integration"] == "standalone"
        for user in home_inspection["users"]
    ))
    t.assertFalse(home_inspection["writeEnabled"])
    t.assertFalse(home_inspection["activationEnabled"])

    home_payload = json.dumps({
        "username": "ncm-ui",
        "integration": "standalone",
        "packages": ["git"],
    })
    home_source_hashes = machine.succeed(
        "find ${homeManagerRoot} -type f -print0 | sort -z | xargs -0 sha256sum"
    )
    machine.fail("test -e ${homeManagerRoot}/ncm")
    machine.fail("test -e /var/lib/ncm-ui/user-state.json")
    machine.fail("test -e /nix/var/nix/profiles/per-user/ncm-ui/home-manager")

    home_plan = json.loads(machine.succeed(
        "${curl} -fsS -X POST "
        f"-H 'X-NCM-Token: {token}' -H 'Content-Type: application/json' "
        f"--data '{home_payload}' "
        + base_url + "/api/home-manager/adoption-plan"
    ))
    t.assertEqual(home_plan["status"], "ready")
    t.assertTrue(home_plan["safeToValidate"])
    t.assertFalse(home_plan["safeToApply"])
    t.assertFalse(home_plan["writeEnabled"])
    t.assertFalse(home_plan["activationEnabled"])
    t.assertEqual(len(home_plan["changes"]), 3)

    home_validation = json.loads(machine.succeed(
        "${curl} -fsS --max-time 300 -X POST "
        f"-H 'X-NCM-Token: {token}' -H 'Content-Type: application/json' "
        f"--data '{home_payload}' "
        + base_url + "/api/home-manager/validate-adoption",
        timeout=long_timeout,
    ))
    if home_validation["status"] != "passed":
        print("Home Manager validation response:", json.dumps(home_validation, indent=2))
    t.assertEqual(home_validation["status"], "passed")
    t.assertTrue(home_validation["workingCopyRemoved"])
    t.assertEqual(len(home_validation["planFingerprint"]), 64)
    t.assertFalse(home_validation["writeEnabled"])
    t.assertFalse(home_validation["buildEnabled"])
    t.assertFalse(home_validation["activationEnabled"])

    home_build_payload = json.dumps({
        "username": "ncm-ui",
        "integration": "standalone",
        "packages": ["git"],
        "planFingerprint": home_validation["planFingerprint"],
    })
    unauthorized_home_build = machine.succeed(
        "${curl} -sS -o /tmp/unauthorized-home-build.json -w '%{http_code}' "
        "-X POST -H 'Content-Type: application/json' "
        f"--data '{home_build_payload}' "
        + base_url + "/api/home-manager/build-preview"
    ).strip()
    t.assertEqual(unauthorized_home_build, "403")

    home_build = json.loads(machine.succeed(
        "${curl} -fsS -X POST "
        f"-H 'X-NCM-Token: {token}' -H 'Content-Type: application/json' "
        f"--data '{home_build_payload}' "
        + base_url + "/api/home-manager/build-preview"
    ))
    home_build_events = list(home_build["events"])
    home_build_cursor = home_build["nextCursor"]
    while home_build["cancellable"]:
        time.sleep(0.5)
        home_build = json.loads(machine.succeed(
            "${curl} -fsS " + base_url
            + f"/api/home-manager/build-preview/{home_build['jobId']}?after={home_build_cursor}",
            timeout=long_timeout,
        ))
        home_build_events.extend(home_build["events"])
        home_build_cursor = home_build["nextCursor"]
    if home_build["status"] != "passed":
        print("Home Manager build response:", json.dumps(home_build, indent=2))
        print("Home Manager build events:", json.dumps(home_build_events, indent=2))
    t.assertEqual(home_build["status"], "passed")
    t.assertEqual(home_build["workflow"], "home-manager")
    t.assertEqual(home_build["username"], "ncm-ui")
    t.assertEqual(home_build["integration"], "standalone")
    t.assertEqual(
        home_build["expectedPlanFingerprint"],
        home_validation["planFingerprint"],
    )
    t.assertEqual(home_build["planFingerprint"], home_validation["planFingerprint"])
    t.assertFalse(home_build["privileged"])
    t.assertFalse(home_build["configurationWriteEnabled"])
    t.assertTrue(home_build["nixStoreWriteExpected"])
    t.assertFalse(home_build["activationEnabled"])
    t.assertFalse(home_build["homeManagerActivationEnabled"])
    t.assertFalse(home_build["testEnabled"])
    t.assertFalse(home_build["switchEnabled"])
    t.assertFalse(home_build["flakeInputMutationEnabled"])
    t.assertFalse(home_build["lockFileWriteEnabled"])
    t.assertFalse(home_build["activationPreviewReady"])
    t.assertTrue(home_build["workingCopyRemoved"])
    t.assertEqual(len(home_build["outputPaths"]), 1)
    t.assertEqual(home_build["activationPackagePath"], home_build["outputPaths"][0])
    t.assertIn("--no-link", home_build["command"])
    t.assertIn("--no-write-lock-file", home_build["command"])
    t.assertIn(
        '.#homeConfigurations."ncm-ui".activationPackage',
        home_build["command"],
    )
    t.assertNotIn("home-manager", home_build["command"][0])
    t.assertNotIn("switch", home_build["command"])
    t.assertTrue(any(event["stream"] == "command" for event in home_build_events))
    t.assertEqual(
        machine.succeed("cat " + home_build["activationPackagePath"] + "/marker").strip(),
        "Home Manager build-preview only",
    )
    latest_home_build = json.loads(machine.succeed(
        "${curl} -fsS " + base_url + "/api/home-manager/build-preview"
    ))
    t.assertEqual(latest_home_build["jobId"], home_build["jobId"])
    t.assertEqual(latest_home_build["status"], "passed")
    t.assertEqual(
        machine.succeed(
            "find ${homeManagerRoot} -type f -print0 | sort -z | xargs -0 sha256sum"
        ),
        home_source_hashes,
    )
    machine.fail("test -e ${homeManagerRoot}/ncm")
    machine.fail("test -e /var/lib/ncm-ui/user-state.json")
    machine.fail("test -e /var/lib/ncm-ui/result")
    machine.fail("test -e /nix/var/nix/profiles/per-user/ncm-ui/home-manager")

    validation = json.loads(machine.succeed(
        "${curl} -fsS --max-time 300 -X POST "
        f"-H 'X-NCM-Token: {token}' "
        + base_url + "/api/helper/validate-adoption",
        timeout=long_timeout,
    ))
    if validation["status"] != "passed":
        print("live read-only UI validation response:", json.dumps(validation, indent=2))
    t.assertEqual(validation["source"], "system-helper")
    t.assertEqual(validation["status"], "passed")
    t.assertTrue(validation["readOnly"])
    t.assertFalse(validation["applyEnabled"])
    t.assertFalse(validation["recoveryEnabled"])
    t.assertFalse(validation["activationEnabled"])
    t.assertFalse(validation["validationReceiptIssued"])
    t.assertTrue(validation["workingCopyRemoved"])
    t.assertGreaterEqual(len(validation["checks"]), 2)
    t.assertTrue(all(check["status"] == "passed" for check in validation["checks"]))

    generation_before = machine.succeed("readlink -f /run/current-system").strip()
    build = json.loads(machine.succeed(
        "${curl} -fsS -X POST "
        f"-H 'X-NCM-Token: {token}' "
        + base_url + "/api/build-preview"
    ))
    build_events = list(build["events"])
    build_cursor = build["nextCursor"]
    while build["cancellable"]:
        time.sleep(0.5)
        build = json.loads(machine.succeed(
            "${curl} -fsS " + base_url
            + f"/api/build-preview/{build['jobId']}?after={build_cursor}",
            timeout=long_timeout,
        ))
        build_events.extend(build["events"])
        build_cursor = build["nextCursor"]
    if build["status"] != "passed":
        print("live UI build-preview response:", json.dumps(build, indent=2))
        interesting = [
            event for event in build_events
            if any(word in event["message"].lower() for word in (
                "error", "failed", "permission", "space", "cannot", "denied"
            ))
        ]
        print("live UI build-preview errors:", json.dumps(interesting[-100:], indent=2))
    t.assertEqual(build["status"], "passed")
    t.assertFalse(build["privileged"])
    t.assertFalse(build["configurationWriteEnabled"])
    t.assertFalse(build["activationEnabled"])
    t.assertFalse(build["testEnabled"])
    t.assertFalse(build["switchEnabled"])
    t.assertTrue(build["workingCopyRemoved"])
    t.assertTrue(build["outputPaths"])
    t.assertTrue(build["impactAvailable"])
    t.assertIn("diff-closures", build["impactCommand"])
    t.assertFalse(build["dryActivateExecuted"])
    t.assertTrue(build["activationPreviewReady"])
    t.assertIn("--no-out-link", build["command"])
    t.assertNotIn("nixos-rebuild", " ".join(build["command"]))
    t.assertTrue(any(event["stream"] == "command" for event in build_events))
    t.assertEqual(
        machine.succeed("readlink -f /run/current-system").strip(),
        generation_before,
    )
    machine.fail("test -e /var/lib/ncm-ui/result")

    activation_preview = json.loads(machine.succeed(
        "${curl} -fsS --max-time 300 -X POST "
        f"-H 'X-NCM-Token: {token}' "
        + base_url + "/api/helper/activation-preview",
        timeout=long_timeout,
    ))
    print("activation preview response:", json.dumps(activation_preview, indent=2))
    t.assertEqual(activation_preview["status"], "passed")
    t.assertEqual(activation_preview["systemPath"], build["outputPaths"][0])
    t.assertTrue(activation_preview["dryActivateExecuted"])
    t.assertTrue(activation_preview["authorizedByPolkit"])
    t.assertTrue(activation_preview["sourceFilesUnchanged"])
    t.assertTrue(activation_preview["currentSystemUnchanged"])
    t.assertFalse(activation_preview["configurationWriteEnabled"])
    t.assertFalse(activation_preview["activationEnabled"])
    t.assertFalse(activation_preview["testEnabled"])
    t.assertFalse(activation_preview["switchEnabled"])
    t.assertTrue(activation_preview["reportIncomplete"])
    t.assertEqual(activation_preview["command"][-1], "dry-activate")
    t.assertNotIn("test", activation_preview["command"])
    t.assertNotIn("switch", activation_preview["command"])
    t.assertEqual(
        machine.succeed("readlink -f /run/current-system").strip(),
        generation_before,
    )

    t.assertEqual(
        machine.succeed(
            "find /etc/nixos -type f -print0 | sort -z | xargs -0 sha256sum"
        ),
        original_hashes,
    )
    machine.fail("test -e /var/lib/nix-control-manager/transactions")

    apply_command = (
        "${runAsUi} ${client} apply-plan --target live "
        f"--plan-fingerprint {fake_fingerprint} --receipt {fake_receipt} "
        "> /tmp/live-apply.json"
    )
    apply_status, _ = machine.execute(apply_command, timeout=long_timeout)
    t.assertEqual(apply_status, 2)
    apply_result = json.loads(machine.succeed("cat /tmp/live-apply.json"))
    t.assertEqual(apply_result["error"]["code"], "operation-disabled")

    recovery_command = (
        "${runAsUi} ${client} recover-transaction --target live "
        "--transaction-id aaaaaaaaaaaaaaaaaaaaaaaa > /tmp/live-recovery.json"
    )
    recovery_status, _ = machine.execute(recovery_command, timeout=long_timeout)
    t.assertEqual(recovery_status, 2)
    recovery_result = json.loads(machine.succeed("cat /tmp/live-recovery.json"))
    t.assertEqual(recovery_result["error"]["code"], "operation-disabled")
    machine.fail(
        "journalctl -u polkit.service --no-pager | "
        "grep -F NCM_LIVE_READ_ONLY_REACHED_POLKIT"
    )
    machine.succeed("systemctl is-active --quiet ncm-ui.service")
    machine.succeed("systemctl is-active --quiet nix-control-manager-helper.service")
  '';
}
