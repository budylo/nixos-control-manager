{ pkgs, ncmPackage, ncmModule }:

let
  instrumentation = ./live-test-candidate-instrumentation.nix;
  ncmFixture = ./live-control-fixture/ncm;
  polkitRule = ''
    polkit.addRule(function(action, subject) {
      if ((action.id == "org.nixos.nix-control-manager.preview-activation"
           || action.id == "org.nixos.nix-control-manager.test-activation"
           || action.id == "org.nixos.nix-control-manager.recover-test-activation"
           || action.id == "org.nixos.nix-control-manager.commit-tested-system"
           || action.id == "org.nixos.nix-control-manager.rollback-committed-system")
          && subject.user == "ncm-control") {
        return polkit.Result.YES;
      }
      if (action.id.indexOf("org.nixos.nix-control-manager.") == 0) {
        polkit.log("NCM_LIVE_CONTROL_UNEXPECTED_POLKIT_ACTION");
        return polkit.Result.NO;
      }
    });
  '';
  candidateNcmModule = import ../../packaging/nixos-module.nix {
    defaultPackage = pkgs: pkgs.runCommand "ncm-candidate-helper" { }
      "mkdir -p $out/bin";
  };
  candidateConfiguration = { ... }: {
    imports = [ instrumentation candidateNcmModule ncmFixture ];
    boot.loader.grub.devices = [ "nodev" ];
    fileSystems."/".device = "none";
    fileSystems."/".fsType = "tmpfs";
    networking.hostName = "ncm-live-control";
    system.stateVersion = "26.05";
    users.groups.ncm-control = { };
    users.users.ncm-control = {
      isSystemUser = true;
      group = "ncm-control";
    };
    services.nix-control-manager-helper = {
      enable = true;
      mode = "live-control";
      targetId = "control";
      allowedUsers = [ "ncm-control" ];
      validationTimeout = 300;
      testActivationTimeout = 120;
    };
    security.polkit.extraConfig = polkitRule;
  };
  candidateSystem = (import (pkgs.path + "/nixos") {
    configuration = candidateConfiguration;
    system = pkgs.stdenv.hostPlatform.system;
  }).system;
  recoveryTools = pkgs.buildEnv {
    name = "ncm-live-control-recovery-tools";
    paths = [ pkgs.bash pkgs.coreutils pkgs.findutils pkgs.gnugrep pkgs.systemd ];
  };
  recoverySystem = pkgs.runCommand "ncm-live-control-recovery-system" { } ''
    mkdir -p "$out/bin"
    ln -s ${recoveryTools} "$out/sw"
    cat > "$out/bin/switch-to-configuration" <<'SCRIPT'
#!@shell@
set -eu
case "$1" in
  test|switch)
    @coreutils@/bin/ln -sfn '@recovery@' /run/current-system
    echo "$1" > /run/ncm-live-control-recovered
    ;;
  *) exit 64 ;;
esac
SCRIPT
    substituteInPlace "$out/bin/switch-to-configuration" \
      --replace-fail '@shell@' '${pkgs.runtimeShell}' \
      --replace-fail '@coreutils@' '${pkgs.coreutils}' \
      --replace-fail '@recovery@' "$out"
    chmod 0755 "$out/bin/switch-to-configuration"
  '';
  moduleExpression = ''
    (import ${../../packaging}/nixos-module.nix {
      # The candidate never starts this service in the VM. A deterministic
      # placeholder keeps configuration.nix content-addressed while the
      # running helper still uses the real ncmPackage from the test node.
      defaultPackage = pkgs: pkgs.runCommand "ncm-candidate-helper" { }
        "mkdir -p $out/bin";
    })
  '';
  liveConfiguration = pkgs.writeText "ncm-live-control-configuration.nix" ''
    { ... }:
    {
      imports = [
        ${instrumentation}
        ${moduleExpression}
        (if false then ./ncm else ${ncmFixture})
      ];
      boot.loader.grub.devices = [ "nodev" ];
      fileSystems."/".device = "none";
      fileSystems."/".fsType = "tmpfs";
      networking.hostName = "ncm-live-control";
      system.stateVersion = "26.05";
      users.groups.ncm-control = { };
      users.users.ncm-control = {
        isSystemUser = true;
        group = "ncm-control";
      };
      services.nix-control-manager-helper = {
        enable = true;
        mode = "live-control";
        targetId = "control";
        allowedUsers = [ "ncm-control" ];
        validationTimeout = 300;
        testActivationTimeout = 120;
      };
      security.polkit.extraConfig = ${builtins.toJSON polkitRule};
    }
  '';
  socketPath = "/run/nix-control-manager/helper.sock";
  testJournal = "/var/lib/nix-control-manager/test-activations";
  managedJournal = "/var/lib/nix-control-manager/managed-transactions";
  client = "${ncmPackage}/bin/ncm-helper-client --socket ${socketPath} --timeout 300";
  runAsUser = "${pkgs.util-linux}/bin/runuser -u ncm-control --";
  userSystemctl = "${runAsUser} env XDG_RUNTIME_DIR=/run/user/1000 ${pkgs.systemd}/bin/systemctl --user";
in
pkgs.testers.runNixOSTest {
  name = "nix-control-manager-live-control";

  nodes.machine = { ... }: {
    imports = [ ncmModule ];
    virtualisation.memorySize = 2560;
    virtualisation.diskSize = 5120;
    virtualisation.writableStore = true;
    virtualisation.additionalPaths = [ candidateSystem recoverySystem ];
    nix.nixPath = [ "nixpkgs=${pkgs.path}" ];
    users.groups.ncm-control = { };
    users.users.ncm-control = {
      isNormalUser = true;
      group = "ncm-control";
      linger = true;
    };
    environment.systemPackages = [
      ncmPackage
      pkgs.coreutils
      pkgs.findutils
      pkgs.jq
      pkgs.python3
      pkgs.util-linux
    ];
    services.nix-control-manager-helper = {
      enable = true;
      mode = "live-control";
      targetId = "control";
      allowedUsers = [ "ncm-control" ];
      validationTimeout = 300;
      testActivationTimeout = 120;
    };
    programs.nix-control-manager = {
      enable = true;
      openBrowser = false;
    };
    security.polkit.extraConfig = polkitRule;
    systemd.services.ncm-live-control-setup = {
      wantedBy = [ "multi-user.target" ];
      before = [ "nix-control-manager-helper.service" ];
      serviceConfig = { Type = "oneshot"; RemainAfterExit = true; };
      script = ''
        install -d -m 0755 /etc/nixos/ncm /nix/var/nix/profiles
        install -m 0644 ${liveConfiguration} /etc/nixos/configuration.nix
        cp ${ncmFixture}/* /etc/nixos/ncm/
        chmod 0644 /etc/nixos/configuration.nix /etc/nixos/ncm/*
        ln -sfn ${recoverySystem} /run/current-system
        ln -sfn ${recoverySystem} /nix/var/nix/profiles/system
      '';
    };
    systemd.services.nix-control-manager-helper = {
      requires = [ "ncm-live-control-setup.service" ];
      after = [ "ncm-live-control-setup.service" ];
    };
  };

  testScript = ''
    from datetime import timedelta
    import json

    timeout = timedelta(seconds=300)
    candidate = "${candidateSystem}"
    previous = "${recoverySystem}"
    machine.start()
    machine.wait_for_unit("multi-user.target")
    machine.wait_for_unit("ncm-live-control-setup.service")
    machine.wait_for_unit("nix-control-manager-helper.socket")
    machine.wait_for_unit("user@1000.service")
    machine.succeed("${userSystemctl} start nix-control-manager-gui.service")
    machine.wait_until_succeeds(
      "${userSystemctl} is-active nix-control-manager-gui.service"
    )
    machine.wait_until_succeeds(
      "${pkgs.python3}/bin/python3 -c "
      "'import socket; socket.create_connection((\"127.0.0.1\", 8765), timeout=1).close()'"
    )

    capabilities = json.loads(machine.succeed(
      "${runAsUser} ${client} capabilities", timeout=timeout
    ))
    target = next(x for x in capabilities["result"]["targets"] if x["targetId"] == "control")
    t.assertTrue(target["readOnly"])
    t.assertTrue(target["managedWriteEnabled"])
    t.assertTrue(target["testActivationEnabled"])
    t.assertTrue(target["permanentSwitchEnabled"])
    t.assertTrue(target["rollbackGenerationEnabled"])
    t.assertFalse(capabilities["result"]["arbitraryCommandsAccepted"])
    paths = machine.succeed(
      "systemctl show nix-control-manager-helper.service -p ReadWritePaths --value"
    )
    t.assertIn("/etc/nixos/ncm", paths)
    t.assertIn("${testJournal}", paths)
    t.assertIn("${managedJournal}", paths)
    dependencies = machine.succeed(
      "systemctl show nix-control-manager-helper.service -p Requires -p Wants"
    )
    t.assertNotIn("polkit.service", next(
      line for line in dependencies.splitlines() if line.startswith("Requires=")
    ))
    t.assertIn("polkit.service", next(
      line for line in dependencies.splitlines() if line.startswith("Wants=")
    ))

    source_hashes = machine.succeed(
      "find /etc/nixos -type f -print0 | sort -z | xargs -0 sha256sum"
    )
    fingerprint = machine.succeed(
      "${runAsUser} env PYTHONPATH=${../../src} ${pkgs.python3}/bin/python3 -c "
      "'from pathlib import Path; from nix_control_manager.adoption import plan_adoption; "
      "from nix_control_manager.candidate import plan_identity; "
      "print(plan_identity(plan_adoption(Path(\"/etc/nixos\")), None)[0])'"
    ).strip()
    helper_pid = machine.succeed(
      "systemctl show nix-control-manager-helper.service -p MainPID --value"
    ).strip()
    gui_pid = machine.succeed(
      "${userSystemctl} show nix-control-manager-gui.service -p MainPID --value"
    ).strip()
    polkit_pid = machine.succeed(
      "systemctl show polkit.service -p MainPID --value"
    ).strip()

    # Reproduce a GUI/client disappearing while the helper is still doing the
    # comparatively slow exact-candidate validation.  The daemon must absorb
    # the failed response write and continue serving the next request.
    machine.succeed(
      "${runAsUser} env PYTHONPATH=${../../src} ${pkgs.python3}/bin/python3 "
      "${./abandon-live-preview.py} --socket ${socketPath} --config-root /etc/nixos "
      "--target control --system-path " + candidate
      + " --plan-fingerprint " + fingerprint,
      timeout=timeout,
    )
    capabilities_after_disconnect = json.loads(machine.succeed(
      "${runAsUser} ${client} capabilities", timeout=timeout
    ))
    t.assertEqual(capabilities_after_disconnect["status"], "ok")
    t.assertEqual(machine.succeed(
      "systemctl show nix-control-manager-helper.service -p MainPID --value"
    ).strip(), helper_pid)

    preview = json.loads(machine.succeed(
      "${runAsUser} ${client} preview-activation --target control "
      "--config-root /etc/nixos --system-path " + candidate
      + " --plan-fingerprint " + fingerprint,
      timeout=timeout,
    ))
    t.assertEqual(preview["status"], "ok")
    t.assertEqual(preview["result"]["status"], "passed")
    receipt = preview["result"]["testReceipt"]

    activation = json.loads(machine.succeed(
      "${runAsUser} ${client} test-activation --target control --system-path "
      + candidate + " --plan-fingerprint " + fingerprint + " --receipt " + receipt,
      timeout=timeout,
    ))
    session = activation["result"]["sessionId"]
    t.assertEqual(activation["result"]["status"], "active")
    t.assertEqual(machine.succeed("readlink -f /run/current-system").strip(), candidate)
    t.assertEqual(machine.succeed("readlink -f /nix/var/nix/profiles/system").strip(), previous)
    t.assertNotEqual(machine.succeed(
      "systemctl show polkit.service -p MainPID --value"
    ).strip(), polkit_pid)
    t.assertEqual(machine.succeed(
      "systemctl show nix-control-manager-helper.service -p MainPID --value"
    ).strip(), helper_pid)
    t.assertEqual(machine.succeed(
      "${userSystemctl} show nix-control-manager-gui.service -p MainPID --value"
    ).strip(), gui_pid)

    commit = json.loads(machine.succeed(
      "${runAsUser} ${client} commit-tested-system --target control "
      "--config-root /etc/nixos --system-path " + candidate
      + " --plan-fingerprint " + fingerprint + " --session-id " + session,
      timeout=timeout,
    ))
    t.assertEqual(commit["result"]["status"], "committing")
    machine.wait_until_succeeds(
      "${pkgs.jq}/bin/jq -e '.state == \"committed\"' ${testJournal}/" + session + ".json",
      timeout=timedelta(seconds=120),
    )
    t.assertEqual(machine.succeed("readlink -f /run/current-system").strip(), candidate)
    t.assertEqual(machine.succeed("readlink -f /nix/var/nix/profiles/system").strip(), candidate)
    machine.wait_for_unit("nix-control-manager-helper.socket")
    t.assertEqual(machine.succeed(
      "systemctl show nix-control-manager-helper.service -p MainPID --value"
    ).strip(), helper_pid)
    t.assertEqual(machine.succeed(
      "${userSystemctl} show nix-control-manager-gui.service -p MainPID --value"
    ).strip(), gui_pid)

    status = json.loads(machine.succeed(
      "${runAsUser} ${client} activation-session-status --target control --session-id " + session,
      timeout=timeout,
    ))
    t.assertEqual(status["result"]["status"], "committed")

    rollback = json.loads(machine.succeed(
      "${runAsUser} ${client} rollback-committed-system --target control --session-id " + session,
      timeout=timeout,
    ))
    t.assertEqual(rollback["result"]["status"], "rolling-back")
    machine.wait_until_succeeds(
      "${pkgs.jq}/bin/jq -e '.state == \"rolled-back\"' ${testJournal}/" + session + ".json",
      timeout=timedelta(seconds=120),
    )
    t.assertEqual(machine.succeed("readlink -f /run/current-system").strip(), previous)
    t.assertEqual(machine.succeed("readlink -f /nix/var/nix/profiles/system").strip(), previous)
    t.assertEqual(machine.succeed(
      "find /etc/nixos -type f -print0 | sort -z | xargs -0 sha256sum"
    ), source_hashes)
    t.assertEqual(machine.succeed(
      "systemctl show nix-control-manager-helper.service -p MainPID --value"
    ).strip(), helper_pid)
    t.assertEqual(machine.succeed(
      "${userSystemctl} show nix-control-manager-gui.service -p MainPID --value"
    ).strip(), gui_pid)
    t.assertEqual(machine.succeed(
      "grep -c -E '^(test|switch)$' /run/ncm-live-test-candidate"
    ).strip(), "2")
    machine.fail("systemctl list-units --all 'ncm-test-rollback-*' --no-legend | grep .")
    machine.fail("journalctl -u polkit.service --no-pager | grep -F NCM_LIVE_CONTROL_UNEXPECTED_POLKIT_ACTION")
  '';
}
