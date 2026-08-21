{ pkgs, ncmPackage, ncmModule }:

let
  candidateInstrumentation = ./live-test-candidate-instrumentation.nix;

  candidateConfigurationModule = { ... }: {
    imports = [ candidateInstrumentation ];
    boot.loader.grub.devices = [ "nodev" ];
    fileSystems."/".device = "none";
    fileSystems."/".fsType = "tmpfs";
    networking.hostName = "ncm-live-test-candidate";
    system.stateVersion = "26.05";
  };

  candidateSystem = (import (pkgs.path + "/nixos") {
    configuration = candidateConfigurationModule;
    system = pkgs.stdenv.hostPlatform.system;
  }).system;

  recoveryTools = pkgs.buildEnv {
    name = "ncm-live-test-recovery-tools";
    paths = [ pkgs.bash pkgs.coreutils pkgs.findutils pkgs.gnugrep pkgs.systemd ];
  };

  recoverySystem = pkgs.runCommand "ncm-live-test-recovery-system" { } ''
    mkdir -p "$out/bin"
    ln -s ${recoveryTools} "$out/sw"
    cat > "$out/bin/switch-to-configuration" <<'SCRIPT'
#!@shell@
set -eu

case "$1" in
  test)
    @coreutils@/bin/ln -sfn '@recovery@' /run/current-system
    echo recovered > /run/ncm-live-test-recovered
    ;;
  *)
    echo "unsupported VM-only recovery mode: $1" >&2
    exit 64
    ;;
esac
SCRIPT
    substituteInPlace "$out/bin/switch-to-configuration" \
      --replace-fail '@shell@' '${pkgs.runtimeShell}' \
      --replace-fail '@coreutils@' '${pkgs.coreutils}' \
      --replace-fail '@recovery@' "$out"
    chmod 0755 "$out/bin/switch-to-configuration"
  '';

  liveConfiguration = pkgs.writeText "live-test-configuration.nix" ''
    { lib, ... }:

    {
      imports = [
        ${candidateInstrumentation}
      ];

      boot.loader.grub.devices = [ "nodev" ];
      fileSystems."/".device = "none";
      fileSystems."/".fsType = "tmpfs";
      networking.hostName = "ncm-live-test-candidate";
      system.stateVersion = "26.05";
    }
  '';

  socketPath = "/run/nix-control-manager/helper.sock";
  journalRoot = "/var/lib/nix-control-manager/test-activations";
  client = "${ncmPackage}/bin/ncm-helper-client --socket ${socketPath} --timeout 300";
  runAsUser = "${pkgs.util-linux}/bin/runuser -u ncm-test --";
  jq = "${pkgs.jq}/bin/jq";
in
pkgs.testers.runNixOSTest {
  name = "nix-control-manager-live-test-recovery";

  nodes.machine = { pkgs, ... }: {
    imports = [ ncmModule ];

    virtualisation.memorySize = 2048;
    virtualisation.diskSize = 4096;
    virtualisation.writableStore = true;
    virtualisation.additionalPaths = [ candidateSystem recoverySystem ];
    nix.nixPath = [ "nixpkgs=${pkgs.path}" ];

    users.groups.ncm-test = { };
    users.users.ncm-test = {
      isSystemUser = true;
      group = "ncm-test";
    };

    environment.systemPackages = [ ncmPackage pkgs.jq pkgs.util-linux ];

    services.nix-control-manager-helper = {
      enable = true;
      mode = "live-test";
      targetId = "live-test";
      allowedUsers = [ "ncm-test" ];
      validationTimeout = 300;
      testActivationTimeout = 30;
    };

    security.polkit.extraConfig = ''
      polkit.addRule(function(action, subject) {
        if ((action.id == "org.nixos.nix-control-manager.preview-activation"
             || action.id == "org.nixos.nix-control-manager.test-activation"
             || action.id == "org.nixos.nix-control-manager.recover-test-activation")
            && subject.user == "ncm-test") {
          return polkit.Result.YES;
        }
        if (action.id.indexOf("org.nixos.nix-control-manager.") == 0) {
          polkit.log("NCM_LIVE_TEST_UNEXPECTED_POLKIT_ACTION");
          return polkit.Result.NO;
        }
      });
    '';

    systemd.services.ncm-live-test-configuration-setup = {
      description = "Prepare disposable live-test /etc/nixos";
      wantedBy = [ "multi-user.target" ];
      before = [ "nix-control-manager-helper.service" ];
      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
      };
      script = ''
        install -d -m 0755 /etc/nixos
        install -m 0644 ${liveConfiguration} /etc/nixos/configuration.nix
        install -d -m 0755 /nix/var/nix/profiles
        ln -sfn ${recoverySystem} /run/current-system
        ln -sfn ${recoverySystem} /nix/var/nix/profiles/system
      '';
    };

    systemd.services.nix-control-manager-helper = {
      requires = [ "ncm-live-test-configuration-setup.service" ];
      after = [ "ncm-live-test-configuration-setup.service" ];
    };
  };

  testScript = ''
    from datetime import timedelta
    import json

    long_timeout = timedelta(seconds=300)
    candidate = "${candidateSystem}"

    machine.start()
    machine.wait_for_unit("multi-user.target")
    machine.wait_for_unit("ncm-live-test-configuration-setup.service")
    machine.wait_for_unit("nix-control-manager-helper.socket")
    machine.succeed("test -S ${socketPath}")
    machine.succeed("test -x " + candidate + "/bin/switch-to-configuration")
    machine.succeed("test -x ${recoverySystem}/bin/switch-to-configuration")

    capabilities = json.loads(machine.succeed(
        "${runAsUser} ${client} capabilities",
        timeout=long_timeout,
    ))
    t.assertEqual(capabilities["status"], "ok")
    target = next(item for item in capabilities["result"]["targets"] if item["targetId"] == "live-test")
    t.assertTrue(target["liveTarget"])
    t.assertTrue(target["readOnly"])
    t.assertFalse(target["applyEnabled"])
    t.assertFalse(target["recoveryEnabled"])
    t.assertTrue(target["testActivationEnabled"])
    t.assertFalse(capabilities["result"]["activationEnabled"])
    t.assertNotIn("switch", capabilities["result"]["operations"])

    machine.wait_for_unit("nix-control-manager-helper.service")
    t.assertIn(
        "/etc/nixos",
        machine.succeed(
            "systemctl show nix-control-manager-helper.service -p ReadOnlyPaths --value"
        ),
    )
    t.assertEqual(
        machine.succeed(
            "systemctl show nix-control-manager-helper.service -p ReadWritePaths --value"
        ).strip(),
        "${journalRoot}",
    )
    t.assertEqual(
        machine.succeed(
            "systemctl show nix-control-manager-helper.service -p CapabilityBoundingSet --value"
        ).strip(),
        "",
    )
    dependencies = machine.succeed(
        "systemctl show nix-control-manager-helper.service -p Requires -p Wants"
    )
    t.assertNotIn(
        "polkit.service",
        next(line for line in dependencies.splitlines() if line.startswith("Requires=")),
    )
    t.assertIn(
        "polkit.service",
        next(line for line in dependencies.splitlines() if line.startswith("Wants=")),
    )
    machine.succeed("test $(stat -c %a ${journalRoot}) = 700")

    source_hashes = machine.succeed(
        "find /etc/nixos -type f -print0 | sort -z | xargs -0 sha256sum"
    )
    previous_runtime = machine.succeed("readlink -f /run/current-system").strip()
    previous_profile = machine.succeed(
        "readlink -f /nix/var/nix/profiles/system"
    ).strip()
    t.assertEqual(previous_runtime, previous_profile)

    validation = json.loads(machine.succeed(
        "${runAsUser} ${client} validate-plan --target live-test "
        "--config-root /etc/nixos",
        timeout=long_timeout,
    ))
    if validation["status"] != "ok":
        print("validation response:", json.dumps(validation, indent=2))
    t.assertEqual(validation["status"], "ok")
    t.assertEqual(validation["result"]["validation"]["status"], "passed")
    fingerprint = validation["result"]["planFingerprint"]

    preview = json.loads(machine.succeed(
        "${runAsUser} ${client} preview-activation --target live-test "
        "--config-root /etc/nixos --system-path " + candidate + " "
        "--plan-fingerprint " + fingerprint,
        timeout=long_timeout,
    ))
    if preview["status"] != "ok":
        print("dry preview response:", json.dumps(preview, indent=2))
    t.assertEqual(preview["status"], "ok")
    t.assertEqual(preview["result"]["status"], "passed")
    t.assertTrue(preview["result"]["testActivationPrepared"])
    receipt = preview["result"]["testReceipt"]
    t.assertEqual(machine.succeed("readlink -f /run/current-system").strip(), previous_runtime)

    activation_command = (
        "${runAsUser} ${client} test-activation --target live-test "
        "--system-path " + candidate + " --plan-fingerprint " + fingerprint
        + " --receipt " + receipt
    )
    activation = json.loads(machine.succeed(activation_command, timeout=long_timeout))
    if activation["status"] != "ok":
        print("test activation response:", json.dumps(activation, indent=2))
    t.assertEqual(activation["status"], "ok")
    result = activation["result"]
    t.assertEqual(result["status"], "active")
    t.assertTrue(result["autoRecoveryScheduled"])
    t.assertFalse(result["switchEnabled"])
    t.assertFalse(result["bootGenerationChanged"])
    session_id = result["sessionId"]
    rollback_unit = result["autoRecoveryUnit"]

    t.assertEqual(machine.succeed("readlink -f /run/current-system").strip(), candidate)
    t.assertEqual(machine.succeed("readlink -f /nix/var/nix/profiles/system").strip(), previous_profile)
    machine.succeed("test -f /run/ncm-live-test-candidate")
    machine.succeed("systemctl is-active --quiet " + rollback_unit + ".timer")
    machine.succeed("test $(stat -c %a ${journalRoot}/" + session_id + ".json) = 600")
    t.assertEqual(
        json.loads(machine.succeed("cat ${journalRoot}/" + session_id + ".json"))["state"],
        "active",
    )

    replay_status, _ = machine.execute(
        activation_command + " > /tmp/replayed-test.json",
        timeout=long_timeout,
    )
    t.assertEqual(replay_status, 2)
    replay = json.loads(machine.succeed("cat /tmp/replayed-test.json"))
    t.assertEqual(replay["error"]["code"], "invalid-receipt")

    machine.wait_until_succeeds(
        "test $(readlink -f /run/current-system) = " + previous_runtime
        + " && ${jq} -e '.state == \"recovered\" and .recoveryExitCode == 0' "
        "${journalRoot}/" + session_id + ".json",
        timeout=90,
    )
    recovered = json.loads(machine.succeed(
        "cat ${journalRoot}/" + session_id + ".json"
    ))
    t.assertEqual(recovered["previousSystemPath"], previous_profile)
    t.assertEqual(recovered["candidateSystemPath"], candidate)
    machine.succeed("test -f /run/ncm-live-test-recovered")
    t.assertEqual(machine.succeed("readlink -f /nix/var/nix/profiles/system").strip(), previous_profile)
    t.assertEqual(
        machine.succeed(
            "find /etc/nixos -type f -print0 | sort -z | xargs -0 sha256sum"
        ),
        source_hashes,
    )
    machine.fail("journalctl -u polkit.service --no-pager | grep -F NCM_LIVE_TEST_UNEXPECTED_POLKIT_ACTION")
    machine.succeed("systemctl is-active --quiet nix-control-manager-helper.socket")
  '';
}
