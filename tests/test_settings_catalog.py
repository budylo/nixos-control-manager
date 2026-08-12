import unittest

from nix_control_manager.catalog import (
    SETTING_VALUE_TYPES,
    load_settings_catalog,
    setting_definition,
    validate_setting_value,
)
from nix_control_manager.errors import ValidationError


class SettingsCatalogTests(unittest.TestCase):
    def test_catalog_is_unique_typed_and_covers_first_categories(self) -> None:
        catalog = load_settings_catalog()
        paths = [definition["path"] for definition in catalog]

        self.assertEqual(len(paths), len(set(paths)))
        self.assertGreaterEqual(len(catalog), 30)
        self.assertTrue({item["valueType"] for item in catalog} <= SETTING_VALUE_TYPES)
        self.assertTrue(
            {
                "Мова і час",
                "Робочий стіл",
                "Звук",
                "Мережа",
                "Служби",
                "Обслуговування",
                "Віртуалізація",
                "Система",
            }
            <= {item["category"] for item in catalog}
        )

    def test_boolean_enum_integer_and_list_validation(self) -> None:
        self.assertTrue(validate_setting_value("services.pipewire.enable", True))
        self.assertEqual(
            validate_setting_value(
                "networking.networkmanager.wifi.backend", "wpa_supplicant"
            ),
            "wpa_supplicant",
        )
        self.assertEqual(validate_setting_value("boot.loader.timeout", 10), 10)
        self.assertEqual(validate_setting_value("zramSwap.memoryPercent", 75), 75)
        self.assertEqual(
            validate_setting_value(
                "networking.firewall.allowedTCPPorts", [443, 80, 443]
            ),
            [443, 80],
        )
        self.assertEqual(
            validate_setting_value("networking.firewall.allowedUDPPorts", [53, 53]),
            [53],
        )

    def test_invalid_known_setting_values_fail_closed(self) -> None:
        cases = (
            ("services.pipewire.enable", "yes", "boolean"),
            ("networking.networkmanager.wifi.backend", "unknown", "one of"),
            ("boot.loader.timeout", 121, "at most"),
            ("networking.firewall.allowedTCPPorts", [65536], "at most"),
            ("zramSwap.memoryPercent", 0, "at least 1"),
            ("i18n.supportedLocales", [""], "non-empty string"),
            ("time.timeZone", "Europe/Kyiv invalid", "містити пробілів"),
        )
        for path, value, message in cases:
            with self.subTest(path=path, value=value):
                with self.assertRaisesRegex(ValidationError, message):
                    validate_setting_value(path, value)

    def test_unknown_option_is_not_claimed_by_catalog(self) -> None:
        self.assertIsNone(setting_definition("custom.module.option"))
        value = {"kept": [1, True]}
        self.assertIs(validate_setting_value("custom.module.option", value), value)

    def test_dependency_rules_reference_typed_catalog_settings(self) -> None:
        catalog = load_settings_catalog()
        rules = [
            (definition["path"], rule)
            for definition in catalog
            for rule in definition.get("requires", [])
        ]
        self.assertEqual(len(rules), 7)
        self.assertEqual(
            {(owner, rule["path"]) for owner, rule in rules},
            {
                ("services.pipewire.pulse.enable", "services.pipewire.enable"),
                (
                    "networking.networkmanager.wifi.backend",
                    "networking.networkmanager.enable",
                ),
                (
                    "networking.firewall.allowedTCPPorts",
                    "networking.firewall.enable",
                ),
                (
                    "networking.firewall.allowedUDPPorts",
                    "networking.firewall.enable",
                ),
                ("hardware.bluetooth.powerOnBoot", "hardware.bluetooth.enable"),
                ("services.blueman.enable", "hardware.bluetooth.enable"),
                ("zramSwap.memoryPercent", "zramSwap.enable"),
            },
        )
        self.assertTrue(all(rule["requiredValue"] is True for _, rule in rules))


if __name__ == "__main__":
    unittest.main()
