"use strict";

const assert = require("node:assert/strict");
const settings = require(
  process.env.NCM_SETTINGS_JS || "../src/nix_control_manager/web/settings.js",
);

assert.deepEqual(
  settings.normalizeOptions({ "z.option": true, "a.option": 1 }),
  { "a.option": 1, "z.option": true },
);
assert.equal(
  settings.optionChangeCount(
    { "a.option": true, "b.option": [1] },
    { "a.option": false, "c.option": [1] },
  ),
  3,
);
assert.equal(
  settings.parseEditorValue({ name: "PipeWire", valueType: "boolean" }, "true"),
  true,
);
assert.equal(
  settings.parseEditorValue(
    { name: "Timeout", valueType: "integer", minimum: 0, maximum: 120 },
    "15",
  ),
  15,
);
assert.deepEqual(
  settings.parseEditorValue(
    { name: "Ports", valueType: "integer-list", minimum: 0, maximum: 65535 },
    "443, 80 443",
  ),
  [443, 80],
);
assert.deepEqual(
  settings.parseEditorValue({ name: "Locales", valueType: "string-list" }, "uk_UA, en_US\nuk_UA"),
  ["uk_UA", "en_US"],
);
assert.throws(
  () => settings.parseEditorValue(
    { name: "Ports", valueType: "integer-list", minimum: 0, maximum: 65535 },
    "70000",
  ),
  /максимум 65535/,
);
assert.throws(
  () => settings.parseEditorValue(
    { name: "Backend", valueType: "enum", choices: [{ value: "iwd" }] },
    "other",
  ),
  /недозволене/,
);
assert.throws(
  () => settings.parseEditorValue(
    {
      name: "Timezone",
      valueType: "string",
      pattern: "^[^\\s]+$",
      patternMessage: "не може містити пробілів",
    },
    "Europe/Kyiv invalid",
  ),
  /не може містити пробілів/,
);

const dependencyDefinitions = [
  { path: "parent.enable", name: "Parent" },
  {
    path: "child.enable",
    name: "Child",
    requires: [{
      path: "parent.enable",
      requiredValue: true,
      when: "true",
      message: "Parent is required.",
    }],
  },
];
assert.deepEqual(
  settings.dependencyIssues(
    dependencyDefinitions,
    { "child.enable": true },
    [{ path: "parent.enable", available: true, value: false }],
  ),
  [{
    path: "child.enable",
    name: "Child",
    requiredPath: "parent.enable",
    requiredName: "Parent",
    requiredValue: true,
    message: "Parent is required.",
    source: "effective",
    status: "unsatisfied",
  }],
);
assert.equal(
  settings.dependencyIssues(
    dependencyDefinitions,
    { "child.enable": true, "parent.enable": true },
    [],
  )[0].status,
  "satisfied",
);
assert.deepEqual(
  settings.dependencyIssues(
    dependencyDefinitions,
    { "child.enable": false },
    [],
  ),
  [],
);

const serviceDefinitions = [
  {
    path: "services.openssh.enable",
    valueType: "boolean",
    service: { platforms: ["nixos", "wsl"] },
  },
  {
    path: "services.fwupd.enable",
    valueType: "boolean",
    service: { platforms: ["nixos"] },
  },
  { path: "services.pipewire.pulse.enable", valueType: "boolean" },
];
assert.deepEqual(
  settings.serviceDefinitions(serviceDefinitions).map((definition) => definition.path),
  ["services.openssh.enable", "services.fwupd.enable"],
);
assert.deepEqual(
  settings.serviceTargetStatus(serviceDefinitions[1], { configurationFlags: ["wsl"] }),
  { target: "wsl", supported: false },
);
assert.deepEqual(
  settings.serviceSummary(
    serviceDefinitions,
    { "services.openssh.enable": false },
    [
      { path: "services.openssh.enable", available: true, value: true },
      { path: "services.fwupd.enable", available: false, assessment: "option-missing" },
    ],
    { configurationFlags: ["wsl"] },
  ),
  { total: 2, managed: 1, enabled: 1, pending: 1, attention: 1, notRecommended: 1 },
);

const driverDefinitions = [
  { path: "hardware.graphics.enable", name: "Graphics", valueType: "boolean" },
  { path: "services.xserver.videoDrivers", name: "Drivers", valueType: "string-list" },
];
const driverDocument = settings.normalizeDriverProfiles({
  schemaVersion: 1,
  profiles: [{
    id: "amd-graphics",
    name: "AMD",
    description: "AMD graphics profile",
    category: "graphics",
    risk: "medium",
    guidance: "recommended",
    vendors: ["amd"],
    platforms: ["nixos"],
    formFactors: [],
    configurationFlags: [],
    options: {
      "hardware.graphics.enable": true,
      "services.xserver.videoDrivers": ["amdgpu"],
    },
    warnings: ["Review old GPUs."],
  }],
}, driverDefinitions);
const amdProfile = driverDocument.profiles[0];
const amdContext = {
  configurationFlags: [],
  gpuVendors: ["amd"],
  videoDrivers: [],
  formFactor: "desktop",
  runtimeHardwareInspected: true,
};
assert.equal(settings.driverProfileAssessment(amdProfile, amdContext).status, "recommended");
assert.equal(
  settings.driverProfileAssessment(
    amdProfile,
    { ...amdContext, gpuVendors: ["amd", "intel"] },
  ).status,
  "review",
);
assert.equal(
  settings.driverProfileAssessment(
    amdProfile,
    { ...amdContext, configurationFlags: ["wsl"] },
  ).status,
  "unsupported",
);
assert.equal(
  settings.driverProfileAssessment(
    amdProfile,
    { ...amdContext, gpuVendors: ["nvidia"] },
  ).status,
  "not-applicable",
);
assert.equal(settings.driverProfileDelta(amdProfile, {}), 2);
const appliedDriver = settings.applyDriverProfile(
  amdProfile,
  { schemaVersion: 1, packages: ["git"], options: { "custom.option": true } },
);
assert.deepEqual(appliedDriver, {
  state: {
    schemaVersion: 1,
    packages: ["git"],
    options: {
      "custom.option": true,
      "hardware.graphics.enable": true,
      "services.xserver.videoDrivers": ["amdgpu"],
    },
  },
  changedOptions: 2,
});
assert.deepEqual(
  settings.driverSummary([amdProfile], appliedDriver.state.options, amdContext),
  { total: 1, recommended: 1, review: 0, configured: 1 },
);
assert.throws(
  () => settings.normalizeDriverProfiles(
    { schemaVersion: 1, profiles: [{ ...amdProfile, options: { "unknown.option": true } }] },
    driverDefinitions,
  ),
  /невідома опція/,
);

console.log("web settings helpers: ok");
