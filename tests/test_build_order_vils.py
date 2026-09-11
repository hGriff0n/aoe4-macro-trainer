import re
import unittest
from pathlib import Path

from tests.scar_runtime import ScarRuntime


ROOT = Path(__file__).resolve().parents[1]
VILS_PATH = ROOT / "assets" / "scar" / "build_orders" / "checks" / "vils.scar"
MAIN_PATH = ROOT / "assets" / "scar" / "winconditions" / "Macro Trainer.scar"
LOCALIZATION_PATH = ROOT / "assets" / "scar" / "build_orders" / "localization.scar"
LOC = {
    "food": "$dfb5645698a84afb91cf7a2dfb0f4a4e:148",
    "gold": "$dfb5645698a84afb91cf7a2dfb0f4a4e:149",
    "wood": "$dfb5645698a84afb91cf7a2dfb0f4a4e:150",
    "allocation": "$dfb5645698a84afb91cf7a2dfb0f4a4e:152",
    "allocationJoin": "$dfb5645698a84afb91cf7a2dfb0f4a4e:153",
    "assign": "$dfb5645698a84afb91cf7a2dfb0f4a4e:156",
    "noCollect": "$dfb5645698a84afb91cf7a2dfb0f4a4e:157",
}


def formatter_runtime(source: str) -> ScarRuntime:
    registration_stub = "function BuildOrder_RegisterHandler(kind, handler)\nend"
    localization = LOCALIZATION_PATH.read_text(encoding="utf-8")
    runtime = ScarRuntime(registration_stub + "\n" + localization + "\n" + source)
    runtime.globals["Loc_FormatText"] = lambda key, *values: (key, *values)
    runtime.globals["Loc_Empty"] = lambda: ()
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


class BuildOrderVilsContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = VILS_PATH.read_text(encoding="utf-8") if VILS_PATH.exists() else ""

    def test_vils_handler_module_exists(self) -> None:
        self.assertTrue(VILS_PATH.exists(), "vils handler must be added")

    def test_main_wincondition_imports_the_vils_handler(self) -> None:
        source = MAIN_PATH.read_text(encoding="utf-8")
        self.assertIn('import("build_orders/checks/vils.scar")', source)

    def test_registers_vils_handler_with_lifecycle_functions(self) -> None:
        self.assertIn('BuildOrder_RegisterHandler("vils", {', self.source)
        self.assertIn("activate = Vils_Activate", self.source)
        self.assertIn("deactivate = Vils_Deactivate", self.source)
        self.assertIn("formatTitle = Vils_FormatTitle", self.source)

    def test_formatter_orders_and_joins_allocation_fragments(self) -> None:
        runtime = formatter_runtime(self.source)
        food = (LOC["allocation"], 6, LOC["food"])
        gold = (LOC["allocation"], 3, LOC["gold"])

        self.assertEqual(
            runtime.call(
                "Vils_FormatTitle",
                {"payload": {"gold": 3, "food": 6}},
                {},
            ),
            (LOC["assign"], (LOC["allocationJoin"], food, gold)),
        )

    def test_formatter_uses_no_collect_template_before_allocations(self) -> None:
        runtime = formatter_runtime(self.source)

        self.assertEqual(
            runtime.call(
                "Vils_FormatTitle",
                {"payload": {"resource": "wood", "no_collect": True}},
                {},
            ),
            (LOC["noCollect"], LOC["wood"]),
        )

    def test_activation_stores_the_context_local_player_per_check(self) -> None:
        activate = function_body(self.source, "Vils_Activate")
        self.assertIn("VILS_STATE[check.id]", activate)
        self.assertIn("player = context.localPlayer", activate)
        self.assertIn("payload = check.payload", activate)

    def test_poll_queries_only_the_stored_player_and_combines_thresholds(self) -> None:
        poll = function_body(self.source, "Vils_Poll")
        self.assertIn("local state = VILS_STATE[checkID]", poll)
        self.assertIn("Player_GetNumGatheringSquads(state.player, RT_Food)", poll)
        self.assertIn("Player_GetNumGatheringSquads(state.player, RT_Gold)", poll)
        self.assertIn("Player_GetNumGatheringSquads(state.player, RT_Wood)", poll)
        self.assertIn("Player_GetNumGatheringSquads(state.player, RT_Stone)", poll)
        self.assertRegex(poll, r"completed\s*=\s*completed\s+and")

    def test_poll_reports_both_complete_and_incomplete_states(self) -> None:
        poll = function_body(self.source, "Vils_Poll")
        self.assertIn("BuildOrder_SetCheckComplete(checkID, true)", poll)
        self.assertIn("BuildOrder_SetCheckComplete(checkID, false)", poll)

    def test_handler_has_no_diagnostic_poll_logging(self) -> None:
        self.assertNotIn("Vils_LogPoll", self.source)
        self.assertNotIn("GRI55_VILS", self.source)
        self.assertNotIn("print(", self.source)

    def test_poll_treats_missing_or_non_numeric_counts_as_incomplete(self) -> None:
        poll = function_body(self.source, "Vils_Poll")
        normalize = function_body(self.source, "Vils_CountOrZero")
        self.assertIn('type(value) ~= "number"', normalize)
        for resource in ("food", "gold", "wood", "stone"):
            self.assertIn(f"{resource} = Vils_CountOrZero({resource})", poll)

    def test_uses_one_named_shared_poll_rule_for_all_active_checks(self) -> None:
        activate = function_body(self.source, "Vils_Activate")
        deactivate = function_body(self.source, "Vils_Deactivate")
        poll_all = function_body(self.source, "Vils_PollAll")
        self.assertIn("for checkID", poll_all)
        self.assertIn("Vils_Poll(checkID)", poll_all)
        self.assertIn("Rule_Add(Vils_PollAll)", activate)
        self.assertNotIn("Rule_Add(function", self.source)
        self.assertNotIn("state.pollRule = function()", self.source)

    def test_poll_batch_prevents_step_mutation_during_state_traversal(self) -> None:
        poll_all = function_body(self.source, "Vils_PollAll")
        self.assertIn("BuildOrder_BeginCheckUpdates()", poll_all)
        self.assertIn("BuildOrder_EndCheckUpdates()", poll_all)
        self.assertLess(poll_all.index("BuildOrder_BeginCheckUpdates()"), poll_all.index("pairs(VILS_STATE)"))
        self.assertLess(poll_all.index("pairs(VILS_STATE)"), poll_all.index("BuildOrder_EndCheckUpdates()"))

    def test_removes_the_shared_rule_only_after_the_last_active_check(self) -> None:
        deactivate = function_body(self.source, "Vils_Deactivate")
        self.assertIn("VILS_STATE[check.id] = nil", deactivate)
        self.assertIn("next(VILS_STATE) == nil", deactivate)
        self.assertIn("Rule_Remove(Vils_PollAll)", deactivate)


if __name__ == "__main__":
    unittest.main()
