(function (root) {
  "use strict";

  function normalizeOptions(options) {
    return Object.fromEntries(
      Object.entries(options || {}).sort(([left], [right]) => left.localeCompare(right)),
    );
  }

  function optionChangeCount(saved, current) {
    const before = normalizeOptions(saved);
    const after = normalizeOptions(current);
    const paths = new Set([...Object.keys(before), ...Object.keys(after)]);
    let count = 0;
    for (const path of paths) {
      if (JSON.stringify(before[path]) !== JSON.stringify(after[path])) count += 1;
    }
    return count;
  }

  function unique(items) {
    return items.filter((item, index) => items.indexOf(item) === index);
  }

  function parseInteger(raw, definition, label) {
    const text = String(raw).trim();
    if (!/^-?\d+$/.test(text)) throw new Error(`${label}: введіть ціле число.`);
    const value = Number(text);
    if (!Number.isSafeInteger(value)) throw new Error(`${label}: число завелике.`);
    if (definition.minimum !== undefined && value < definition.minimum) {
      throw new Error(`${label}: мінімум ${definition.minimum}.`);
    }
    if (definition.maximum !== undefined && value > definition.maximum) {
      throw new Error(`${label}: максимум ${definition.maximum}.`);
    }
    return value;
  }

  function parseEditorValue(definition, raw) {
    const label = definition.name || definition.path;
    switch (definition.valueType) {
      case "boolean":
        if (raw === true || raw === "true") return true;
        if (raw === false || raw === "false") return false;
        throw new Error(`${label}: виберіть увімкнено або вимкнено.`);
      case "enum": {
        const allowed = new Set((definition.choices || []).map((choice) => choice.value));
        if (!allowed.has(raw)) throw new Error(`${label}: недозволене значення.`);
        return raw;
      }
      case "string": {
        const value = String(raw).trim();
        if (!value) throw new Error(`${label}: значення не може бути порожнім.`);
        if (definition.pattern && !(new RegExp(definition.pattern)).test(value)) {
          throw new Error(`${label}: ${definition.patternMessage}.`);
        }
        return value;
      }
      case "integer":
        return parseInteger(raw, definition, label);
      case "string-list": {
        const values = unique(String(raw).split(/[\n,]/).map((item) => item.trim()).filter(Boolean));
        if (values.some((item) => item.length > 256)) {
          throw new Error(`${label}: один з елементів задовгий.`);
        }
        return values;
      }
      case "integer-list": {
        const chunks = String(raw).split(/[\s,]+/).map((item) => item.trim()).filter(Boolean);
        return unique(chunks.map((item) => parseInteger(item, definition, label)));
      }
      default:
        throw new Error(`${label}: редактор не підтримує цей тип.`);
    }
  }

  function formatEditorValue(definition, value) {
    if (definition.valueType === "boolean") return String(value);
    if (definition.valueType === "string-list" || definition.valueType === "integer-list") {
      return Array.isArray(value) ? value.join(", ") : "";
    }
    return value === null || value === undefined ? "" : String(value);
  }

  function dependencyIssues(definitions, options, effectiveSettings) {
    const byPath = new Map((definitions || []).map((definition) => [definition.path, definition]));
    const effective = new Map(
      (effectiveSettings || [])
        .filter((setting) => setting.available)
        .map((setting) => [setting.path, setting.value]),
    );
    const issues = [];
    for (const definition of definitions || []) {
      if (!Object.hasOwn(options || {}, definition.path)) continue;
      const childValue = options[definition.path];
      for (const rule of definition.requires || []) {
        const active = rule.when === "always"
          || (rule.when === "true" && childValue === true)
          || (rule.when === "non-empty" && Array.isArray(childValue) && childValue.length > 0);
        if (!active) continue;
        let value;
        let source;
        if (Object.hasOwn(options, rule.path)) {
          value = options[rule.path];
          source = "managed";
        } else if (effective.has(rule.path)) {
          value = effective.get(rule.path);
          source = "effective";
        } else {
          source = "unknown";
        }
        const status = source === "unknown"
          ? "unknown"
          : (JSON.stringify(value) === JSON.stringify(rule.requiredValue)
            ? "satisfied"
            : "unsatisfied");
        issues.push({
          path: definition.path,
          name: definition.name,
          requiredPath: rule.path,
          requiredName: byPath.get(rule.path)?.name || rule.path,
          requiredValue: rule.requiredValue,
          message: rule.message,
          source,
          status,
        });
      }
    }
    return issues;
  }

  function serviceDefinitions(definitions) {
    return (definitions || []).filter(
      (definition) => definition.valueType === "boolean" && definition.service,
    );
  }

  function serviceTargetStatus(definition, context) {
    const target = (context?.configurationFlags || []).includes("wsl") ? "wsl" : "nixos";
    const platforms = definition?.service?.platforms || [];
    return {
      target,
      supported: platforms.includes(target),
    };
  }

  function serviceSummary(definitions, options, effectiveSettings, context) {
    const services = serviceDefinitions(definitions);
    const effective = new Map(
      (effectiveSettings || []).map((setting) => [setting.path, setting]),
    );
    let managed = 0;
    let enabled = 0;
    let pending = 0;
    let attention = 0;
    let notRecommended = 0;
    for (const definition of services) {
      const actual = effective.get(definition.path);
      const isManaged = Object.hasOwn(options || {}, definition.path);
      if (isManaged) managed += 1;
      if (actual?.available && actual.value === true) enabled += 1;
      if (
        isManaged
        && actual?.available
        && JSON.stringify(options[definition.path]) !== JSON.stringify(actual.value)
      ) pending += 1;
      if (["conflict", "evaluation-failed", "option-missing"].includes(actual?.assessment)) {
        attention += 1;
      }
      if (!serviceTargetStatus(definition, context).supported) notRecommended += 1;
    }
    return { total: services.length, managed, enabled, pending, attention, notRecommended };
  }

  function normalizeDriverProfiles(document, definitions) {
    if (!document || typeof document !== "object" || Array.isArray(document)) {
      throw new Error("Каталог драйверів має бути об’єктом.");
    }
    if (document.schemaVersion !== 1 || !Array.isArray(document.profiles)) {
      throw new Error("Непідтримувана версія каталогу драйверів.");
    }
    const known = new Map((definitions || []).map((definition) => [definition.path, definition]));
    const ids = new Set();
    const categories = new Set(["firmware", "graphics"]);
    const guidance = new Set(["manual", "recommended"]);
    const risks = new Set(["low", "medium", "high"]);
    const vendors = new Set(["amd", "intel", "microsoft", "nvidia", "virtio", "other"]);
    const factors = new Set(["laptop", "desktop", "unknown"]);
    const flags = new Set(["bluetooth", "libvirtd", "pipewire", "steam", "wsl"]);
    const expected = [
      "category", "configurationFlags", "description", "formFactors", "guidance",
      "id", "name", "options", "platforms", "risk", "vendors", "warnings",
    ];
    const stringArray = (value, allowed, label, allowEmpty = true) => {
      if (
        !Array.isArray(value)
        || (!allowEmpty && value.length === 0)
        || value.some((item) => typeof item !== "string" || !item || !allowed.has(item))
        || new Set(value).size !== value.length
      ) throw new Error(`${label}: некоректний список.`);
      return [...value];
    };
    const profiles = document.profiles.map((raw, index) => {
      if (
        !raw
        || typeof raw !== "object"
        || Array.isArray(raw)
        || JSON.stringify(Object.keys(raw).sort()) !== JSON.stringify(expected)
      ) throw new Error(`Профіль драйвера ${index}: некоректна схема.`);
      if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(raw.id) || ids.has(raw.id)) {
        throw new Error(`Профіль драйвера ${index}: некоректний або повторний id.`);
      }
      ids.add(raw.id);
      if (
        typeof raw.name !== "string" || !raw.name.trim()
        || typeof raw.description !== "string" || !raw.description.trim()
        || !categories.has(raw.category)
        || !guidance.has(raw.guidance)
        || !risks.has(raw.risk)
      ) throw new Error(`${raw.id}: некоректні метадані.`);
      if (!raw.options || typeof raw.options !== "object" || Array.isArray(raw.options)) {
        throw new Error(`${raw.id}: опції мають бути об’єктом.`);
      }
      const normalizedOptions = {};
      for (const [path, value] of Object.entries(raw.options)) {
        const definition = known.get(path);
        if (!definition) throw new Error(`${raw.id}: невідома опція ${path}.`);
        const normalized = parseEditorValue(definition, formatEditorValue(definition, value));
        if (JSON.stringify(normalized) !== JSON.stringify(value)) {
          throw new Error(`${raw.id}: некоректне значення ${path}.`);
        }
        normalizedOptions[path] = normalized;
      }
      if (Object.keys(normalizedOptions).length === 0) {
        throw new Error(`${raw.id}: профіль не містить опцій.`);
      }
      if (!Array.isArray(raw.warnings) || raw.warnings.length === 0
        || raw.warnings.some((warning) => typeof warning !== "string" || !warning.trim())) {
        throw new Error(`${raw.id}: потрібне хоча б одне застереження.`);
      }
      return {
        ...raw,
        vendors: stringArray(raw.vendors, vendors, `${raw.id}.vendors`),
        platforms: stringArray(raw.platforms, new Set(["nixos"]), `${raw.id}.platforms`, false),
        formFactors: stringArray(raw.formFactors, factors, `${raw.id}.formFactors`),
        configurationFlags: stringArray(
          raw.configurationFlags, flags, `${raw.id}.configurationFlags`,
        ),
        options: normalizedOptions,
        warnings: [...raw.warnings],
      };
    });
    return { schemaVersion: 1, profiles };
  }

  function driverTargetFacts(context) {
    const flags = Array.isArray(context?.configurationFlags)
      ? context.configurationFlags : [];
    const vendors = Array.isArray(context?.gpuVendors) ? unique(context.gpuVendors) : [];
    return {
      target: flags.includes("wsl") ? "wsl" : "nixos",
      vendors,
      configuredDrivers: Array.isArray(context?.videoDrivers)
        ? unique(context.videoDrivers) : [],
      formFactor: context?.formFactor || "unknown",
      hardwareInspected: context?.runtimeHardwareInspected === true,
      hybrid: vendors.length > 1,
      configurationFlags: flags,
    };
  }

  function driverProfileAssessment(profile, context) {
    const facts = driverTargetFacts(context);
    if (facts.target !== "nixos" || !(profile?.platforms || []).includes("nixos")) {
      return { status: "unsupported", reason: "wsl", facts };
    }
    const requiredVendors = profile?.vendors || [];
    if (requiredVendors.length) {
      if (!facts.hardwareInspected || facts.vendors.length === 0) {
        return { status: "unknown", reason: "hardware-unknown", facts };
      }
      if (!requiredVendors.some((vendor) => facts.vendors.includes(vendor))) {
        return { status: "not-applicable", reason: "vendor-mismatch", facts };
      }
    }
    const requiredFactors = profile?.formFactors || [];
    if (requiredFactors.length && !requiredFactors.includes(facts.formFactor)) {
      return {
        status: facts.formFactor === "unknown" ? "unknown" : "not-applicable",
        reason: facts.formFactor === "unknown" ? "hardware-unknown" : "form-factor-mismatch",
        facts,
      };
    }
    const requiredFlags = profile?.configurationFlags || [];
    if (requiredFlags.some((flag) => !facts.configurationFlags.includes(flag))) {
      return { status: "not-applicable", reason: "feature-mismatch", facts };
    }
    if (facts.hybrid && profile?.category === "graphics") {
      return { status: "review", reason: "hybrid-gpu", facts };
    }
    if (profile?.guidance === "manual") {
      return { status: "review", reason: "manual-review", facts };
    }
    return { status: "recommended", reason: "hardware-match", facts };
  }

  function driverProfileDelta(profile, options) {
    return Object.entries(profile?.options || {}).filter(
      ([path, value]) => JSON.stringify((options || {})[path]) !== JSON.stringify(value),
    ).length;
  }

  function applyDriverProfile(profile, state) {
    const current = state || { schemaVersion: 1, packages: [], options: {} };
    const options = normalizeOptions({ ...(current.options || {}), ...(profile?.options || {}) });
    return {
      state: {
        schemaVersion: current.schemaVersion || 1,
        packages: [...(current.packages || [])],
        options,
      },
      changedOptions: driverProfileDelta(profile, current.options || {}),
    };
  }

  function driverSummary(profiles, options, context) {
    const counts = { total: 0, recommended: 0, review: 0, configured: 0 };
    for (const profile of profiles || []) {
      counts.total += 1;
      const status = driverProfileAssessment(profile, context).status;
      if (status === "recommended") counts.recommended += 1;
      if (status === "review") counts.review += 1;
      if (driverProfileDelta(profile, options) === 0) counts.configured += 1;
    }
    return counts;
  }

  const api = {
    normalizeOptions,
    optionChangeCount,
    parseEditorValue,
    formatEditorValue,
    dependencyIssues,
    serviceDefinitions,
    serviceTargetStatus,
    serviceSummary,
    normalizeDriverProfiles,
    driverTargetFacts,
    driverProfileAssessment,
    driverProfileDelta,
    applyDriverProfile,
    driverSummary,
  };
  root.NcmSettings = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
}(typeof globalThis !== "undefined" ? globalThis : this));
