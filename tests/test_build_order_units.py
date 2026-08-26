import re
import tempfile
import unittest
from pathlib import Path

from tools.build_orders.compiler import compile_directory


ROOT = Path(__file__).resolve().parents[1]
UNITS_HANDLER = ROOT / "assets" / "scar" / "build_orders" / "checks" / "units.scar"


def function_body(source: str, name: str) -> str:
    match = re.search(
        rf"function {re.escape(name)}\([^)]*\)(.*?)(?=^function |\Z)",
        source,
        re.MULTILINE | re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"missing function {name}")
    return match.group(1)


class UnitsCompilerTests(unittest.TestCase):
    def compile(self, units: str):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "order.yaml"
            path.write_text(
                "civ: English\n"
                "title: Active units\n"
                "steps:\n"
                f"  - units: {units}\n",
                encoding="utf-8",
            )
            return compile_directory(path.parent).build_orders[0].steps[0].checks

    def test_renders_each_active_unit_threshold_with_its_exact_payload(self) -> None:
        checks = self.compile("[{id: spearman, count: 3}, {id: archer}]")
        self.assertEqual(
            [(check.title, check.optional, check.payload) for check in checks],
            [
                ("Have 3 spearman active", False, {"id": "spearman", "count": 3}),
                ("Have 1 archer active", False, {"id": "archer", "count": 1}),
            ],
        )


class UnitsHandlerContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = UNITS_HANDLER.read_text(encoding="utf-8") if UNITS_HANDLER.exists() else ""

    def test_registers_per_check_polling_handler(self) -> None:
        self.assertTrue(UNITS_HANDLER.exists(), "units handler is missing")
        self.assertIn('BuildOrder_RegisterHandler("units", {', self.source)
        activate = function_body(self.source, "Units_Activate")
        self.assertIn("local player = context.localPlayer", activate)
        self.assertIn("UNITS_STATE[check.id]", activate)
        self.assertIn("unitBlueprint = BP_GetSquadBlueprint(check.payload.id)", activate)
        self.assertIn("Rule_AddInterval(Units_Poll", activate)

    def test_recomputes_human_owned_living_canonical_squads_before_each_threshold(self) -> None:
        scan = function_body(self.source, "Units_ScanSquad")
        owner = "Squad_GetPlayerOwner(squad) ~= state.player"
        blueprint = "Squad_GetBlueprint(squad) ~= state.unitBlueprint"
        alive = "Squad_IsAlive(squad) == false"
        self.assertIn(owner, scan)
        self.assertIn(blueprint, scan)
        self.assertIn(alive, scan)
        self.assertLess(scan.index(owner), scan.index(blueprint))
        self.assertLess(scan.index(owner), scan.index(alive))

        poll = function_body(self.source, "Units_Poll")
        self.assertIn("state.count = 0", poll)
        self.assertIn("SGroup_ForEach(Player_GetSquads(state.player), Units_ScanSquad)", poll)
        self.assertIn("state.count >= state.payload.count", poll)

    def test_poll_reports_both_threshold_and_below_threshold_transitions(self) -> None:
        poll = function_body(self.source, "Units_Poll")
        self.assertIn("for _, state in pairs(UNITS_STATE) do", poll)
        self.assertIn("BuildOrder_SetCheckComplete(state.checkID, state.count >= state.payload.count)", poll)
        self.assertNotIn("remaining", self.source)
        self.assertNotIn("seen", self.source)

    def test_deactivation_is_idempotent_and_removes_only_the_shared_poll_rule_after_last_check(self) -> None:
        deactivate = function_body(self.source, "Units_Deactivate")
        self.assertIn("if state == nil then", deactivate)
        self.assertIn("UNITS_STATE[check.id] = nil", deactivate)
        self.assertIn("if next(UNITS_STATE) == nil and UNITS_POLLING then", deactivate)
        self.assertIn("Rule_Remove(Units_Poll)", deactivate)


if __name__ == "__main__":
    unittest.main()
