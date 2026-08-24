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
  const FORM_FACTORS = new Set(["laptop", "desktop", "unknown"]);

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
    const rawContext = raw.context && typeof raw.context === "object" && !Array.isArray(raw.context)
      ? raw.context
      : {};
    const stringArray = (value) => Array.isArray(value)
      ? [...new Set(value.filter((item) => typeof item === "string" && item))]
      : [];
    return {
      schemaVersion: 1,
      status: raw.status,
      readOnly: true,
      configurationMode: typeof raw.configurationMode === "string" ? raw.configurationMode : "missing",
      flakeTarget: typeof raw.flakeTarget === "string" ? raw.flakeTarget : null,
      system: typeof raw.system === "string" ? raw.system : "",
      context: {
        desktopEnvironments: stringArray(rawContext.desktopEnvironments),
        configurationFlags: stringArray(rawContext.configurationFlags),
        videoDrivers: stringArray(rawContext.videoDrivers),
        formFactor: FORM_FACTORS.has(rawContext.formFactor) ? rawContext.formFactor : "unknown",
        gpuVendors: stringArray(rawContext.gpuVendors),
        kvmAvailable: rawContext.kvmAvailable === true,
        runtimeHardwareInspected: rawContext.runtimeHardwareInspected === true,
      },
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

  function normalizeCatalogGuidance(raw) {
    if (!raw || typeof raw !== "object" || Array.isArray(raw) || raw.schemaVersion !== 1) {
      throw new Error("Підказки каталогу мають непідтримуваний формат.");
    }
    if (!Array.isArray(raw.alternativeGroups)
        || !Array.isArray(raw.companions)
        || !Array.isArray(raw.contextRecommendations)) {
      throw new Error("Підказки каталогу мають неповну структуру.");
    }
    const attributes = new Set();
    const groups = raw.alternativeGroups.map((group) => {
      if (!group || typeof group.id !== "string" || typeof group.title !== "string"
          || typeof group.description !== "string" || !Array.isArray(group.members)
          || group.members.length < 2) {
        throw new Error("Некоректна група альтернатив у підказках каталогу.");
      }
      const members = group.members.map((member) => {
        if (!member || typeof member.attribute !== "string" || !ATTRIBUTE_PATH.test(member.attribute)
            || attributes.has(member.attribute) || !Array.isArray(member.desktopEnvironments)) {
          throw new Error("Некоректний або повторний пакет у групах альтернатив.");
        }
        attributes.add(member.attribute);
        return {
          attribute: member.attribute,
          desktopEnvironments: [...new Set(member.desktopEnvironments.filter((item) => typeof item === "string"))],
        };
      });
      return { id: group.id, title: group.title, description: group.description, members };
    });
    const companions = raw.companions.map((item) => {
      if (!item || typeof item.source !== "string" || typeof item.target !== "string"
          || !ATTRIBUTE_PATH.test(item.source) || !ATTRIBUTE_PATH.test(item.target)
          || item.source === item.target || typeof item.reason !== "string" || !item.reason) {
        throw new Error("Некоректний зв’язок супутніх пакетів.");
      }
      return { source: item.source, target: item.target, reason: item.reason };
    });
    const contextRecommendations = raw.contextRecommendations.map((item) => {
      if (!item || typeof item.id !== "string" || typeof item.title !== "string"
          || typeof item.reason !== "string" || !item.match || typeof item.match !== "object"
          || !Array.isArray(item.packages) || !item.packages.length
          || item.packages.some((attribute) => typeof attribute !== "string" || !ATTRIBUTE_PATH.test(attribute))) {
        throw new Error("Некоректна контекстна рекомендація каталогу.");
      }
      return clone(item);
    });
    return { schemaVersion: 1, alternativeGroups: groups, companions, contextRecommendations };
  }

  function contextMatches(match, context) {
    const arrayFields = ["desktopEnvironments", "gpuVendors", "configurationFlags"];
    for (const field of arrayFields) {
      if (Array.isArray(match[field])
          && !match[field].some((value) => (context[field] || []).includes(value))) return false;
    }
    if (Array.isArray(match.formFactors) && !match.formFactors.includes(context.formFactor)) return false;
    if (typeof match.kvmAvailable === "boolean" && context.kvmAvailable !== match.kvmAvailable) return false;
    return true;
  }

  function compatibleForSuggestion(attribute, report) {
    return report?.status !== "passed"
      || packageCompatibility(report, attribute).status === "compatible";
  }

  function bestAlternative(attribute, guidance, report) {
    const group = (guidance?.alternativeGroups || []).find(
      (candidate) => candidate.members.some((member) => member.attribute === attribute),
    );
    if (!group) return null;
    const desktops = report?.context?.desktopEnvironments || [];
    const ranked = group.members
      .filter((member) => member.attribute !== attribute && compatibleForSuggestion(member.attribute, report))
      .map((member, index) => ({
        ...member,
        index,
        fit: member.desktopEnvironments.some((desktop) => desktops.includes(desktop)) ? 2
          : member.desktopEnvironments.length === 0 ? 1 : 0,
      }))
      .sort((left, right) => right.fit - left.fit || left.index - right.index);
    if (!ranked.length) return null;
    return {
      attribute: ranked[0].attribute,
      groupId: group.id,
      title: group.title,
      reason: ranked[0].fit === 2
        ? `Сумісна альтернатива, що пасує до ${desktops.join(" / ")}.`
        : group.description,
    };
  }

  function companionSuggestions(selected, guidance, report, limit = 3) {
    const chosen = new Set(selected || []);
    const seen = new Set();
    const suggestions = [];
    for (const rule of guidance?.companions || []) {
      if (!chosen.has(rule.source) || chosen.has(rule.target) || seen.has(rule.target)
          || !compatibleForSuggestion(rule.target, report)) continue;
      seen.add(rule.target);
      suggestions.push({
        kind: "companion",
        attribute: rule.target,
        source: rule.source,
        title: "Добре працює разом",
        reason: rule.reason,
      });
      if (suggestions.length >= limit) break;
    }
    return suggestions;
  }

  function contextSuggestions(selected, guidance, report, limit = 3) {
    const chosen = new Set(selected || []);
    const context = report?.context || {};
    const seen = new Set();
    const suggestions = [];
    const isWsl = (context.configurationFlags || []).includes("wsl");
    for (const recommendation of guidance?.contextRecommendations || []) {
      const hardwareOnly = recommendation.match.formFactors
        || recommendation.match.gpuVendors
        || typeof recommendation.match.kvmAvailable === "boolean";
      const explicitlyForWsl = (recommendation.match.configurationFlags || []).includes("wsl");
      if (isWsl && hardwareOnly && !explicitlyForWsl) continue;
      if (!contextMatches(recommendation.match, context)) continue;
      const attribute = recommendation.packages.find(
        (candidate) => !chosen.has(candidate) && !seen.has(candidate)
          && compatibleForSuggestion(candidate, report),
      );
      if (!attribute) continue;
      seen.add(attribute);
      suggestions.push({
        kind: "context",
        attribute,
        contextId: recommendation.id,
        title: recommendation.title,
        reason: recommendation.reason,
      });
      if (suggestions.length >= limit) break;
    }
    return suggestions;
  }

  function incompatibleAlternativeSuggestions(catalog, selected, guidance, report, limit = 2) {
    if (report?.status !== "passed") return [];
    const chosen = new Set(selected || []);
    const seenTargets = new Set();
    const suggestions = [];
    for (const app of catalog || []) {
      if (packageCompatibility(report, app.attribute).status !== "incompatible") continue;
      const alternative = bestAlternative(app.attribute, guidance, report);
      if (!alternative || chosen.has(alternative.attribute) || seenTargets.has(alternative.attribute)) continue;
      seenTargets.add(alternative.attribute);
      suggestions.push({
        kind: "alternative",
        attribute: alternative.attribute,
        source: app.attribute,
        title: `Замість ${app.name || app.attribute}`,
        reason: alternative.reason,
      });
      if (suggestions.length >= limit) break;
    }
    return suggestions;
  }

  const api = {
    applyPreset,
    bestAlternative,
    companionSuggestions,
    contextSuggestions,
    incompatibleAlternativeSuggestions,
    normalizeCompatibilityReport,
    normalizeCatalogGuidance,
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
