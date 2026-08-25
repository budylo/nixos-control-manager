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
  const previewStatuses = new Set([
    "analyzing", "blocked", "cancelled", "cancelling", "cleaning", "failed",
    "idle", "no-change", "passed", "preparing", "queued", "running", "unavailable",
  ]);
  const previewKeys = [
    "activationEnabled", "after", "applyEnabled", "before", "candidateOnlyChanges",
    "applied", "beforeLockSha256", "candidateLockSha256",
    "cancelRequested", "cancellable", "changedNodeCount", "changedNodes", "command",
    "createdAt", "durationMs", "effectiveUid", "error", "events", "exitCode",
    "finishedAt", "inputName", "jobId", "lockDiff", "logsTruncated", "networkRequired",
    "nextCursor", "nixStoreWriteExpected", "privileged", "schemaVersion", "sourceFingerprint",
    "planFingerprint", "readyForApply", "transactionId",
    "sourceUnchanged", "sourceWriteEnabled", "startedAt", "status", "temporaryCopyRemoved",
    "temporaryLockWriteEnabled", "timedOut",
  ];

  function exactKeys(value, expected) {
    return value && typeof value === "object" && !Array.isArray(value)
      && JSON.stringify(Object.keys(value).sort()) === JSON.stringify([...expected].sort());
  }

  function string(value, { nullable = false, max = 4096 } = {}) {
    if (nullable && value === null) return null;
    if (typeof value !== "string" || value.length > max) throw new Error("Некоректний текст у звіті Flakes");
    return value;
  }

  function stringList(value, { maxItems = 512, maxLength = 128, unique = true } = {}) {
    if (!Array.isArray(value) || value.length > maxItems) throw new Error("Некоректний список у звіті Flakes");
    const result = value.map((item) => string(item, { max: maxLength }));
    if (unique && new Set(result).size !== result.length) throw new Error("Повторювані значення у звіті Flakes");
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

  function nullableNumber(value, label) {
    if (value === null) return null;
    if (typeof value !== "number" || !Number.isFinite(value) || value < 0) {
      throw new Error(`Некоректне поле ${label} у preview Flakes`);
    }
    return value;
  }

  function normalizePreviewEvent(value) {
    if (!exactKeys(value, ["message", "sequence", "stream", "timestamp"])
      || !Number.isInteger(value.sequence) || value.sequence < 1) {
      throw new Error("Некоректна подія preview Flakes");
    }
    return {
      sequence: value.sequence,
      timestamp: nullableNumber(value.timestamp, "timestamp"),
      stream: string(value.stream, { max: 32 }),
      message: string(value.message, { max: 1000 }),
    };
  }

  function normalizeFlakeUpdatePreview(value) {
    if (!exactKeys(value, previewKeys) || value.schemaVersion !== 1
      || !previewStatuses.has(value.status)) {
      throw new Error("Некоректна схема update-preview Flakes");
    }
    if (value.networkRequired !== true || value.sourceWriteEnabled !== false
      || value.temporaryLockWriteEnabled !== true || value.nixStoreWriteExpected !== true
      || value.applyEnabled !== false || value.activationEnabled !== false) {
      throw new Error("Update-preview Flakes порушує preview-only межу");
    }
    for (const key of [
      "sourceUnchanged", "candidateOnlyChanges", "temporaryCopyRemoved", "cancelRequested",
      "timedOut", "cancellable", "privileged", "logsTruncated",
      "applied", "readyForApply",
    ]) {
      if (typeof value[key] !== "boolean") throw new Error(`Некоректне поле ${key} у preview Flakes`);
    }
    const idle = value.status === "idle";
    const jobId = string(value.jobId, { nullable: true, max: 24 });
    const inputName = string(value.inputName, { nullable: true, max: 128 });
    if (idle ? (jobId !== null || inputName !== null) : !/^[0-9a-f]{24}$/.test(jobId || "")) {
      throw new Error("Некоректний ідентифікатор update-preview Flakes");
    }
    if (!idle && !/^[A-Za-z0-9_-]{1,128}$/.test(inputName || "")) {
      throw new Error("Некоректний input update-preview Flakes");
    }
    if (value.exitCode !== null && !Number.isInteger(value.exitCode)) {
      throw new Error("Некоректний exit code update-preview Flakes");
    }
    if (value.effectiveUid !== null && (!Number.isInteger(value.effectiveUid) || value.effectiveUid < 0)) {
      throw new Error("Некоректний UID update-preview Flakes");
    }
    if (!Number.isInteger(value.nextCursor) || value.nextCursor < 0
      || !Number.isInteger(value.changedNodeCount) || value.changedNodeCount < 0) {
      throw new Error("Некоректний лічильник update-preview Flakes");
    }
    const changedNodes = stringList(value.changedNodes);
    if (changedNodes.length !== value.changedNodeCount) {
      throw new Error("Кількість змінених lock-вузлів не збігається");
    }
    const command = stringList(value.command, { maxItems: 32, maxLength: 4096, unique: false });
    const events = Array.isArray(value.events) && value.events.length <= 256
      ? value.events.map(normalizePreviewEvent)
      : null;
    if (!events || new Set(events.map((event) => event.sequence)).size !== events.length) {
      throw new Error("Некоректний журнал update-preview Flakes");
    }
    let error = null;
    if (value.error !== null) {
      if (!exactKeys(value.error, ["code", "message"])) throw new Error("Некоректна помилка preview Flakes");
      error = {
        code: string(value.error.code, { max: 128 }),
        message: string(value.error.message, { max: 4096 }),
      };
    }
    const before = value.before === null ? null : normalizeInput(value.before);
    const after = value.after === null ? null : normalizeInput(value.after);
    const sourceFingerprint = string(value.sourceFingerprint, { nullable: true, max: 64 });
    if (sourceFingerprint !== null && !/^[0-9a-f]{64}$/.test(sourceFingerprint)) {
      throw new Error("Некоректний fingerprint update-preview Flakes");
    }
    for (const key of ["beforeLockSha256", "candidateLockSha256", "planFingerprint"]) {
      const digest = string(value[key], { nullable: true, max: 64 });
      if (digest !== null && !/^[0-9a-f]{64}$/.test(digest)) throw new Error(`Некоректний ${key}`);
    }
    const transactionId = string(value.transactionId, { nullable: true, max: 24 });
    if (transactionId !== null && !/^[0-9a-f]{24}$/.test(transactionId)) throw new Error("Некоректна транзакція flake.lock");
    if (value.readyForApply && (value.status !== "passed" || !value.planFingerprint || value.applied)) {
      throw new Error("Некоректна готовність flake.lock до запису");
    }
    if (["passed", "no-change"].includes(value.status)
      && (!before || !after || value.exitCode !== 0 || value.sourceUnchanged !== true
        || value.candidateOnlyChanges !== true || value.temporaryCopyRemoved !== true)) {
      throw new Error("Завершений update-preview Flakes не підтвердив безпечну межу");
    }
    const lockDiff = string(value.lockDiff, { max: 128000 });
    if (value.status === "passed" && !lockDiff) throw new Error("Update-preview не містить lock diff");
    if (value.status === "no-change" && lockDiff) throw new Error("No-change preview містить неочікуваний diff");
    return {
      ...value,
      jobId,
      inputName,
      createdAt: nullableNumber(value.createdAt, "createdAt"),
      startedAt: nullableNumber(value.startedAt, "startedAt"),
      finishedAt: nullableNumber(value.finishedAt, "finishedAt"),
      durationMs: nullableNumber(value.durationMs, "durationMs"),
      command,
      before,
      after,
      changedNodes,
      lockDiff,
      sourceFingerprint,
      error,
      events,
    };
  }

  function isUpdatePreviewEligible(input) {
    return Boolean(input?.locked && (!input.follows || input.follows.length === 0)
      && !new Set(["follows", "indirect", "path", "unknown"]).has(input.type));
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

  return {
    normalizeFlakeInspection,
    normalizeFlakeUpdatePreview,
    isUpdatePreviewEligible,
    flakeSummary,
  };
}));
