{ defaultPackage }:
{ config, lib, pkgs, ... }:

let
  inherit (lib)
    all
    concatStringsSep
    hasPrefix
    hasSuffix
    mkEnableOption
    mkIf
    mkOption
    optionalAttrs
    optionals
    splitString
    types
    ;
  cfg = config.services.nix-control-manager-helper;
  clientCfg = config.programs.nix-control-manager;
  serviceName = "nix-control-manager-helper";
  socketPath = "/run/nix-control-manager/helper.sock";
  socketGroup = "nix-control-manager";
  guiServiceName = "nix-control-manager-gui";
  isFixture = cfg.mode == "fixture";
  isLiveTest = cfg.mode == "live-test";
  isLiveHomeManager = cfg.mode == "live-home-manager";
  isLiveManaged = cfg.mode == "live-managed";
  isLiveControl = cfg.mode == "live-control";
  hasTestActivation = isLiveTest || isLiveControl;
  hasManagedWrite = isLiveManaged || isLiveControl;
  configurationRoot = if isFixture then cfg.fixtureRoot else "/etc/nixos";
  transactionJournal = if isFixture then cfg.journalRoot else null;
  testJournal = if hasTestActivation then cfg.testJournalRoot else null;
  homeManagerRoot = if isLiveHomeManager then cfg.homeManagerRoot else null;
  homeManagerJournalRoot =
    if isLiveHomeManager then cfg.homeManagerJournalRoot else null;
  managedJournalRoot = if hasManagedWrite then cfg.managedJournalRoot else null;
  effectiveAllowedPaths = if hasManagedWrite then [
    "ncm/state.json"
    "ncm/packages.nix"
  ] else cfg.allowedRelativePaths;
  pathIsSafe = path:
    path != ""
    && !(hasPrefix "/" path)
    && all (part: part != "" && part != "." && part != "..")
      (splitString "/" path);
  helperConfig = (pkgs.formats.json { }).generate "ncm-helper.json" {
    schemaVersion = 6;
    inherit socketPath;
    polkitExecutable = "${pkgs.polkit}/bin/pkcheck";
    validationTimeout = cfg.validationTimeout;
    targets = [
      {
        targetId = cfg.targetId;
        mode = cfg.mode;
        inherit configurationRoot;
        journalRoot = transactionJournal;
        testJournalRoot = testJournal;
        testTimeoutSeconds = cfg.testActivationTimeout;
        inherit homeManagerRoot homeManagerJournalRoot;
        inherit managedJournalRoot;
        allowedRelativePaths = effectiveAllowedPaths;
        flakeTarget = cfg.flakeTarget;
      }
    ];
  };
  clientLauncher = pkgs.writeShellApplication {
    name = "ncm-gui";
    runtimeInputs = [
      pkgs.coreutils
      pkgs.curl
      pkgs.gnugrep
      pkgs.systemd
      pkgs.xdg-utils
    ];
    text = ''
      service=${guiServiceName}.service
      url=http://127.0.0.1:${toString clientCfg.port}/
      open_browser=${if clientCfg.openBrowser then "true" else "false"}
      action=start

      usage() {
        echo 'Usage: ncm-gui [--open|--no-open|--status|--stop]'
      }

      valid_response() {
        local payload="$1"
        grep -Fq '"application": "nix-control-manager"' <<< "$payload" \
          && grep -Fq '"apiVersion": 1' <<< "$payload" \
          && grep -Fq '"localWriteEnabled": false' <<< "$payload"
      }

      if (( $# > 1 )); then
        usage >&2
        exit 2
      elif (( $# == 1 )); then
        action="$1"
      fi

      case "$action" in
        start) ;;
        --open) open_browser=true ;;
        --no-open) open_browser=false ;;
        --stop)
          systemctl --user stop "$service"
          echo "Nix Control Manager stopped."
          exit 0
          ;;
        --status)
          if ! systemctl --user is-active --quiet "$service"; then
            echo "Nix Control Manager is stopped."
            exit 3
          fi
          if response="$(curl -fsS --max-time 1 "''${url}api/config")" \
            && valid_response "$response"; then
            echo "Nix Control Manager is running at $url (read-only)."
            exit 0
          fi
          echo "Nix Control Manager service is active but its API is not ready." >&2
          exit 4
          ;;
        --help|-h)
          usage
          exit 0
          ;;
        *)
          usage >&2
          exit 2
          ;;
      esac

      systemctl --user start "$service"
      response=
      attempt=0
      while (( attempt < 100 )); do
        (( attempt += 1 ))
        if response="$(curl -fsS --max-time 1 "''${url}api/config" 2>/dev/null)" \
          && valid_response "$response"; then
          echo "Nix Control Manager is running at $url (read-only)."
          if [[ "$open_browser" == true ]]; then
            if ! xdg-open "$url" >/dev/null 2>&1; then
              echo "Could not open a browser automatically; open $url manually." >&2
            fi
          fi
          exit 0
        fi
        if systemctl --user is-failed --quiet "$service"; then
          break
        fi
        sleep 0.1
      done

      echo "Nix Control Manager did not become ready at $url." >&2
      systemctl --user status "$service" --no-pager >&2 || true
      exit 1
    '';
  };
  desktopItem = pkgs.makeDesktopItem {
    name = "nix-control-manager";
    desktopName = "Nix Control Manager";
    comment = "Inspect and preview the declarative NixOS configuration";
    exec = "${clientLauncher}/bin/ncm-gui";
    icon = "preferences-system";
    categories = [ "Settings" ];
    terminal = false;
  };
  clientBundle = pkgs.symlinkJoin {
    name = "nix-control-manager-client";
    paths = [ clientCfg.package clientLauncher desktopItem ];
  };
in
{
  options.services.nix-control-manager-helper = {
    enable = mkEnableOption "the sandboxed Nix Control Manager helper";

    mode = mkOption {
      type = types.enum [
        "fixture"
        "live-read-only"
        "live-test"
        "live-home-manager"
        "live-managed"
        "live-control"
      ];
      default = "fixture";
      description = ''
        Helper target mode. live-read-only validates an exact adoption plan
        against /etc/nixos and may produce a Polkit-authorized dry-activation
        report for its exact build output, but cannot issue receipts, apply
        changes, activate a generation, or recover transactions. live-test is
        an explicit opt-in extension which permits only a time-limited runtime
        test activation of that exact output, with automatic recovery; it
        still cannot write /etc/nixos, switch generations, or change boot.
        live-home-manager is a separate opt-in that may persist only an exact,
        validated Home Manager plan under homeManagerRoot. It does not enable
        NixOS apply, Home Manager activation, or generation switching.
        live-managed is a separate opt-in capability that may atomically
        persist only ncm/state.json and ncm/packages.nix after disposable
        evaluation, explicit confirmation, and Polkit authorization. It never
        edits configuration.nix, mutates flake inputs, or activates a system.
        live-control is the combined, higher-trust opt-in mode: it preserves
        the exact managed two-file boundary, requires a successful timed test
        activation, and only then permits a Polkit-authorized switch to that
        exact closure plus rollback to the journaled previous closure.
      '';
    };

    package = mkOption {
      type = types.package;
      default = defaultPackage pkgs;
      defaultText = lib.literalExpression "self.packages.${pkgs.system}.default";
      description = "Nix Control Manager package containing ncm-helper.";
    };

    fixtureRoot = mkOption {
      type = types.str;
      default = "/var/lib/nix-control-manager/fixture";
      description = ''
        Explicitly marked disposable configuration root used only in fixture
        mode. It can never be /etc/nixos.
      '';
    };

    journalRoot = mkOption {
      type = types.str;
      default = "/var/lib/nix-control-manager/transactions";
      description = "Transaction journal outside the fixture configuration root.";
    };

    testJournalRoot = mkOption {
      type = types.str;
      default = "/var/lib/nix-control-manager/test-activations";
      description = "Root-only journal for time-limited live-test activation sessions.";
    };

    testActivationTimeout = mkOption {
      type = types.ints.between 30 1800;
      default = 300;
      description = "Seconds before a live-test session automatically restores the previous runtime system.";
    };

    homeManagerRoot = mkOption {
      type = types.str;
      default = "/etc/nixos";
      description = ''
        Configuration root writable only in live-home-manager mode. The first
        supported deployment is Home Manager's NixOS-module integration under
        /etc/nixos; home directories remain excluded by the service sandbox.
      '';
    };

    homeManagerJournalRoot = mkOption {
      type = types.str;
      default = "/var/lib/nix-control-manager/home-manager-transactions";
      description = "Root-only journal for live Home Manager source transactions.";
    };

    managedJournalRoot = mkOption {
      type = types.str;
      default = "/var/lib/nix-control-manager/managed-transactions";
      description = "Root-only journal for bounded NCM-owned source transactions.";
    };

    targetId = mkOption {
      type = types.strMatching "[a-z][a-z0-9-]{0,31}";
      default = "fixture";
      description = "Stable helper protocol target identifier.";
    };

    flakeTarget = mkOption {
      type = types.nullOr (types.strMatching "[A-Za-z0-9_-]+");
      default = null;
      description = "Optional nixosConfigurations host key for a flake fixture.";
    };

    allowedRelativePaths = mkOption {
      type = types.listOf types.str;
      default = [
        "configuration.nix"
        "ncm/default.nix"
        "ncm/managed.nix"
        "ncm/packages.nix"
        "ncm/state.json"
      ];
      description = "Exact relative paths the selected transactional workflow may change.";
    };

    allowedUsers = mkOption {
      type = types.listOf types.str;
      default = [ ];
      description = "Existing users allowed to connect to the helper socket.";
    };

    validationTimeout = mkOption {
      type = types.ints.between 1 900;
      default = 180;
      description = "Maximum seconds for each Nix validation subprocess.";
    };
  };

  options.programs.nix-control-manager = {
    enable = mkEnableOption "the read-only Nix Control Manager graphical client";

    package = mkOption {
      type = types.package;
      default = defaultPackage pkgs;
      defaultText = lib.literalExpression "self.packages.${pkgs.system}.default";
      description = "Nix Control Manager package containing the local GUI server.";
    };

    port = mkOption {
      type = types.port;
      default = 8765;
      description = "Loopback TCP port used by the local graphical interface.";
    };

    openBrowser = mkOption {
      type = types.bool;
      default = true;
      description = "Open the loopback graphical interface after starting or reusing its user service.";
    };
  };

  config = lib.mkMerge [
    (mkIf cfg.enable {
    assertions = [
      {
        assertion = !isFixture || (
          cfg.fixtureRoot != "/etc/nixos"
          && !(hasSuffix "/etc/nixos" cfg.fixtureRoot)
        );
        message = "The fixture-only Nix Control Manager helper refuses /etc/nixos.";
      }
      {
        assertion = !hasTestActivation || (
          cfg.testJournalRoot != "/etc/nixos"
          && !(hasPrefix "/etc/nixos/" cfg.testJournalRoot)
        );
        message = "The live-test journal must remain outside /etc/nixos.";
      }
      {
        assertion = !isLiveHomeManager || (
          hasPrefix "/" cfg.homeManagerRoot
          && cfg.homeManagerRoot != "/"
          && cfg.homeManagerRoot != "/nix/store"
          && !(hasPrefix "/nix/store/" cfg.homeManagerRoot)
          && cfg.homeManagerRoot != "/home"
          && !(hasPrefix "/home/" cfg.homeManagerRoot)
          && cfg.homeManagerRoot != "/root"
          && !(hasPrefix "/root/" cfg.homeManagerRoot)
        );
        message = "live-home-manager requires an absolute non-home, non-store configuration root.";
      }
      {
        assertion = !hasManagedWrite || (
          hasPrefix "/" cfg.managedJournalRoot
          && cfg.managedJournalRoot != "/etc/nixos"
          && !(hasPrefix "/etc/nixos/" cfg.managedJournalRoot)
        );
        message = "The live-managed journal must be absolute and outside /etc/nixos.";
      }
      {
        assertion = !isLiveControl || cfg.testJournalRoot != cfg.managedJournalRoot;
        message = "live-control requires separate test and managed journals.";
      }
      {
        assertion = !isLiveHomeManager || (
          hasPrefix "/" cfg.homeManagerJournalRoot
          && cfg.homeManagerJournalRoot != cfg.homeManagerRoot
          && !(hasPrefix "${cfg.homeManagerRoot}/" cfg.homeManagerJournalRoot)
        );
        message = "The live Home Manager journal must be absolute and outside homeManagerRoot.";
      }
      {
        assertion = !isFixture || (
          cfg.journalRoot != cfg.fixtureRoot
          && !(hasPrefix "${cfg.fixtureRoot}/" cfg.journalRoot)
        );
        message = "The Nix Control Manager journal must be outside fixtureRoot.";
      }
      {
        assertion = cfg.allowedRelativePaths != [ ]
          && builtins.length cfg.allowedRelativePaths <= 16
          && all pathIsSafe cfg.allowedRelativePaths;
        message = "Nix Control Manager allowedRelativePaths are invalid.";
      }
      {
        assertion = builtins.length cfg.allowedRelativePaths
          == builtins.length (lib.unique cfg.allowedRelativePaths);
        message = "Nix Control Manager allowedRelativePaths contain duplicates.";
      }
    ];

    users.groups.${socketGroup}.members = cfg.allowedUsers;
    security.polkit.enable = true;
    environment.etc."polkit-1/actions/org.nixos.nix-control-manager.policy".source =
      ./polkit/org.nixos.nix-control-manager.policy;
    systemd.tmpfiles.rules =
      optionals isFixture [ "d ${cfg.journalRoot} 0700 root root -" ]
      ++ optionals hasTestActivation [ "d ${cfg.testJournalRoot} 0700 root root -" ]
      ++ optionals isLiveHomeManager [
        "d ${cfg.homeManagerJournalRoot} 0700 root root -"
      ]
      ++ optionals hasManagedWrite [
        "d ${cfg.managedJournalRoot} 0700 root root -"
      ];

    systemd.sockets.${serviceName} = {
      description = "Nix Control Manager helper socket";
      wantedBy = [ "sockets.target" ];
      socketConfig = {
        ListenStream = socketPath;
        SocketMode = "0660";
        SocketUser = "root";
        SocketGroup = socketGroup;
        DirectoryMode = "0755";
        RemoveOnStop = true;
        Service = "${serviceName}.service";
      };
    };

    systemd.services.${serviceName} = {
      description = if isFixture then
        "Fixture-only Nix Control Manager system helper"
      else if isLiveTest then
        "Time-limited test activation Nix Control Manager system helper"
      else if isLiveHomeManager then
        "Home Manager persistence Nix Control Manager system helper"
      else if isLiveManaged then
        "Bounded managed-source Nix Control Manager system helper"
      else if isLiveControl then
        "Test-gated Nix Control Manager system switch helper"
      else
        "Read-only Nix Control Manager system helper";
      requires = [ "polkit.service" ];
      after = [ "polkit.service" ];
      path = [ cfg.package pkgs.nix pkgs.systemd ];
      environment = {
        # ProtectHome makes /root intentionally inaccessible. Nix still probes
        # $HOME/.nix-defexpr even for --parse, so give it the service's private,
        # ephemeral /tmp instead of weakening the home-directory sandbox.
        HOME = "/tmp";
        NIX_PATH = concatStringsSep ":" config.nix.nixPath;
      };
      serviceConfig = {
        Type = "simple";
        ExecStart = "${cfg.package}/bin/ncm-helper --config ${helperConfig}";
        User = "root";
        Group = "root";
        UMask = "0077";
        Restart = "on-failure";
        RestartSec = "1s";
        TimeoutStopSec = "10s";

        NoNewPrivileges = true;
        PrivateTmp = true;
        PrivateDevices = true;
        PrivateNetwork = true;
        ProtectSystem = "strict";
        ProtectHome = true;
        ProtectKernelTunables = true;
        ProtectKernelModules = true;
        ProtectKernelLogs = true;
        ProtectControlGroups = true;
        ProtectClock = true;
        ProtectHostname = true;
        RestrictNamespaces = true;
        RestrictRealtime = true;
        RestrictSUIDSGID = true;
        LockPersonality = true;
        MemoryDenyWriteExecute = true;
        RemoveIPC = true;
        SystemCallArchitectures = "native";
        SystemCallFilter = [
          "@system-service"
          "~@keyring"
          "~@mount"
          "~@obsolete"
          "~@raw-io"
          "~@reboot"
          "~@swap"
        ];
        RestrictAddressFamilies = [ "AF_UNIX" ];
      } // optionalAttrs isFixture {
        StateDirectory = "nix-control-manager";
        StateDirectoryMode = "0700";
        CapabilityBoundingSet = [ "CAP_DAC_OVERRIDE" "CAP_FOWNER" ];
        ReadWritePaths = [ cfg.fixtureRoot cfg.journalRoot ];
      } // optionalAttrs (!isFixture) {
        # An empty Nix list is omitted by the unit renderer. The empty string
        # deliberately emits `CapabilityBoundingSet=` and clears every cap.
        CapabilityBoundingSet = "";
        ReadOnlyPaths = optionals (!isLiveHomeManager && !hasManagedWrite) [ "/etc/nixos" ];
      } // optionalAttrs isLiveTest {
        ReadWritePaths = [ cfg.testJournalRoot ];
      } // optionalAttrs isLiveHomeManager {
        ReadWritePaths = [ cfg.homeManagerRoot cfg.homeManagerJournalRoot ];
      } // optionalAttrs isLiveManaged {
        ReadWritePaths = [ "/etc/nixos/ncm" cfg.managedJournalRoot ];
      } // optionalAttrs isLiveControl {
        ReadWritePaths = [
          "/etc/nixos/ncm"
          cfg.managedJournalRoot
          cfg.testJournalRoot
        ];
      };
    };
    })
    (mkIf clientCfg.enable {
      environment.systemPackages = [ clientBundle ];
      systemd.user.services.${guiServiceName} = {
        description = "Nix Control Manager read-only graphical server";
        path = [ clientCfg.package pkgs.nix ];
        environment = {
          HOME = "/tmp";
          NIX_PATH = concatStringsSep ":" config.nix.nixPath;
          PYTHONUNBUFFERED = "1";
        };
        serviceConfig = {
          Type = "simple";
          ExecStart = concatStringsSep " " ([
            "${clientCfg.package}/bin/ncm"
            "serve"
            "--state /etc/nixos/ncm/state.json"
            "--user-state /etc/nixos/ncm/user-state.json"
            "--output /etc/nixos/ncm/packages.nix"
            "--config-root /etc/nixos"
            "--home-manager-root %h/.config/home-manager"
            "--port ${toString clientCfg.port}"
            "--read-only"
          ] ++ optionals cfg.enable [
            "--helper-socket ${socketPath}"
            "--helper-target ${cfg.targetId}"
            "--validation-timeout ${toString cfg.validationTimeout}"
          ]);
          UMask = "0077";
          Restart = "on-failure";
          RestartSec = "1s";
          KillSignal = "SIGINT";
          TimeoutStopSec = "10s";
          NoNewPrivileges = true;
          PrivateDevices = true;
          PrivateTmp = true;
          ProtectHome = "read-only";
          ProtectSystem = "strict";
          ReadOnlyPaths = [ "/etc/nixos" ];
          RestrictAddressFamilies = [ "AF_UNIX" "AF_INET" "AF_INET6" ];
          RestrictRealtime = true;
          RestrictSUIDSGID = true;
          LockPersonality = true;
        };
      };
    })
  ];
}
