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

console.log("web settings helpers: ok");
