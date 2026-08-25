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

function previewFixture() {
  const before = structuredClone(fixture().inputs[0]);
  const after = { ...structuredClone(before), revision: "b".repeat(40), narHash: "sha256-after" };
  return {
    schemaVersion: 1,
    jobId: "c".repeat(24),
    status: "passed",
    inputName: "nixpkgs",
    createdAt: 1787000000,
    startedAt: 1787000001,
    finishedAt: 1787000002,
    durationMs: 1000,
    command: ["/bin/nix", "--option", "accept-flake-config", "false", "--option", "allow-import-from-derivation", "false"],
    exitCode: 0,
    before,
    after,
    changedNodes: ["nixpkgs"],
    changedNodeCount: 1,
    lockDiff: "--- flake.lock (current)\n+++ flake.lock (preview)\n",
    sourceFingerprint: "d".repeat(64),
    sourceUnchanged: true,
    candidateOnlyChanges: true,
    temporaryCopyRemoved: true,
    cancelRequested: false,
    timedOut: false,
    cancellable: false,
    effectiveUid: 1000,
    privileged: false,
    error: null,
    events: [{ sequence: 1, timestamp: 1787000000, stream: "status", message: "ready" }],
    nextCursor: 1,
    logsTruncated: false,
    networkRequired: true,
    sourceWriteEnabled: false,
    temporaryLockWriteEnabled: true,
    nixStoreWriteExpected: true,
    applyEnabled: false,
    activationEnabled: false,
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

{
  const value = Flakes.normalizeFlakeUpdatePreview(previewFixture());
  assert.equal(value.status, "passed");
  assert.equal(value.before.revision, "a".repeat(40));
  assert.equal(value.after.revision, "b".repeat(40));
  assert.equal(value.command.filter((item) => item === "--option").length, 2);
  assert.equal(Flakes.isUpdatePreviewEligible(value.before), true);
}

{
  const unsafe = previewFixture();
  unsafe.sourceWriteEnabled = true;
  assert.throws(() => Flakes.normalizeFlakeUpdatePreview(unsafe), /preview-only/);
}

{
  const incomplete = previewFixture();
  incomplete.temporaryCopyRemoved = false;
  assert.throws(() => Flakes.normalizeFlakeUpdatePreview(incomplete), /безпечну межу/);
}

{
  const noChange = previewFixture();
  noChange.status = "no-change";
  assert.throws(() => Flakes.normalizeFlakeUpdatePreview(noChange), /неочікуваний diff/);
}

{
  const pathInput = structuredClone(fixture().inputs[0]);
  pathInput.type = "path";
  assert.equal(Flakes.isUpdatePreviewEligible(pathInput), false);
}

console.log("web flakes helpers: ok");
