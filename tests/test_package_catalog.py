import unittest

from nix_control_manager.catalog import PACKAGE_SCOPES, load_catalog, load_presets


class PackageCatalogTests(unittest.TestCase):
    def test_catalog_is_large_unique_searchable_and_scoped(self) -> None:
        catalog = load_catalog()
        attributes = [item["attribute"] for item in catalog]

        self.assertGreaterEqual(len(catalog), 130)
        self.assertEqual(len(attributes), len(set(attributes)))
        self.assertGreaterEqual(len({item["category"] for item in catalog}), 8)
        self.assertGreaterEqual(sum(item["featured"] for item in catalog), 30)
        self.assertTrue(all(item["tags"] for item in catalog))
        self.assertTrue(all(set(item["scopes"]) <= PACKAGE_SCOPES for item in catalog))
        self.assertIn("home-manager", {scope for item in catalog for scope in item["scopes"]})
        self.assertIn("system", {scope for item in catalog for scope in item["scopes"]})

    def test_catalog_results_are_independent_copies(self) -> None:
        first = load_catalog()
        first[0]["tags"].append("mutation")
        self.assertNotIn("mutation", load_catalog()[0]["tags"])

    def test_presets_reference_catalog_and_explicitly_safe_options(self) -> None:
        catalog = {item["attribute"]: item for item in load_catalog()}
        presets = load_presets()
        ids = [item["id"] for item in presets]

        self.assertGreaterEqual(len(presets), 8)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(item["packages"] for item in presets))
        for preset in presets:
            self.assertTrue(set(preset["packages"]) <= set(catalog))
            self.assertTrue(
                all("system" in catalog[attribute]["scopes"] for attribute in preset["packages"])
            )
        gaming = next(item for item in presets if item["id"] == "gaming-ready")
        self.assertTrue(gaming["options"]["programs.steam.enable"])
        laptop = next(item for item in presets if item["id"] == "laptop-care")
        self.assertTrue(laptop["options"]["zramSwap.enable"])
        self.assertEqual(laptop["options"]["zramSwap.memoryPercent"], 25)


if __name__ == "__main__":
    unittest.main()
