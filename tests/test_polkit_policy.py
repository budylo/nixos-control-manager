from pathlib import Path
import unittest
from xml.etree import ElementTree

from nix_control_manager.helper_service import (
    APPLY_ACTION_ID,
    HOME_MANAGER_APPLY_ACTION_ID,
    HOME_MANAGER_RECOVER_ACTION_ID,
    PREVIEW_ACTIVATION_ACTION_ID,
    RECOVER_TEST_ACTIVATION_ACTION_ID,
    RECOVER_ACTION_ID,
    TEST_ACTIVATION_ACTION_ID,
)


class PolkitPolicyTests(unittest.TestCase):
    def test_policy_actions_default_to_explicit_admin_authentication(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        policy_path = (
            repository
            / "packaging"
            / "polkit"
            / "org.nixos.nix-control-manager.policy"
        )
        root = ElementTree.parse(policy_path).getroot()
        actions = {action.attrib["id"]: action for action in root.findall("action")}

        self.assertEqual(
            set(actions),
            {
                APPLY_ACTION_ID,
                HOME_MANAGER_APPLY_ACTION_ID,
                HOME_MANAGER_RECOVER_ACTION_ID,
                PREVIEW_ACTIVATION_ACTION_ID,
                RECOVER_ACTION_ID,
                TEST_ACTIVATION_ACTION_ID,
                RECOVER_TEST_ACTIVATION_ACTION_ID,
            },
        )
        for action in actions.values():
            defaults = action.find("defaults")
            self.assertIsNotNone(defaults)
            self.assertEqual(defaults.findtext("allow_any"), "no")
            self.assertEqual(defaults.findtext("allow_inactive"), "no")
            self.assertEqual(defaults.findtext("allow_active"), "auth_admin")


if __name__ == "__main__":
    unittest.main()
