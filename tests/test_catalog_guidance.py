import unittest

from nix_control_manager.catalog import load_catalog, load_catalog_guidance


class CatalogGuidanceTests(unittest.TestCase):
    def test_guidance_references_known_packages_and_covers_each_signal_type(self) -> None:
        catalog = {item["attribute"] for item in load_catalog()}
        guidance = load_catalog_guidance()

        self.assertEqual(guidance["schemaVersion"], 1)
        self.assertGreaterEqual(len(guidance["alternativeGroups"]), 15)
        self.assertGreaterEqual(len(guidance["companions"]), 12)
        self.assertGreaterEqual(len(guidance["contextRecommendations"]), 8)
        referenced = {
            member["attribute"]
            for group in guidance["alternativeGroups"]
            for member in group["members"]
        }
        referenced.update(item["source"] for item in guidance["companions"])
        referenced.update(item["target"] for item in guidance["companions"])
        referenced.update(
            attribute
            for recommendation in guidance["contextRecommendations"]
            for attribute in recommendation["packages"]
        )
        self.assertTrue(referenced <= catalog)
        match_fields = {
            field
            for recommendation in guidance["contextRecommendations"]
            for field in recommendation["match"]
        }
        self.assertTrue(
            {"desktopEnvironments", "formFactors", "gpuVendors", "kvmAvailable"}
            <= match_fields
        )

    def test_guidance_loader_returns_an_independent_copy(self) -> None:
        first = load_catalog_guidance()
        first["alternativeGroups"].clear()

        self.assertGreater(len(load_catalog_guidance()["alternativeGroups"]), 0)


if __name__ == "__main__":
    unittest.main()
