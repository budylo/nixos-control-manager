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

console.log("web catalog helpers: ok");
