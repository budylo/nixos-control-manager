import unittest

from nix_control_manager.dependencies import (
    analyze_setting_dependencies,
    validate_managed_setting_dependencies,
)
from nix_control_manager.errors import ValidationError


class SettingDependencyTests(unittest.TestCase):
    def test_effective_parent_can_satisfy_or_violate_dependency(self) -> None:
        options = {"services.pipewire.pulse.enable": True}
        satisfied = analyze_setting_dependencies(
            options,
            effective_options={"services.pipewire.enable": True},
        )
        self.assertEqual(satisfied[0].status, "satisfied")
        self.assertEqual(satisfied[0].source, "effective")

        unsatisfied = analyze_setting_dependencies(
            options,
            effective_options={"services.pipewire.enable": False},
        )
        self.assertEqual(unsatisfied[0].status, "unsatisfied")

    def test_unknown_parent_is_reported_but_not_rejected(self) -> None:
        options = {"networking.networkmanager.wifi.backend": "iwd"}
        issues = analyze_setting_dependencies(options)
        self.assertEqual(issues[0].status, "unknown")
        self.assertEqual(issues[0].source, "unknown")
        validate_managed_setting_dependencies(options)

    def test_explicit_managed_contradiction_is_rejected(self) -> None:
        options = {
            "services.pipewire.enable": False,
            "services.pipewire.pulse.enable": True,
        }
        with self.assertRaisesRegex(ValidationError, "requires services.pipewire.enable"):
            validate_managed_setting_dependencies(options)

    def test_inactive_boolean_and_empty_list_do_not_trigger_rules(self) -> None:
        self.assertEqual(
            analyze_setting_dependencies(
                {"services.pipewire.pulse.enable": False},
                effective_options={"services.pipewire.enable": False},
            ),
            (),
        )
        self.assertEqual(
            analyze_setting_dependencies(
                {"networking.firewall.allowedTCPPorts": []},
                effective_options={"networking.firewall.enable": False},
            ),
            (),
        )

    def test_non_empty_ports_require_enabled_firewall(self) -> None:
        issues = analyze_setting_dependencies(
            {"networking.firewall.allowedTCPPorts": [22]},
            effective_options={"networking.firewall.enable": False},
        )
        self.assertEqual(issues[0].required_path, "networking.firewall.enable")
        self.assertEqual(issues[0].status, "unsatisfied")


if __name__ == "__main__":
    unittest.main()
