(function (root) {
  "use strict";

  const ATTRIBUTE_PATH = /^[A-Za-z_][A-Za-z0-9_'-]*(?:\.[A-Za-z_][A-Za-z0-9_'-]*)*$/;
  const STATE_FIELDS = new Set(["schemaVersion", "packages", "options"]);
  const COMPATIBILITY_STATUSES = new Set(["compatible", "incompatible", "unknown"]);
  const INSPECTION_STATUSES = new Set(["passed", "blocked", "unavailable", "timed-out", "failed"]);
  const COMPATIBILITY_REASONS = new Set([
    "available",
    "missing-attribute",
    "unsupported-platform",
    "broken-package",
    "evaluation-rejected",
    "inspection-unavailable",
  ]);

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function assertJsonValue(value, label, depth = 0) {
    if (depth > 16) throw new Error(`${label}: вкладеність завелика.`);
    if (value === null || ["boolean", "string"].includes(typeof value)) return;
    if (typeof value === "number" && Number.isFinite(value)) return;
    if (Array.isArray(value)) {
      if (value.length > 128) throw new Error(`${label}: масив містить забагато елементів.`);
      value.forEach((item) => assertJsonValue(item, label, depth + 1));
      return;
    }
    if (typeof value === "object" && Object.getPrototypeOf(value) === Object.prototype) {
      for (const [key, item] of Object.entries(value)) {
        if (!key) throw new Error(`${label}: порожня назва вкладеної опції.`);
        assertJsonValue(item, label, depth + 1);
      }
      return;
    }
    throw new Error(`${label}: непідтримуване значення.`);
  }

  function validateKnownOption(definition, value, settingsApi) {
    if (!definition || !settingsApi) return value;
    const parsed = settingsApi.parseEditorValue(
      definition,
      settingsApi.formatEditorValue(definition, value),
    );
    if (JSON.stringify(parsed) !== JSON.stringify(value)) {
      throw new Error(`${definition.name || definition.path}: значення не відповідає типу каталогу.`);
    }
    return value;
  }

  function normalizeProfile(raw, settingsDefinitions = [], settingsApi = root.NcmSettings) {
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
      throw new Error("Профіль повинен бути JSON-об’єктом.");
    }
    const unknown = Object.keys(raw).filter((key) => !STATE_FIELDS.has(key));
    if (unknown.length) throw new Error(`Невідомі поля профілю: ${unknown.sort().join(", ")}.`);
    if (raw.schemaVersion !== 1) throw new Error("Підтримується лише schemaVersion 1.");
    if (!Array.isArray(raw.packages)) throw new Error("packages повинно бути JSON-масивом.");
    if (raw.packages.length > 2048) throw new Error("Профіль містить забагато пакунків.");
    const packages = [];
    for (const attribute of raw.packages) {
      if (typeof attribute !== "string" || !ATTRIBUTE_PATH.test(attribute)) {
        throw new Error(`Некоректний шлях пакунка: ${JSON.stringify(attribute)}.`);
      }
      if (!packages.includes(attribute)) packages.push(attribute);
    }
    if (!raw.options || typeof raw.options !== "object" || Array.isArray(raw.options)) {
      throw new Error("options повинно бути JSON-об’єктом.");
    }
    if (Object.keys(raw.options).length > 512) throw new Error("Профіль містить забагато опцій.");
    const definitions = new Map(settingsDefinitions.map((item) => [item.path, item]));
    const options = {};
    for (const path of Object.keys(raw.options).sort()) {
      if (!ATTRIBUTE_PATH.test(path)) throw new Error(`Некоректний шлях опції: ${path}.`);
      const value = raw.options[path];
      assertJsonValue(value, path);
      options[path] = clone(validateKnownOption(definitions.get(path), value, settingsApi));
    }
    return { schemaVersion: 1, packages: packages.sort(), options };
  }

  function parseProfile(text, settingsDefinitions = [], settingsApi = root.NcmSettings) {
    let raw;
    try {
      raw = JSON.parse(text);
    } catch {
      throw new Error("Файл не містить коректний JSON.");
    }
    return normalizeProfile(raw, settingsDefinitions, settingsApi);
  }

  function serializeProfile(state, settingsDefinitions = [], settingsApi = root.NcmSettings) {
    return `${JSON.stringify(normalizeProfile(state, settingsDefinitions, settingsApi), null, 2)}\n`;
  }

  function applyPreset(preset, state) {
    const packages = new Set(state.packages || []);
    let addedPackages = 0;
    for (const attribute of preset.packages || []) {
      if (!packages.has(attribute)) addedPackages += 1;
      packages.add(attribute);
    }
    const options = clone(state.options || {});
    let changedOptions = 0;
    for (const [path, value] of Object.entries(preset.options || {})) {
      if (JSON.stringify(options[path]) !== JSON.stringify(value)) changedOptions += 1;
      options[path] = clone(value);
    }
    return {
      state: { schemaVersion: 1, packages: [...packages].sort(), options },
      addedPackages,
      changedOptions,
    };
  }

  function presetDelta(preset, state) {
    const result = applyPreset(preset, state);
    return result.addedPackages + result.changedOptions;
  }

  function normalizeCompatibilityReport(raw) {
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
      throw new Error("Звіт сумісності повинен бути JSON-об’єктом.");
    }
    if (raw.schemaVersion !== 1 || raw.readOnly !== true || !Array.isArray(raw.packages)) {
      throw new Error("Звіт сумісності має непідтримуваний формат.");
    }
    if (!INSPECTION_STATUSES.has(raw.status)) {
      throw new Error("Звіт сумісності містить невідомий загальний статус.");
    }
    const packages = [];
    const seen = new Set();
    for (const item of raw.packages) {
      if (!item || typeof item !== "object" || Array.isArray(item)) {
        throw new Error("Звіт сумісності містить некоректний запис пакунка.");
      }
      if (typeof item.attribute !== "string" || !ATTRIBUTE_PATH.test(item.attribute) || seen.has(item.attribute)) {
        throw new Error("Звіт сумісності містить некоректний або повторний атрибут.");
      }
      if (!COMPATIBILITY_STATUSES.has(item.status) || !COMPATIBILITY_REASONS.has(item.reason)) {
        throw new Error(`Невідомий статус сумісності: ${item.attribute}.`);
      }
      if (typeof item.unfree !== "boolean" || typeof item.license !== "string") {
        throw new Error(`Некоректні метадані сумісності: ${item.attribute}.`);
      }
      seen.add(item.attribute);
      packages.push({
        attribute: item.attribute,
        status: item.status,
        reason: item.reason,
        unfree: item.unfree,
        license: item.license,
      });
    }
    return {
      schemaVersion: 1,
      status: raw.status,
      readOnly: true,
      configurationMode: typeof raw.configurationMode === "string" ? raw.configurationMode : "missing",
      flakeTarget: typeof raw.flakeTarget === "string" ? raw.flakeTarget : null,
      system: typeof raw.system === "string" ? raw.system : "",
      packages,
      warnings: Array.isArray(raw.warnings) ? raw.warnings.filter((item) => typeof item === "string") : [],
      durationMs: Number.isInteger(raw.durationMs) && raw.durationMs >= 0 ? raw.durationMs : 0,
    };
  }

  function compatibilityIndex(report) {
    return new Map((report?.packages || []).map((item) => [item.attribute, item]));
  }

  function packageCompatibility(report, attribute) {
    return compatibilityIndex(report).get(attribute) || {
      attribute,
      status: "unknown",
      reason: "inspection-unavailable",
      unfree: false,
      license: "",
    };
  }

  function selectionCompatibilityIssues(attributes, report) {
    if (report?.status !== "passed") return [];
    const index = compatibilityIndex(report);
    return [...attributes]
      .map((attribute) => index.get(attribute))
      .filter((item) => item?.status === "incompatible");
  }

  function presetCompatibility(preset, report) {
    const incompatible = selectionCompatibilityIssues(preset?.packages || [], report);
    return {
      compatible: incompatible.length === 0,
      incompatible: incompatible.map((item) => item.attribute),
    };
  }

  const api = {
    applyPreset,
    normalizeCompatibilityReport,
    normalizeProfile,
    packageCompatibility,
    parseProfile,
    presetCompatibility,
    presetDelta,
    selectionCompatibilityIssues,
    serializeProfile,
  };
  root.NcmCatalog = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
}(typeof globalThis !== "undefined" ? globalThis : this));
