{
  description = "A user-friendly control center for declarative NixOS configuration";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      supportedSystems = [ "x86_64-linux" "aarch64-linux" ];
      forAllSystems = nixpkgs.lib.genAttrs supportedSystems;
    in
    {
      packages = forAllSystems (system:
        let pkgs = nixpkgs.legacyPackages.${system};
        in {
          default = import ./packaging/package.nix {
            inherit pkgs;
            source = self;
          };
        } // nixpkgs.lib.optionalAttrs (system == "x86_64-linux") {
          helper-vm-test = import ./tests/nixos/helper-vm-test.nix {
            inherit pkgs;
            ncmPackage = self.packages.${system}.default;
            ncmModule = self.nixosModules.default;
          };
          live-read-only-ui-vm-test = import ./tests/nixos/live-read-only-ui-vm-test.nix {
            inherit pkgs;
            ncmPackage = self.packages.${system}.default;
            ncmModule = self.nixosModules.default;
          };
          live-test-recovery-vm-test = import ./tests/nixos/live-test-recovery-vm-test.nix {
            inherit pkgs;
            ncmPackage = self.packages.${system}.default;
            ncmModule = self.nixosModules.default;
          };
          live-home-manager-vm-test = import ./tests/nixos/live-home-manager-vm-test.nix {
            inherit pkgs;
            ncmPackage = self.packages.${system}.default;
            ncmModule = self.nixosModules.default;
          };
          live-managed-vm-test = import ./tests/nixos/live-managed-vm-test.nix {
            inherit pkgs;
            ncmPackage = self.packages.${system}.default;
            ncmModule = self.nixosModules.default;
          };
          live-control-vm-test = import ./tests/nixos/live-control-vm-test.nix {
            inherit pkgs;
            ncmPackage = self.packages.${system}.default;
            ncmModule = self.nixosModules.default;
          };
        });

      apps = forAllSystems (system: {
        default = {
          type = "app";
          program = "${self.packages.${system}.default}/bin/ncm";
          meta.description = "Launch Nix Control Manager";
        };
      });

      nixosModules = {
        default = import ./packaging/nixos-module.nix {
          defaultPackage = pkgs: self.packages.${pkgs.stdenv.hostPlatform.system}.default;
        };
        channel = import ./packaging/channel-module.nix;
      };

      checks = forAllSystems (system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
          evaluated = nixpkgs.lib.nixosSystem {
            inherit system;
            modules = [
              self.nixosModules.default
              ({ ... }: {
                system.stateVersion = "26.05";
                users.users.fixture-user.isNormalUser = true;
                services.nix-control-manager-helper = {
                  enable = true;
                  fixtureRoot = "/var/lib/nix-control-manager/fixture";
                  allowedUsers = [ "fixture-user" ];
                };
              })
            ];
          };
          evaluatedLiveReadOnly = nixpkgs.lib.nixosSystem {
            inherit system;
            modules = [
              self.nixosModules.default
              ({ ... }: {
                system.stateVersion = "26.05";
                users.users.live-user.isNormalUser = true;
                services.nix-control-manager-helper = {
                  enable = true;
                  mode = "live-read-only";
                  targetId = "live";
                  allowedUsers = [ "live-user" ];
                };
              })
            ];
          };
          evaluatedLiveTest = nixpkgs.lib.nixosSystem {
            inherit system;
            modules = [
              self.nixosModules.default
              ({ ... }: {
                system.stateVersion = "26.05";
                users.users.live-test-user.isNormalUser = true;
                services.nix-control-manager-helper = {
                  enable = true;
                  mode = "live-test";
                  targetId = "live-test";
                  allowedUsers = [ "live-test-user" ];
                };
              })
            ];
          };
          evaluatedLiveHomeManager = nixpkgs.lib.nixosSystem {
            inherit system;
            modules = [
              self.nixosModules.default
              ({ ... }: {
                system.stateVersion = "26.05";
                users.users.live-home-user.isNormalUser = true;
                services.nix-control-manager-helper = {
                  enable = true;
                  mode = "live-home-manager";
                  targetId = "live-home";
                  allowedUsers = [ "live-home-user" ];
                };
              })
            ];
          };
          evaluatedLiveManaged = nixpkgs.lib.nixosSystem {
            inherit system;
            modules = [
              self.nixosModules.default
              ({ ... }: {
                system.stateVersion = "26.05";
                users.users.live-managed-user.isNormalUser = true;
                services.nix-control-manager-helper = {
                  enable = true;
                  mode = "live-managed";
                  targetId = "managed";
                  allowedUsers = [ "live-managed-user" ];
                };
                programs.nix-control-manager.enable = true;
              })
            ];
          };
          evaluatedLiveControl = nixpkgs.lib.nixosSystem {
            inherit system;
            modules = [
              self.nixosModules.default
              ({ ... }: {
                system.stateVersion = "26.05";
                users.users.live-control-user.isNormalUser = true;
                services.nix-control-manager-helper = {
                  enable = true;
                  mode = "live-control";
                  targetId = "control";
                  allowedUsers = [ "live-control-user" ];
                  flakeTarget = "live-control";
                  flakeLockWriteEnable = true;
                };
                programs.nix-control-manager.enable = true;
              })
            ];
          };
          evaluatedChannel = nixpkgs.lib.nixosSystem {
            inherit system;
            modules = [
              self.nixosModules.channel
              ({ ... }: {
                system.stateVersion = "26.05";
                users.users.channel-user.isNormalUser = true;
                services.nix-control-manager-helper = {
                  enable = true;
                  mode = "live-read-only";
                  targetId = "live";
                  allowedUsers = [ "channel-user" ];
                };
                programs.nix-control-manager.enable = true;
              })
            ];
          };
          service = evaluated.config.systemd.services.nix-control-manager-helper;
          socket = evaluated.config.systemd.sockets.nix-control-manager-helper;
          serviceUnit = evaluated.config.systemd.units."nix-control-manager-helper.service".unit;
          socketUnit = evaluated.config.systemd.units."nix-control-manager-helper.socket".unit;
          liveService = evaluatedLiveReadOnly.config.systemd.services.nix-control-manager-helper;
          liveServiceUnit = evaluatedLiveReadOnly.config.systemd.units."nix-control-manager-helper.service".unit;
          liveTestService = evaluatedLiveTest.config.systemd.services.nix-control-manager-helper;
          liveTestServiceUnit = evaluatedLiveTest.config.systemd.units."nix-control-manager-helper.service".unit;
          liveHomeService = evaluatedLiveHomeManager.config.systemd.services.nix-control-manager-helper;
          liveHomeServiceUnit = evaluatedLiveHomeManager.config.systemd.units."nix-control-manager-helper.service".unit;
          liveManagedService = evaluatedLiveManaged.config.systemd.services.nix-control-manager-helper;
          liveManagedServiceUnit = evaluatedLiveManaged.config.systemd.units."nix-control-manager-helper.service".unit;
          liveManagedGuiUnit = evaluatedLiveManaged.config.systemd.user.units."nix-control-manager-gui.service".unit;
          liveControlService = evaluatedLiveControl.config.systemd.services.nix-control-manager-helper;
          liveControlServiceUnit = evaluatedLiveControl.config.systemd.units."nix-control-manager-helper.service".unit;
          liveControlGuiService =
            evaluatedLiveControl.config.systemd.user.services.nix-control-manager-gui;
          liveControlGuiUnit =
            evaluatedLiveControl.config.systemd.user.units."nix-control-manager-gui.service".unit;
          channelService = evaluatedChannel.config.systemd.services.nix-control-manager-helper;
          channelSocket = evaluatedChannel.config.systemd.sockets.nix-control-manager-helper;
          channelPackage = evaluatedChannel.config.services.nix-control-manager-helper.package;
          channelGuiService =
            evaluatedChannel.config.systemd.user.services.nix-control-manager-gui;
          channelGuiUnit =
            evaluatedChannel.config.systemd.user.units."nix-control-manager-gui.service".unit;
          channelClient = nixpkgs.lib.findFirst
            (package: nixpkgs.lib.getName package == "nix-control-manager-client")
            null
            evaluatedChannel.config.environment.systemPackages;
          liveTargetEvaluation = builtins.tryEval (
            (nixpkgs.lib.nixosSystem {
              inherit system;
              modules = [
                self.nixosModules.default
                ({ ... }: {
                  system.stateVersion = "26.05";
                  services.nix-control-manager-helper = {
                    enable = true;
                    fixtureRoot = "/etc/nixos";
                  };
                })
              ];
            }).config.system.build.toplevel
          );
          transitionCandidate = pkgs.runCommand "ncm-transition-candidate" { } ''
            mkdir -p "$out/bin"
            printf '#!/bin/sh\nexit 0\n' > "$out/bin/switch-to-configuration"
            chmod +x "$out/bin/switch-to-configuration"
          '';
          transitionPrevious = pkgs.runCommand "ncm-transition-previous" { } ''
            mkdir -p "$out/bin"
            printf '#!/bin/sh\nexit 0\n' > "$out/bin/switch-to-configuration"
            chmod +x "$out/bin/switch-to-configuration"
          '';
        in {
          settings-options = import ./tests/nixos/settings-options-check.nix {
            inherit pkgs;
          };
          package-catalog = import ./tests/nixos/package-catalog-check.nix {
            inherit pkgs;
          };
          release-smoke = import ./tests/nixos/release-smoke-check.nix {
            inherit pkgs;
            ncmPackage = self.packages.${system}.default;
          };
          web-settings = pkgs.runCommand "nix-control-manager-web-settings-check" {
            nativeBuildInputs = [ pkgs.nodejs ];
          } ''
            NCM_SETTINGS_JS=${./src/nix_control_manager/web/settings.js} \
              node ${./tests/test_web_settings.js}
            NCM_SETTINGS_JS=${./src/nix_control_manager/web/settings.js} \
              NCM_CATALOG_JS=${./src/nix_control_manager/web/catalog.js} \
              node ${./tests/test_web_catalog.js}
            NCM_FLAKES_JS=${./src/nix_control_manager/web/flakes.js} \
              node ${./tests/test_web_flakes.js}
            node --check ${./src/nix_control_manager/web/settings.js}
            node --check ${./src/nix_control_manager/web/catalog.js}
            node --check ${./src/nix_control_manager/web/flakes.js}
            node --check ${./src/nix_control_manager/web/app.js}
            touch "$out"
          '';
          activation-transition = pkgs.runCommand "nix-control-manager-activation-transition-check" {
            nativeBuildInputs = [ pkgs.python3 ];
          } ''
            export PYTHONPATH=${./src}
            export NCM_TEST_CANDIDATE_SYSTEM=${transitionCandidate}
            export NCM_TEST_PREVIOUS_SYSTEM=${transitionPrevious}
            python3 ${./tests/test_activation_transition.py}
            touch "$out"
          '';
          home-manager-detection = pkgs.runCommand "nix-control-manager-home-manager-detection-check" {
            nativeBuildInputs = [ self.packages.${system}.default pkgs.jq pkgs.nix pkgs.python3 ];
          } ''
            mkdir -p fixture/etc-nixos fixture/home-manager
            cat > fixture/etc-nixos/flake.nix <<'EOF'
            { home-manager, ... }: {
              modules = [ home-manager.nixosModules.home-manager ];
              home-manager.users.fixture-user = ./home.nix;
            }
            EOF
            cat > fixture/etc-nixos/configuration.nix <<'EOF'
            { ... }:
            {
              imports = [
              ];
              home-manager.users.fixture-user = ./home.nix;
            }
            EOF
            cat > fixture/home-manager/home.nix <<'EOF'
            { ... }:
            {
              home.username = "standalone-user";
              home.stateVersion = "26.05";
            }
            EOF
            ncm detect-home-manager \
              --config-root fixture/etc-nixos \
              --standalone-root fixture/home-manager \
              --user-state fixture/user-state.json \
              --json > inspection.json
            jq -e '
              .status == "detected"
              and .writeEnabled == false
              and .activationEnabled == false
              and (.integrations | sort) == ["nixos-module", "standalone"]
              and ([.users[].name] | sort) == ["fixture-user", "standalone-user"]
              and .userState.status == "missing"
            ' inspection.json
            test ! -e fixture/user-state.json
            ncm preview-home-manager \
              --user fixture-user \
              --integration nixos-module \
              --package firefox \
              --package git \
              --output fixture/managed-home-fixture-user.nix \
              --json > preview.json
            jq -e '
              .username == "fixture-user"
              and .integration == "nixos-module"
              and .readOnly == true
              and .writeEnabled == false
              and .activationEnabled == false
              and .flakeInputMutationEnabled == false
              and (.generated | contains("home.packages"))
              and (.generated | contains("pkgs.firefox"))
            ' preview.json
            export NIX_STATE_DIR="$TMPDIR/nix-state"
            mkdir -p "$NIX_STATE_DIR/profiles"
            jq -r .generated preview.json | nix-instantiate --parse - >/dev/null
            test ! -e fixture/managed-home-fixture-user.nix
            ncm plan-home-manager-adoption \
              --config-root fixture/etc-nixos \
              --standalone-root fixture/home-manager \
              --user-state fixture/user-state.json \
              --user fixture-user \
              --integration nixos-module \
              --package firefox \
              --json > adoption.json
            jq -e '
              .status == "ready"
              and .safeToValidate == true
              and .safeToApply == false
              and .writeEnabled == false
              and (.changes | length) == 4
              and (.combinedDiff | contains("home-manager-fixture-user.nix"))
              and (.combinedDiff | contains("ncm/user-state.json"))
            ' adoption.json
            test ! -e fixture/etc-nixos/ncm
            ncm validate-home-manager-adoption \
              --config-root fixture/etc-nixos \
              --standalone-root fixture/home-manager \
              --user-state fixture/user-state.json \
              --user standalone-user \
              --integration standalone \
              --package git \
              --json > validation.json
            jq -e '
              .status == "passed"
              and .workingCopyRemoved == true
              and (.planFingerprint | length) == 64
              and (.candidateDigests | length) == 3
              and .writeEnabled == false
              and .buildEnabled == false
              and .activationEnabled == false
            ' validation.json
            test ! -e fixture/home-manager/ncm
            export HOME="$TMPDIR/home"
            mkdir -p "$HOME"
            PYTHONPATH=${./src} python3 ${./tests/integration_home_manager_fixture_real_nix.py} \
              --root fixture/home-manager-transaction \
              --journal fixture/home-manager-journals > transaction.json
            jq -e '
              .state == "committed"
              and .fixtureOnly == true
              and .liveWriteEnabled == false
              and .activationEnabled == false
              and .transaction.state == "committed"
            ' transaction.json
            PYTHONPATH=${./src} python3 ${./tests/integration_home_manager_fixture_helper_real_nix.py} \
              --root fixture/home-manager-helper \
              --journal fixture/home-manager-helper-journals \
              --socket fixture/home-manager-helper.sock > helper-transaction.json
            jq -e '
              .state == "committed"
              and .fixtureOnly == true
              and .liveWriteEnabled == false
              and .activationEnabled == false
              and .filesWritten == 3
            ' helper-transaction.json
            mkdir "$out"
            cp inspection.json preview.json adoption.json validation.json \
              transaction.json helper-transaction.json "$out"/
          '';
          nixos-module =
            assert liveTargetEvaluation.success == false;
            assert service.serviceConfig.ProtectSystem == "strict";
            assert service.serviceConfig.PrivateNetwork == true;
            assert service.serviceConfig.NoNewPrivileges == true;
            assert service.serviceConfig.RestrictAddressFamilies == [ "AF_UNIX" ];
            assert service.environment.HOME == "/tmp";
            assert !(builtins.hasAttr "ReadWritePaths" liveService.serviceConfig);
            assert !(builtins.hasAttr "StateDirectory" liveService.serviceConfig);
            assert liveService.serviceConfig.ReadOnlyPaths == [ "/etc/nixos" ];
            assert liveService.serviceConfig.CapabilityBoundingSet == "";
            assert liveTestService.serviceConfig.ReadOnlyPaths == [ "/etc/nixos" ];
            assert liveTestService.serviceConfig.ReadWritePaths == [ "/var/lib/nix-control-manager/test-activations" ];
            assert liveTestService.serviceConfig.CapabilityBoundingSet == "";
            assert !(builtins.hasAttr "StateDirectory" liveTestService.serviceConfig);
            assert liveTestService.requires == [ ];
            assert liveTestService.wants == [ "polkit.service" ];
            assert liveTestService.restartIfChanged == false;
            assert liveHomeService.serviceConfig.ReadWritePaths == [
              "/etc/nixos"
              "/var/lib/nix-control-manager/home-manager-transactions"
            ];
            assert liveHomeService.serviceConfig.CapabilityBoundingSet == "";
            assert !(builtins.hasAttr "StateDirectory" liveHomeService.serviceConfig);
            assert liveManagedService.serviceConfig.ReadWritePaths == [
              "/etc/nixos/ncm"
              "/var/lib/nix-control-manager/managed-transactions"
            ];
            assert liveManagedService.serviceConfig.CapabilityBoundingSet == "";
            assert !(builtins.hasAttr "StateDirectory" liveManagedService.serviceConfig);
            assert liveControlService.serviceConfig.ReadWritePaths == [
              "/etc/nixos/ncm"
              "/var/lib/nix-control-manager/managed-transactions"
              "/var/lib/nix-control-manager/test-activations"
              "/etc/nixos/flake.lock"
              "/var/lib/nix-control-manager/flake-lock-transactions"
            ];
            assert liveControlService.serviceConfig.CapabilityBoundingSet == "";
            assert !(builtins.hasAttr "StateDirectory" liveControlService.serviceConfig);
            assert liveControlService.requires == [ ];
            assert liveControlService.wants == [ "polkit.service" ];
            assert liveControlService.restartIfChanged == false;
            assert liveControlGuiService.restartIfChanged == false;
            assert socket.socketConfig.SocketMode == "0660";
            assert socket.socketConfig.SocketGroup == "nix-control-manager";
            pkgs.runCommand "nix-control-manager-module-check" { } ''
              test -x ${self.packages.${system}.default}/bin/ncm-helper
              test -x ${self.packages.${system}.default}/bin/ncm-system-transition
              grep -F 'ProtectSystem=strict' ${serviceUnit}/nix-control-manager-helper.service
              grep -F 'PrivateNetwork=true' ${serviceUnit}/nix-control-manager-helper.service
              grep -F 'NoNewPrivileges=true' ${serviceUnit}/nix-control-manager-helper.service
              grep -F 'HOME=/tmp' ${serviceUnit}/nix-control-manager-helper.service
              grep -F 'SocketMode=0660' ${socketUnit}/nix-control-manager-helper.socket
              grep -F 'SocketGroup=nix-control-manager' ${socketUnit}/nix-control-manager-helper.socket
              grep -F 'ReadOnlyPaths=/etc/nixos' ${liveServiceUnit}/nix-control-manager-helper.service
              grep -x 'CapabilityBoundingSet=' ${liveServiceUnit}/nix-control-manager-helper.service
              grep -F 'ReadOnlyPaths=/etc/nixos' ${liveTestServiceUnit}/nix-control-manager-helper.service
              grep -F 'ReadWritePaths=/var/lib/nix-control-manager/test-activations' ${liveTestServiceUnit}/nix-control-manager-helper.service
              grep -x 'CapabilityBoundingSet=' ${liveTestServiceUnit}/nix-control-manager-helper.service
              grep -F 'Wants=polkit.service' ${liveTestServiceUnit}/nix-control-manager-helper.service
              if grep -F 'Requires=polkit.service' ${liveTestServiceUnit}/nix-control-manager-helper.service; then
                echo 'live-test service unexpectedly requires polkit' >&2
                exit 1
              fi
              grep -F 'ReadWritePaths=/etc/nixos' ${liveHomeServiceUnit}/nix-control-manager-helper.service
              grep -F 'ReadWritePaths=/var/lib/nix-control-manager/home-manager-transactions' ${liveHomeServiceUnit}/nix-control-manager-helper.service
              grep -x 'CapabilityBoundingSet=' ${liveHomeServiceUnit}/nix-control-manager-helper.service
              grep -F 'ReadWritePaths=/etc/nixos/ncm' ${liveManagedServiceUnit}/nix-control-manager-helper.service
              grep -F 'ReadWritePaths=/var/lib/nix-control-manager/managed-transactions' ${liveManagedServiceUnit}/nix-control-manager-helper.service
              grep -x 'CapabilityBoundingSet=' ${liveManagedServiceUnit}/nix-control-manager-helper.service
              grep -F 'ReadWritePaths=/etc/nixos/ncm' ${liveControlServiceUnit}/nix-control-manager-helper.service
              grep -F 'ReadWritePaths=/var/lib/nix-control-manager/managed-transactions' ${liveControlServiceUnit}/nix-control-manager-helper.service
              grep -F 'ReadWritePaths=/var/lib/nix-control-manager/test-activations' ${liveControlServiceUnit}/nix-control-manager-helper.service
              grep -F 'ReadWritePaths=/etc/nixos/flake.lock' ${liveControlServiceUnit}/nix-control-manager-helper.service
              grep -F 'ReadWritePaths=/var/lib/nix-control-manager/flake-lock-transactions' ${liveControlServiceUnit}/nix-control-manager-helper.service
              grep -x 'CapabilityBoundingSet=' ${liveControlServiceUnit}/nix-control-manager-helper.service
              grep -F 'Wants=polkit.service' ${liveControlServiceUnit}/nix-control-manager-helper.service
              if grep -F 'Requires=polkit.service' ${liveControlServiceUnit}/nix-control-manager-helper.service; then
                echo 'live-control service unexpectedly requires polkit' >&2
                exit 1
              fi
              grep -F 'X-RestartIfChanged=false' ${liveControlGuiUnit}/nix-control-manager-gui.service
              grep -F -- '--helper-socket /run/nix-control-manager/helper.sock' ${liveManagedGuiUnit}/nix-control-manager-gui.service
              grep -F -- '--helper-target managed' ${liveManagedGuiUnit}/nix-control-manager-gui.service
              if grep -F 'ReadWritePaths=' ${liveServiceUnit}/nix-control-manager-helper.service; then
                echo 'live-read-only service unexpectedly has ReadWritePaths' >&2
                exit 1
              fi
              if grep -F 'StateDirectory=' ${liveServiceUnit}/nix-control-manager-helper.service; then
                echo 'live-read-only service unexpectedly has StateDirectory' >&2
                exit 1
              fi
              if grep -F 'StateDirectory=' ${liveTestServiceUnit}/nix-control-manager-helper.service; then
                echo 'live-test service unexpectedly has StateDirectory' >&2
                exit 1
              fi
              mkdir -p "$out"
              cp ${serviceUnit}/nix-control-manager-helper.service "$out/"
              cp ${socketUnit}/nix-control-manager-helper.socket "$out/"
              cp ${liveServiceUnit}/nix-control-manager-helper.service "$out/live-read-only.service"
              cp ${liveTestServiceUnit}/nix-control-manager-helper.service "$out/live-test.service"
              cp ${liveHomeServiceUnit}/nix-control-manager-helper.service "$out/live-home-manager.service"
              cp ${liveManagedServiceUnit}/nix-control-manager-helper.service "$out/live-managed.service"
              cp ${liveControlServiceUnit}/nix-control-manager-helper.service "$out/live-control.service"
              touch "$out/passed"
            '';
          channel-module =
            assert channelPackage.pname == "nix-control-manager";
            assert channelService.serviceConfig.ReadOnlyPaths == [ "/etc/nixos" ];
            assert channelService.serviceConfig.CapabilityBoundingSet == "";
            assert !(builtins.hasAttr "ReadWritePaths" channelService.serviceConfig);
            assert channelSocket.socketConfig.SocketMode == "0660";
            assert evaluatedChannel.config.users.groups.nix-control-manager.members == [ "channel-user" ];
            assert channelClient != null;
            assert channelGuiService.serviceConfig.ProtectSystem == "strict";
            assert channelGuiService.serviceConfig.ReadOnlyPaths == [ "/etc/nixos" ];
            assert channelGuiService.serviceConfig.KillSignal == "SIGINT";
            pkgs.runCommand "nix-control-manager-channel-module-check" { } ''
              test -x ${channelPackage}/bin/ncm
              test -x ${channelPackage}/bin/ncm-helper
              test -x ${channelClient}/bin/ncm-gui
              grep -F -- 'systemctl --user start' ${channelClient}/bin/ncm-gui
              grep -F -- 'systemctl --user stop' ${channelClient}/bin/ncm-gui
              grep -F -- 'localWriteEnabled' ${channelClient}/bin/ncm-gui
              desktop_exec="$(sed -n 's/^Exec=//p' \
                ${channelClient}/share/applications/nix-control-manager.desktop)"
              test -x "$desktop_exec"
              grep -F -- '--read-only' \
                ${channelGuiUnit}/nix-control-manager-gui.service
              grep -F 'KillSignal=SIGINT' \
                ${channelGuiUnit}/nix-control-manager-gui.service
              grep -F 'ProtectSystem=strict' \
                ${channelGuiUnit}/nix-control-manager-gui.service
              if grep -F '[Install]' \
                ${channelGuiUnit}/nix-control-manager-gui.service; then
                echo 'GUI user service must remain on-demand' >&2
                exit 1
              fi
              touch "$out"
            '';
        } // nixpkgs.lib.optionalAttrs (system == "x86_64-linux") {
          helper-vm = self.packages.${system}.helper-vm-test;
          live-read-only-ui-vm = self.packages.${system}.live-read-only-ui-vm-test;
          live-test-recovery-vm = self.packages.${system}.live-test-recovery-vm-test;
          live-home-manager-vm = self.packages.${system}.live-home-manager-vm-test;
          live-managed-vm = self.packages.${system}.live-managed-vm-test;
          live-control-vm = self.packages.${system}.live-control-vm-test;
        });

      devShells = forAllSystems (system:
        let pkgs = nixpkgs.legacyPackages.${system};
        in {
          default = pkgs.mkShell {
            packages = [ pkgs.python3 pkgs.python3Packages.setuptools ];
            shellHook = ''
              export PYTHONPATH="$PWD/src''${PYTHONPATH:+:$PYTHONPATH}"
            '';
          };
        });
    };
}
