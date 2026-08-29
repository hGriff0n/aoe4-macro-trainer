import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VILS_PATH = ROOT / "assets" / "scar" / "build_orders" / "checks" / "vils.scar"


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

    def test_registers_vils_handler_with_lifecycle_functions(self) -> None:
        self.assertIn('BuildOrder_RegisterHandler("vils", {', self.source)
        self.assertIn("activate = Vils_Activate", self.source)
        self.assertIn("deactivate = Vils_Deactivate", self.source)

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

    def test_uses_one_named_shared_poll_rule_for_all_active_checks(self) -> None:
        activate = function_body(self.source, "Vils_Activate")
        deactivate = function_body(self.source, "Vils_Deactivate")
        poll_all = function_body(self.source, "Vils_PollAll")
        self.assertIn("for checkID", poll_all)
        self.assertIn("Vils_Poll(checkID)", poll_all)
        self.assertIn("Rule_Add(Vils_PollAll)", activate)
        self.assertNotIn("Rule_Add(function", self.source)
        self.assertNotIn("state.pollRule = function()", self.source)

    def test_removes_the_shared_rule_only_after_the_last_active_check(self) -> None:
        deactivate = function_body(self.source, "Vils_Deactivate")
        self.assertIn("VILS_STATE[check.id] = nil", deactivate)
        self.assertIn("next(VILS_STATE) == nil", deactivate)
        self.assertIn("Rule_Remove(Vils_PollAll)", deactivate)


if __name__ == "__main__":
    unittest.main()
