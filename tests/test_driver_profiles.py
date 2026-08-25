import unittest

from nix_control_manager.catalog import (
    DRIVER_CATEGORIES,
    DRIVER_GUIDANCE,
    DRIVER_PLATFORMS,
    GPU_VENDORS,
    load_driver_profiles,
    load_settings_catalog,
    validate_setting_value,
)


class DriverProfileTests(unittest.TestCase):
    def test_profiles_are_typed_hardware_aware_and_explicit(self) -> None:
        document = load_driver_profiles()
        profiles = document["profiles"]
        settings = {definition["path"] for definition in load_settings_catalog()}

        self.assertEqual(document["schemaVersion"], 1)
        self.assertEqual(len(profiles), 6)
        self.assertEqual(len({profile["id"] for profile in profiles}), len(profiles))
        self.assertEqual({profile["category"] for profile in profiles}, DRIVER_CATEGORIES)
        self.assertTrue({profile["guidance"] for profile in profiles} <= DRIVER_GUIDANCE)
        self.assertTrue(
            {platform for profile in profiles for platform in profile["platforms"]}
            <= DRIVER_PLATFORMS
        )
        self.assertTrue(
            {vendor for profile in profiles for vendor in profile["vendors"]}
            <= GPU_VENDORS
        )
        for profile in profiles:
            self.assertTrue(set(profile["options"]) <= settings)
            self.assertTrue(profile["warnings"])
            for path, value in profile["options"].items():
                self.assertEqual(validate_setting_value(path, value), value)

        by_id = {profile["id"]: profile for profile in profiles}
        self.assertEqual(
            by_id["nvidia-proprietary"]["options"]["services.xserver.videoDrivers"],
            ["nvidia"],
        )
        self.assertFalse(by_id["nvidia-proprietary"]["options"]["hardware.nvidia.open"])
        self.assertTrue(by_id["nvidia-open"]["options"]["hardware.nvidia.open"])

    def test_loader_returns_a_nested_copy(self) -> None:
        first = load_driver_profiles()
        first["profiles"][0]["options"].clear()
        first["profiles"][0]["warnings"].append("mutated")

        second = load_driver_profiles()
        self.assertTrue(second["profiles"][0]["options"])
        self.assertNotIn("mutated", second["profiles"][0]["warnings"])


if __name__ == "__main__":
    unittest.main()
