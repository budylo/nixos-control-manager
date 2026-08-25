(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.NcmFlakes = api;
}(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const topKeys = [
    "activeTarget", "activeTargetStatus", "evaluation", "files", "inputUpdateEnabled",
    "inputs", "lock", "lockWriteEnabled", "networkAccessEnabled", "nixosConfigurations",
    "readOnly", "root", "schemaVersion", "status", "warnings",
  ];
  const inputKeys = [
    "follows", "lastModified", "lastModifiedDate", "locked", "name", "narHash",
    "node", "ref", "revision", "source", "type",
  ];
  const statuses = new Set(["absent", "detected", "incomplete", "invalid"]);
  const lockStatuses = new Set(["attention", "invalid", "missing", "not-applicable", "valid"]);
  const evaluationStatuses = new Set([
    "blocked", "failed", "not-run", "passed", "timed-out", "unavailable",
  ]);
  const targetStatuses = new Set([
    "invalid", "missing", "not-applicable", "selected", "unverified",
  ]);

  function exactKeys(value, expected) {
    return value && typeof value === "object" && !Array.isArray(value)
      && JSON.stringify(Object.keys(value).sort()) === JSON.stringify([...expected].sort());
  }

  function string(value, { nullable = false, max = 4096 } = {}) {
    if (nullable && value === null) return null;
    if (typeof value !== "string" || value.length > max) throw new Error("Некоректний текст у звіті Flakes");
    return value;
  }

  function stringList(value, { maxItems = 512, maxLength = 128 } = {}) {
    if (!Array.isArray(value) || value.length > maxItems) throw new Error("Некоректний список у звіті Flakes");
    const result = value.map((item) => string(item, { max: maxLength }));
    if (new Set(result).size !== result.length) throw new Error("Повторювані значення у звіті Flakes");
    return result;
  }

  function normalizeInput(value) {
    if (!exactKeys(value, inputKeys)) throw new Error("Некоректна схема input у звіті Flakes");
    if (typeof value.locked !== "boolean") throw new Error("Некоректний locked-стан input");
    if (value.lastModified !== null && (!Number.isInteger(value.lastModified) || value.lastModified < 0)) {
      throw new Error("Некоректний час input");
    }
    return {
      name: string(value.name, { max: 128 }),
      node: string(value.node, { nullable: true, max: 128 }),
      follows: stringList(value.follows),
      locked: value.locked,
      type: string(value.type, { max: 64 }),
      source: string(value.source, { max: 512 }),
      ref: string(value.ref, { max: 512 }),
      revision: string(value.revision, { max: 512 }),
      lastModified: value.lastModified,
      lastModifiedDate: string(value.lastModifiedDate, { nullable: true, max: 32 }),
      narHash: string(value.narHash, { max: 512 }),
    };
  }

  function normalizeFlakeInspection(value) {
    if (!exactKeys(value, topKeys) || value.schemaVersion !== 1 || !statuses.has(value.status)) {
      throw new Error("Некоректна схема звіту Flakes");
    }
    if (value.readOnly !== true || value.networkAccessEnabled !== false
      || value.lockWriteEnabled !== false || value.inputUpdateEnabled !== false) {
      throw new Error("Звіт Flakes порушує read-only межу");
    }
    if (!exactKeys(value.files, ["flake", "flakeExists", "lock", "lockExists"])
      || typeof value.files.flakeExists !== "boolean" || typeof value.files.lockExists !== "boolean") {
      throw new Error("Некоректні файли у звіті Flakes");
    }
    if (!exactKeys(value.lock, ["rootNode", "status", "version"])
      || !lockStatuses.has(value.lock.status)
      || (value.lock.version !== null && (!Number.isInteger(value.lock.version) || value.lock.version < 1))) {
      throw new Error("Некоректний lock-стан у звіті Flakes");
    }
    if (!exactKeys(value.evaluation, ["durationMs", "noWriteLockFile", "offline", "status"])
      || !evaluationStatuses.has(value.evaluation.status)
      || value.evaluation.offline !== true || value.evaluation.noWriteLockFile !== true
      || !Number.isInteger(value.evaluation.durationMs) || value.evaluation.durationMs < 0) {
      throw new Error("Некоректний evaluation-стан у звіті Flakes");
    }
    if (!targetStatuses.has(value.activeTargetStatus)) throw new Error("Некоректна активна ціль Flakes");
    if (!Array.isArray(value.inputs) || value.inputs.length > 512) throw new Error("Забагато inputs у звіті Flakes");
    return {
      ...value,
      root: string(value.root),
      activeTarget: string(value.activeTarget, { nullable: true, max: 128 }),
      files: {
        flake: string(value.files.flake),
        flakeExists: value.files.flakeExists,
        lock: string(value.files.lock),
        lockExists: value.files.lockExists,
      },
      lock: {
        status: value.lock.status,
        version: value.lock.version,
        rootNode: string(value.lock.rootNode, { nullable: true, max: 128 }),
      },
      inputs: value.inputs.map(normalizeInput),
      nixosConfigurations: stringList(value.nixosConfigurations),
      evaluation: { ...value.evaluation },
      warnings: stringList(value.warnings, { maxItems: 128, maxLength: 4096 }),
    };
  }

  function flakeSummary(inspection) {
    const inputs = inspection?.inputs || [];
    const targets = inspection?.nixosConfigurations || [];
    return {
      inputs: inputs.length,
      locked: inputs.filter((item) => item.locked).length,
      follows: inputs.filter((item) => item.follows.length > 0).length,
      targets: targets.length,
      warnings: (inspection?.warnings || []).length,
    };
  }

  return { normalizeFlakeInspection, flakeSummary };
}));
