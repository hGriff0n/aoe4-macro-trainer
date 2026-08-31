import re
import tempfile
import unittest
from pathlib import Path

from tools.build_orders.compiler import compile_directory


ROOT = Path(__file__).resolve().parents[1]
RESOURCES_PATH = ROOT / "assets" / "scar" / "build_orders" / "checks" / "resources.scar"


def function_body(source: str, name: str) -> str:
    match = re.search(
        rf"function {re.escape(name)}\([^)]*\)(.*?)(?=^function |\Z)",
        source,
        re.MULTILINE | re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"missing function {name}")
    return match.group(1)


class BuildOrderResourcesCompilerTests(unittest.TestCase):
    def test_resources_descriptors_preserve_yaml_order_and_render_collection_titles(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "resources.yaml"
            source.write_text(
                """civ: English
title: Resource threshold
steps:
  - resources:
      wood: 400
      gold: 200
""",
                encoding="utf-8",
            )
            checks = compile_directory(Path(temp)).build_orders[0].steps[0].checks

        self.assertEqual(
            [(check.title, check.optional, check.payload) for check in checks],
            [
                ("Collect at least 400 wood", False, {"resource": "wood", "count": 400}),
                ("Collect at least 200 gold", False, {"resource": "gold", "count": 200}),
            ],
        )


class BuildOrderResourcesContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = RESOURCES_PATH.read_text(encoding="utf-8") if RESOURCES_PATH.exists() else ""

    def test_resources_handler_module_exists_and_registers_lifecycle(self) -> None:
        self.assertTrue(RESOURCES_PATH.exists(), "resources handler must be added")
        self.assertIn('BuildOrder_RegisterHandler("resources", {', self.source)
        self.assertIn("activate = Resources_Activate", self.source)
        self.assertIn("deactivate = Resources_Deactivate", self.source)

    def test_activation_keeps_one_local_player_state_and_evaluates_it_immediately(self) -> None:
        activate = function_body(self.source, "Resources_Activate")
        self.assertIn("RESOURCES_STATE[check.id] = state", activate)
        self.assertIn("player = context.localPlayer", activate)
        self.assertIn("payload = check.payload", activate)
        self.assertIn("Resources_Poll(check.id)", activate)

    def test_multiple_descriptors_share_a_named_poll_rule_with_first_last_lifecycle(self) -> None:
        activate = function_body(self.source, "Resources_Activate")
        deactivate = function_body(self.source, "Resources_Deactivate")
        poll_all = function_body(self.source, "Resources_PollAll")

        self.assertNotIn("state.pollRule = function()", self.source)
        self.assertIn("RESOURCES_ACTIVE_COUNT = RESOURCES_ACTIVE_COUNT + 1", activate)
        self.assertIn("if RESOURCES_ACTIVE_COUNT == 0 then", activate)
        self.assertIn(
            "Rule_AddInterval(Resources_PollAll, RESOURCES_POLL_INTERVAL_SECONDS)",
            activate,
        )
        self.assertIn("RESOURCES_ACTIVE_COUNT = RESOURCES_ACTIVE_COUNT - 1", deactivate)
        self.assertIn("if RESOURCES_ACTIVE_COUNT == 0 then", deactivate)
        self.assertIn("Rule_Remove(Resources_PollAll)", deactivate)
        self.assertIn("for checkID, _ in pairs(RESOURCES_STATE) do", poll_all)
        self.assertIn("Resources_Poll(checkID)", poll_all)

    def test_poll_reads_only_the_stored_player_bank_for_the_descriptor_resource(self) -> None:
        poll = function_body(self.source, "Resources_Poll")
        self.assertIn("local state = RESOURCES_STATE[checkID]", poll)
        self.assertIn("Player_GetResource(state.player, state.resourceType)", poll)
        self.assertNotIn("Game_GetLocalPlayer", self.source)
        self.assertNotRegex(poll, r"Player_GetResource\(\s*context\.localPlayer")

    def test_poll_reports_true_above_threshold_and_false_after_spending(self) -> None:
        poll = function_body(self.source, "Resources_Poll")
        self.assertIn("amount >= state.payload.count", poll)
        self.assertIn("BuildOrder_SetCheckComplete(checkID, amount >= state.payload.count)", poll)

    def test_resource_names_map_to_official_resource_types(self) -> None:
        resource_type = function_body(self.source, "Resources_ResourceType")
        for resource, resource_type_name in (
            ("food", "RT_Food"),
            ("gold", "RT_Gold"),
            ("wood", "RT_Wood"),
            ("stone", "RT_Stone"),
        ):
            self.assertIn(f'resource == "{resource}"', resource_type)
            self.assertIn(f"return {resource_type_name}", resource_type)

    def test_deactivation_removes_its_state_and_is_idempotent(self) -> None:
        deactivate = function_body(self.source, "Resources_Deactivate")
        self.assertIn("if state == nil then", deactivate)
        self.assertIn("RESOURCES_STATE[check.id] = nil", deactivate)


if __name__ == "__main__":
    unittest.main()
