import tempfile
import unittest
from pathlib import Path

from tools.build_orders.compiler import compile_directory


ROOT = Path(__file__).resolve().parents[1]
HANDLER_PATH = ROOT / "assets" / "scar" / "build_orders" / "checks" / "rallypoint.scar"
UNSUPPORTED_SUFFIX = " [OPTIONAL: rally target resource cannot be verified]"


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

    def test_single_rallypoint_visibly_explains_the_non_blocking_limitation(self) -> None:
        checks = self.compile("[food]")
        self.assertEqual(len(checks), 1)
        self.assertEqual(
            checks[0].title,
            "Rally new vils to food" + UNSUPPORTED_SUFFIX,
        )
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
                    "Rally Main TC to wood" + UNSUPPORTED_SUFFIX,
                    True,
                    {"resource": "wood", "tc_index": 1, "tc_count": 2},
                ),
                (
                    "Rally TC #2 to gold" + UNSUPPORTED_SUFFIX,
                    True,
                    {"resource": "gold", "tc_index": 2, "tc_count": 2},
                ),
            ],
        )


class UnsupportedRallypointModel:
    """Executable fallback contract while SCAR cannot identify rally resources."""

    def __init__(self) -> None:
        self.active: dict[str, str] = {}

    def activate(self, check_id: str, local_player: str) -> None:
        self.active.setdefault(check_id, local_player)

    def poll(self, check_id: str, observed_owner: str, observed_resource: str) -> bool:
        return False

    def deactivate(self, check_id: str) -> bool:
        return self.active.pop(check_id, None) is not None


class RallypointNonBlockingModelTests(unittest.TestCase):
    def test_matching_opponent_rally_cannot_transition_a_check(self) -> None:
        model = UnsupportedRallypointModel()
        model.activate("step:1", "human")

        self.assertFalse(model.poll("step:1", "opponent", "food"))
        self.assertEqual(model.active, {"step:1": "human"})

    def test_two_check_ids_coexist_without_cross_cleanup(self) -> None:
        model = UnsupportedRallypointModel()
        model.activate("step:1", "human")
        model.activate("step:2", "human")

        self.assertTrue(model.deactivate("step:1"))
        self.assertEqual(model.active, {"step:2": "human"})
        self.assertFalse(model.poll("step:2", "human", "wood"))

    def test_duplicate_activation_cleanup_and_late_poll_are_idempotent(self) -> None:
        model = UnsupportedRallypointModel()
        model.activate("step:1", "human")
        model.activate("step:1", "human")

        self.assertEqual(model.active, {"step:1": "human"})
        self.assertTrue(model.deactivate("step:1"))
        self.assertFalse(model.deactivate("step:1"))
        self.assertFalse(model.poll("step:1", "opponent", "food"))


class RallypointHandlerSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = HANDLER_PATH.read_text(encoding="utf-8")

    def test_unsupported_descriptor_never_selects_or_observes_a_town_center(self) -> None:
        self.assertIn('RALLYPOINT_STATE[check.id]', self.source)
        self.assertIn('BuildOrder_RegisterHandler("rallypoint"', self.source)
        self.assertIn("RALLYPOINT_STATE[check.id] = nil", self.source)
        self.assertIn("if state == nil then", self.source)
        self.assertIn("RALLYPOINT_STATE[check.id] ~= nil", self.source)
        self.assertIn("cannot identify the rally target resource", self.source)
        for unsupported_call in (
            "Rule_AddInterval",
            "Rule_Remove",
            "Player_GetEntities",
            "Entity_GetPlayerOwner",
            "Entity_GetRallyPointPositions",
            "BuildOrder_SetCheckComplete",
        ):
            self.assertNotIn(unsupported_call, self.source)


if __name__ == "__main__":
    unittest.main()
