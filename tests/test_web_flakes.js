"use strict";

const assert = require("node:assert/strict");
const Flakes = require(
  process.env.NCM_FLAKES_JS || "../src/nix_control_manager/web/flakes.js",
);

function fixture() {
  return {
    schemaVersion: 1,
    status: "detected",
    readOnly: true,
    networkAccessEnabled: false,
    lockWriteEnabled: false,
    inputUpdateEnabled: false,
    root: "/etc/nixos",
    files: {
      flake: "/etc/nixos/flake.nix",
      flakeExists: true,
      lock: "/etc/nixos/flake.lock",
      lockExists: true,
    },
    lock: { status: "valid", version: 7, rootNode: "root" },
    inputs: [{
      name: "nixpkgs", node: "nixpkgs", follows: [], locked: true, type: "github",
      source: "github:NixOS/nixpkgs", ref: "nixos-unstable", revision: "a".repeat(40),
      lastModified: 1787000000, lastModifiedDate: "2026-08-17", narHash: "sha256-example",
    }],
    nixosConfigurations: ["desktop"],
    activeTarget: "desktop",
    activeTargetStatus: "selected",
    evaluation: { status: "passed", offline: true, noWriteLockFile: true, durationMs: 42 },
    warnings: [],
  };
}

{
  const value = Flakes.normalizeFlakeInspection(fixture());
  assert.equal(value.inputs[0].name, "nixpkgs");
  assert.deepEqual(Flakes.flakeSummary(value), {
    inputs: 1, locked: 1, follows: 0, targets: 1, warnings: 0,
  });
}

{
  const unsafe = fixture();
  unsafe.lockWriteEnabled = true;
  assert.throws(() => Flakes.normalizeFlakeInspection(unsafe), /read-only/);
}

{
  const extra = fixture();
  extra.unexpected = true;
  assert.throws(() => Flakes.normalizeFlakeInspection(extra), /схема/);
}

{
  const duplicate = fixture();
  duplicate.nixosConfigurations.push("desktop");
  assert.throws(() => Flakes.normalizeFlakeInspection(duplicate), /Повторювані/);
}

console.log("web flakes helpers: ok");
