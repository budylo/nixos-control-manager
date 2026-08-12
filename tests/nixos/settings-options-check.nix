{ pkgs }:
let
  lib = pkgs.lib;
  catalog = builtins.fromJSON (
    builtins.readFile ../../src/nix_control_manager/data/settings_catalog.json
  );
  catalogByPath = builtins.listToAttrs (
    map (definition: { name = definition.path; value = definition; }) catalog
  );
  dependencies = lib.concatMap (definition:
    map (rule: { owner = definition; inherit rule; }) (definition.requires or [ ])
  ) catalog;
  missingDependencyPaths = map (dependency: dependency.rule.path) (
    builtins.filter (dependency: !(builtins.hasAttr dependency.rule.path catalogByPath)) dependencies
  );
  activeForDefault = dependency:
    dependency.rule.when == "always"
    || (dependency.rule.when == "true" && dependency.owner.default == true)
    || (dependency.rule.when == "non-empty" && dependency.owner.default != [ ]);
  inconsistentDependencyDefaults = map (dependency: dependency.owner.path) (
    builtins.filter (dependency:
      activeForDefault dependency
      && (builtins.getAttr dependency.rule.path catalogByPath).default
        != dependency.rule.requiredValue
    ) dependencies
  );
  evaluated = import (pkgs.path + "/nixos") {
    system = pkgs.stdenv.hostPlatform.system;
    configuration = { ... }: { system.stateVersion = "26.05"; };
  };
  optionExists = definition:
    lib.attrByPath (lib.splitString "." definition.path) null evaluated.options != null;
  missing = map (definition: definition.path) (builtins.filter (definition: !optionExists definition) catalog);
  catalogModule = lib.foldl' lib.recursiveUpdate { } (
    map (definition:
      lib.setAttrByPath (lib.splitString "." definition.path) definition.default
    ) catalog
  );
  configured = import (pkgs.path + "/nixos") {
    system = pkgs.stdenv.hostPlatform.system;
    configuration = { ... }: lib.recursiveUpdate catalogModule {
      system.stateVersion = "26.05";
    };
  };
  mismatched = map (definition: definition.path) (
    builtins.filter (definition:
      lib.attrByPath (lib.splitString "." definition.path) null configured.config
        != definition.default
    ) catalog
  );
  unexpectedPriority = map (definition: definition.path) (
    builtins.filter (definition:
      (lib.attrByPath (lib.splitString "." definition.path) null configured.options).highestPrio
        != 100
    ) catalog
  );
  mergeFixture = import (pkgs.path + "/nixos") {
    system = pkgs.stdenv.hostPlatform.system;
    configuration = { ... }: {
      imports = [
        ({ ... }: { networking.firewall.allowedTCPPorts = [ 22 ]; })
        ({ ... }: { networking.firewall.allowedTCPPorts = [ 443 ]; })
      ];
      system.stateVersion = "26.05";
    };
  };
  equalScalarFixture = import (pkgs.path + "/nixos") {
    system = pkgs.stdenv.hostPlatform.system;
    configuration = { ... }: {
      imports = [
        ({ ... }: { services.openssh.enable = true; })
        ({ ... }: { services.openssh.enable = true; })
      ];
      system.stateVersion = "26.05";
    };
  };
  forceFixture = import (pkgs.path + "/nixos") {
    system = pkgs.stdenv.hostPlatform.system;
    configuration = { lib, ... }: {
      time.timeZone = lib.mkForce "UTC";
      system.stateVersion = "26.05";
    };
  };
  conflictEvaluation = builtins.tryEval (
    (import (pkgs.path + "/nixos") {
      system = pkgs.stdenv.hostPlatform.system;
      configuration = { ... }: {
        imports = [
          ({ ... }: { services.openssh.enable = true; })
          ({ ... }: { services.openssh.enable = false; })
        ];
        system.stateVersion = "26.05";
      };
    }).config.services.openssh.enable
  );
in
assert lib.assertMsg (missing == [ ])
  "Nix Control Manager settings catalog contains missing NixOS options: ${lib.concatStringsSep ", " missing}";
assert lib.assertMsg (mismatched == [ ])
  "Nix Control Manager settings defaults fail NixOS type/merge evaluation: ${lib.concatStringsSep ", " mismatched}";
assert lib.assertMsg (unexpectedPriority == [ ])
  "Nix Control Manager normal settings do not expose priority 100: ${lib.concatStringsSep ", " unexpectedPriority}";
assert lib.assertMsg (missingDependencyPaths == [ ])
  "Settings dependencies reference missing catalog paths: ${lib.concatStringsSep ", " missingDependencyPaths}";
assert lib.assertMsg (inconsistentDependencyDefaults == [ ])
  "Settings defaults violate dependencies: ${lib.concatStringsSep ", " inconsistentDependencyDefaults}";
assert lib.assertMsg
  (mergeFixture.config.networking.firewall.allowedTCPPorts == [ 22 443 ]
    && mergeFixture.options.networking.firewall.allowedTCPPorts.highestPrio == 100
    && builtins.length mergeFixture.options.networking.firewall.allowedTCPPorts.definitionsWithLocations >= 2)
  "List merge metadata is not available as expected";
assert lib.assertMsg
  (equalScalarFixture.config.services.openssh.enable
    && builtins.length equalScalarFixture.options.services.openssh.enable.definitionsWithLocations == 2)
  "Equal scalar definition metadata is not available as expected";
assert lib.assertMsg
  (forceFixture.options.time.timeZone.highestPrio == 50)
  "mkForce priority metadata is not available as expected";
assert lib.assertMsg (!conflictEvaluation.success)
  "Conflicting scalar definitions unexpectedly evaluated";
pkgs.runCommand "nix-control-manager-settings-options-check" { } ''
  mkdir -p "$out"
  ${lib.concatMapStringsSep "\n" (definition: "echo ${lib.escapeShellArg definition.path} >> $out/options") catalog}
''
