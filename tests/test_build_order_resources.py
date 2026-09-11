import re
import tempfile
import unittest
from pathlib import Path

from tools.build_orders.compiler import compile_directory
from tests.scar_runtime import ScarRuntime


ROOT = Path(__file__).resolve().parents[1]
RESOURCES_PATH = ROOT / "assets" / "scar" / "build_orders" / "checks" / "resources.scar"
LOCALIZATION_PATH = ROOT / "assets" / "scar" / "build_orders" / "localization.scar"
LOC = {
    "gold": "$dfb5645698a84afb91cf7a2dfb0f4a4e:149",
    "collect": "$dfb5645698a84afb91cf7a2dfb0f4a4e:155",
}


def formatter_runtime(source: str) -> ScarRuntime:
    registration_stub = "function BuildOrder_RegisterHandler(kind, handler)\nend"
    localization = LOCALIZATION_PATH.read_text(encoding="utf-8")
    runtime = ScarRuntime(registration_stub + "\n" + localization + "\n" + source)
    runtime.globals["Loc_FormatText"] = lambda key, *values: (key, *values)
    return runtime


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
    def test_resources_descriptors_preserve_yaml_order_and_semantic_payloads(self) -> None:
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
            [(check.kind, check.optional, check.payload) for check in checks],
            [
                ("resources", False, {"resource": "wood", "count": 400}),
                ("resources", False, {"resource": "gold", "count": 200}),
            ],
        )
        self.assertFalse(hasattr(checks[0], "title"))


class BuildOrderResourcesContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = RESOURCES_PATH.read_text(encoding="utf-8") if RESOURCES_PATH.exists() else ""

    def test_resources_handler_module_exists_and_registers_lifecycle(self) -> None:
        self.assertTrue(RESOURCES_PATH.exists(), "resources handler must be added")
        self.assertIn('BuildOrder_RegisterHandler("resources", {', self.source)
        self.assertIn("activate = Resources_Activate", self.source)
        self.assertIn("deactivate = Resources_Deactivate", self.source)
        self.assertIn("formatTitle = Resources_FormatTitle", self.source)

    def test_formatter_localizes_the_threshold_and_resource_name(self) -> None:
        runtime = formatter_runtime(self.source)

        self.assertEqual(
            runtime.call(
                "Resources_FormatTitle",
                {"payload": {"resource": "gold", "count": 150}},
                {},
            ),
            (LOC["collect"], 150, LOC["gold"]),
        )

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

    def test_poll_batches_completion_updates_around_state_traversal(self) -> None:
        poll_all = function_body(self.source, "Resources_PollAll")
        self.assertIn("BuildOrder_BeginCheckUpdates()", poll_all)
        self.assertIn("BuildOrder_EndCheckUpdates()", poll_all)
        self.assertLess(poll_all.index("BuildOrder_BeginCheckUpdates()"), poll_all.index("pairs(RESOURCES_STATE)"))
        self.assertLess(poll_all.index("pairs(RESOURCES_STATE)"), poll_all.index("BuildOrder_EndCheckUpdates()"))

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
