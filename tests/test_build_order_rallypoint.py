import tempfile
import unittest
from pathlib import Path

from tools.build_orders.compiler import compile_directory


ROOT = Path(__file__).resolve().parents[1]
HANDLER_PATH = ROOT / "assets" / "scar" / "build_orders" / "checks" / "rallypoint.scar"


class RallypointCompilerTests(unittest.TestCase):
    def compile(self, rallypoint: str):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "order.yaml"
            source.write_text(
                "civ: english\n"
                "title: Rally test\n"
                "steps:\n"
                f"  - rallypoint: {rallypoint}\n",
                encoding="utf-8",
            )
            return compile_directory(Path(temp)).build_orders[0].steps[0].checks

    def test_single_rallypoint_has_a_clear_non_blocking_title_and_payload(self) -> None:
        checks = self.compile("[food]")
        self.assertEqual(len(checks), 1)
        self.assertEqual(checks[0].title, "Rally new vils to food")
        self.assertTrue(checks[0].optional)
        self.assertEqual(
            checks[0].payload,
            {"resource": "food", "tc_index": 1, "tc_count": 1},
        )

    def test_multiple_rallypoints_have_stable_one_based_titles_and_payloads(self) -> None:
        checks = self.compile("[wood, gold]")
        self.assertEqual(
            [(check.title, check.optional, check.payload) for check in checks],
            [
                (
                    "Rally Main TC to wood",
                    True,
                    {"resource": "wood", "tc_index": 1, "tc_count": 2},
                ),
                (
                    "Rally TC #2 to gold",
                    True,
                    {"resource": "gold", "tc_index": 2, "tc_count": 2},
                ),
            ],
        )


class RallypointHandlerContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = HANDLER_PATH.read_text(encoding="utf-8")

    def test_registers_per_check_reversible_polling_state(self) -> None:
        self.assertIn('RALLYPOINT_STATE[check.id]', self.source)
        self.assertIn('BuildOrder_RegisterHandler("rallypoint"', self.source)
        self.assertIn("Rule_AddInterval(state.rule, 1)", self.source)
        self.assertIn("Rule_Remove(state.rule)", self.source)
        self.assertIn("RALLYPOINT_STATE[check.id] = nil", self.source)
        self.assertIn("if state == nil then", self.source)
        self.assertIn("BuildOrder_SetCheckComplete(check.id, false)", self.source)

    def test_observes_only_explicitly_owned_local_player_town_centers(self) -> None:
        self.assertIn("local player = context.localPlayer", self.source)
        self.assertIn("Player_GetEntities(player)", self.source)
        self.assertIn("Entity_GetPlayerOwner(entity) ~= player", self.source)
        self.assertIn('Entity_IsEBPOfType(blueprint, "town_center_capital")', self.source)
        self.assertIn('Entity_IsEBPOfType(blueprint, "town_center")', self.source)
        self.assertNotIn("Game_GetLocalPlayer", self.source)
        self.assertNotIn("World_GetPlayer", self.source)

    def test_uses_the_supported_rally_target_query_without_inferring_resource_completion(self) -> None:
        self.assertIn("Entity_GetRallyPointPositions(townCenter)", self.source)
        self.assertIn("rallyPositions.position1", self.source)
        self.assertIn("activeState.payload.tc_index", self.source)
        self.assertIn("activeState.payload.tc_count", self.source)
        self.assertNotIn("BuildOrder_SetCheckComplete(check.id, true)", self.source)
        self.assertIn("cannot identify the rally target resource", self.source)


if __name__ == "__main__":
    unittest.main()
