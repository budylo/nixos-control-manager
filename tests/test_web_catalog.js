"use strict";

const assert = require("node:assert/strict");
const settings = require(
  process.env.NCM_SETTINGS_JS || "../src/nix_control_manager/web/settings.js",
);
const catalog = require(
  process.env.NCM_CATALOG_JS || "../src/nix_control_manager/web/catalog.js",
);

const definitions = [
  { path: "services.demo.enable", name: "Demo", valueType: "boolean" },
  { path: "demo.count", name: "Count", valueType: "integer", minimum: 1, maximum: 10 },
];
const state = { schemaVersion: 1, packages: ["firefox"], options: { "services.demo.enable": false } };
const preset = {
  packages: ["firefox", "git"],
  options: { "services.demo.enable": true, "demo.count": 3 },
};
const applied = catalog.applyPreset(preset, state);
assert.deepEqual(applied.state, {
  schemaVersion: 1,
  packages: ["firefox", "git"],
  options: { "services.demo.enable": true, "demo.count": 3 },
});
assert.equal(applied.addedPackages, 1);
assert.equal(applied.changedOptions, 2);
assert.equal(catalog.presetDelta(preset, applied.state), 0);
assert.deepEqual(state, {
  schemaVersion: 1,
  packages: ["firefox"],
  options: { "services.demo.enable": false },
});

const normalized = catalog.parseProfile(
  '{"schemaVersion":1,"packages":["git","firefox","git"],"options":{"demo.count":3}}',
  definitions,
  settings,
);
assert.deepEqual(normalized, {
  schemaVersion: 1,
  packages: ["firefox", "git"],
  options: { "demo.count": 3 },
});
assert.equal(catalog.parseProfile(catalog.serializeProfile(normalized, definitions, settings), definitions, settings).packages.length, 2);
assert.throws(() => catalog.parseProfile("not json", definitions, settings), /коректний JSON/);
assert.throws(
  () => catalog.normalizeProfile({ schemaVersion: 2, packages: [], options: {} }, definitions, settings),
  /schemaVersion 1/,
);
assert.throws(
  () => catalog.normalizeProfile({ schemaVersion: 1, packages: ["bad;path"], options: {} }, definitions, settings),
  /Некоректний шлях пакунка/,
);
assert.throws(
  () => catalog.normalizeProfile({ schemaVersion: 1, packages: [], options: { "demo.count": 20 } }, definitions, settings),
  /максимум 10/,
);
assert.throws(
  () => catalog.normalizeProfile({ schemaVersion: 1, packages: [], options: {}, surprise: true }, definitions, settings),
  /Невідомі поля/,
);

const compatibility = catalog.normalizeCompatibilityReport({
  schemaVersion: 1,
  status: "passed",
  readOnly: true,
  configurationMode: "flake",
  flakeTarget: "desktop",
  system: "x86_64-linux",
  context: {
    desktopEnvironments: ["plasma"],
    configurationFlags: ["pipewire"],
    videoDrivers: ["amdgpu"],
    formFactor: "laptop",
    gpuVendors: ["amd"],
    kvmAvailable: true,
    runtimeHardwareInspected: true,
  },
  durationMs: 17,
  warnings: [],
  packages: [
    { attribute: "firefox", status: "compatible", reason: "available", unfree: false, license: "MPL-2.0" },
    { attribute: "vscode", status: "incompatible", reason: "evaluation-rejected", unfree: true, license: "unfree" },
    { attribute: "git", status: "compatible", reason: "available", unfree: false, license: "GPL-2.0" },
  ],
});
assert.equal(catalog.packageCompatibility(compatibility, "firefox").status, "compatible");
assert.equal(catalog.packageCompatibility(compatibility, "unknown-package").status, "unknown");
assert.deepEqual(
  catalog.selectionCompatibilityIssues(["firefox", "vscode"], compatibility).map((item) => item.attribute),
  ["vscode"],
);
assert.deepEqual(catalog.presetCompatibility({ packages: ["vscode"] }, compatibility), {
  compatible: false,
  incompatible: ["vscode"],
});
assert.deepEqual(catalog.selectionCompatibilityIssues(["vscode"], { status: "failed" }), []);
assert.deepEqual(compatibility.context.desktopEnvironments, ["plasma"]);
assert.equal(compatibility.context.formFactor, "laptop");
assert.equal(compatibility.context.kvmAvailable, true);
assert.throws(
  () => catalog.normalizeCompatibilityReport({ schemaVersion: 1, status: "passed", readOnly: true, packages: [
    { attribute: "bad;name", status: "unknown", reason: "inspection-unavailable", unfree: false, license: "" },
  ] }),
  /атрибут/,
);
assert.throws(
  () => catalog.normalizeCompatibilityReport({ schemaVersion: 1, status: "mystery", readOnly: true, packages: [] }),
  /загальний статус/,
);

const guidance = catalog.normalizeCatalogGuidance({
  schemaVersion: 1,
  alternativeGroups: [
    {
      id: "editors",
      title: "Редактори",
      description: "Оберіть редактор.",
      members: [
        { attribute: "vscode", desktopEnvironments: [] },
        { attribute: "firefox", desktopEnvironments: ["plasma"] },
      ],
    },
  ],
  companions: [
    { source: "firefox", target: "git", reason: "Пояснення супутнього пакета." },
  ],
  contextRecommendations: [
    {
      id: "plasma-tools",
      title: "Для Plasma",
      reason: "Пасує до Plasma.",
      match: { desktopEnvironments: ["plasma"] },
      packages: ["git"],
    },
    {
      id: "laptop-tools",
      title: "Для ноутбука",
      reason: "Виявлено ноутбук.",
      match: { formFactors: ["laptop"], kvmAvailable: true },
      packages: ["firefox"],
    },
  ],
});
assert.equal(catalog.bestAlternative("vscode", guidance, compatibility).attribute, "firefox");
assert.deepEqual(
  catalog.companionSuggestions(["firefox"], guidance, compatibility).map((item) => item.attribute),
  ["git"],
);
assert.deepEqual(
  catalog.contextSuggestions([], guidance, compatibility).map((item) => item.attribute),
  ["git", "firefox"],
);
const wslCompatibility = {
  ...compatibility,
  context: {
    ...compatibility.context,
    configurationFlags: ["wsl"],
  },
};
assert.deepEqual(
  catalog.contextSuggestions([], guidance, wslCompatibility).map((item) => item.attribute),
  ["git"],
);
assert.deepEqual(
  catalog.incompatibleAlternativeSuggestions(
    [{ attribute: "vscode", name: "VS Code" }],
    [],
    guidance,
    compatibility,
  ).map((item) => [item.source, item.attribute]),
  [["vscode", "firefox"]],
);
assert.throws(
  () => catalog.normalizeCatalogGuidance({ schemaVersion: 1, alternativeGroups: [], companions: [] }),
  /неповну структуру/,
);

console.log("web catalog helpers: ok");
