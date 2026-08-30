import re
import tempfile
import unittest
from dataclasses import dataclass
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


@dataclass
class SquadFixture:
    owner: str
    blueprint: str
    alive: bool = True


class PoisonedOpponentSquad:
    def __init__(self, owner: str) -> None:
        self.owner = owner

    @property
    def blueprint(self) -> str:
        raise AssertionError("blueprint must not be read before opponent ownership is rejected")

    @property
    def alive(self) -> bool:
        raise AssertionError("alive status must not be read before opponent ownership is rejected")


class UnitsPollingModel:
    """Test-only executable contract for the SCAR polling boundary."""

    def __init__(self) -> None:
        self.checks: dict[str, dict[str, object]] = {}
        self.polling = False

    def activate(self, check_id: str, player: str, blueprint: str, count: int) -> None:
        self.checks[check_id] = {"player": player, "blueprint": blueprint, "count": count}
        self.polling = True

    def deactivate(self, check_id: str) -> None:
        self.checks.pop(check_id, None)
        self.polling = bool(self.checks)

    def poll(self, squads: list[SquadFixture | PoisonedOpponentSquad]) -> dict[str, bool]:
        completed: dict[str, bool] = {}
        for check_id, check in self.checks.items():
            active_count = 0
            for squad in squads:
                if squad.owner != check["player"]:
                    continue
                if squad.blueprint != check["blueprint"]:
                    continue
                if squad.alive is False:
                    continue
                active_count += 1
            completed[check_id] = active_count >= check["count"]
        return completed


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
        checks = self.compile("[{id: spearman_2, count: 3}, {id: longbowman_2}]")
        self.assertEqual(
            [(check.title, check.optional, check.payload) for check in checks],
            [
                ("spearman 2", False, {"id": "unit_spearman_2_eng", "count": 3}),
                ("longbowman 2", False, {"id": "unit_archer_2_eng", "count": 1}),
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
        self.assertIn("pbg = BP_GetSquadBlueprint(check.payload.id)", activate)
        self.assertIn("Rule_AddInterval(Units_Poll", activate)
        self.assertIn("Units_Poll()", activate)

    def test_resolves_unit_blueprint_at_activation_not_each_poll(self) -> None:
        self.assertIn("pbg = BP_GetSquadBlueprint(check.payload.id)", self.source)
        start = self.source.index("function Units_Poll")
        end = self.source.index("function Units_Activate", start + 1)
        poll = self.source[start:end]
        self.assertNotIn("BP_GetSquadBlueprint", poll)
        self.assertIn("state.pbg", poll)

    def test_recomputes_human_owned_living_canonical_squads_before_each_threshold(self) -> None:
        scan = function_body(self.source, "Units_ScanSquad")
        owner = "Squad_GetPlayerOwner(squad) ~= state.player"
        blueprint = "Squad_GetBlueprint(squad) ~= state.pbg"
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


class UnitsPollingBehaviorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.model = UnitsPollingModel()
        self.model.activate("spears", "human", "spearman", 2)

    def test_opponent_squad_is_rejected_before_blueprint_or_alive_are_observed(self) -> None:
        result = self.model.poll(
            [
                SquadFixture("human", "spearman"),
                SquadFixture("human", "spearman"),
                PoisonedOpponentSquad("opponent"),
            ]
        )
        self.assertEqual(result, {"spears": True})

    def test_death_below_threshold_reverses_a_completed_check(self) -> None:
        first = SquadFixture("human", "spearman")
        second = SquadFixture("human", "spearman")
        self.assertEqual(self.model.poll([first, second]), {"spears": True})
        second.alive = False
        self.assertEqual(self.model.poll([first, second]), {"spears": False})

    def test_conversion_away_from_the_human_reverses_a_completed_check(self) -> None:
        first = SquadFixture("human", "spearman")
        second = SquadFixture("human", "spearman")
        self.assertEqual(self.model.poll([first, second]), {"spears": True})
        second.owner = "opponent"
        self.assertEqual(self.model.poll([first, second]), {"spears": False})

    def test_simultaneous_descriptors_remain_independent_when_one_is_removed(self) -> None:
        self.model.activate("archers", "human", "archer", 1)
        squads = [SquadFixture("human", "spearman"), SquadFixture("human", "spearman"), SquadFixture("human", "archer")]
        self.assertEqual(self.model.poll(squads), {"spears": True, "archers": True})
        self.model.deactivate("spears")
        self.assertTrue(self.model.polling)
        self.assertEqual(self.model.poll(squads), {"archers": True})
        self.model.deactivate("archers")
        self.model.deactivate("archers")
        self.assertFalse(self.model.polling)
        self.assertEqual(self.model.poll(squads), {})


if __name__ == "__main__":
    unittest.main()
