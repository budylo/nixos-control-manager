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

  const api = { normalizeOptions, optionChangeCount, parseEditorValue, formatEditorValue };
  root.NcmSettings = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
}(typeof globalThis !== "undefined" ? globalThis : this));
