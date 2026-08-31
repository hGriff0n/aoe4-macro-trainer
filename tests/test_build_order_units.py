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


class PbgFixture:
    def __init__(self, group_id: int, modpack_id: int, type_id: int) -> None:
        self.PropertyBagGroupID = group_id
        self.PropertyBagGroupModPackID = modpack_id
        self.PropertyBagGroupType = type_id


@dataclass
class SquadFixture:
    owner: str
    blueprint: object
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

    def activate(self, check_id: str, player: str, blueprints: list[object], count: int) -> None:
        self.checks[check_id] = {"player": player, "blueprints": blueprints, "count": count}
        self.polling = True

    def deactivate(self, check_id: str) -> None:
        self.checks.pop(check_id, None)
        self.polling = bool(self.checks)

    @staticmethod
    def blueprints_equal(left: object, right: object) -> bool:
        if isinstance(left, PbgFixture) and isinstance(right, PbgFixture):
            return (
                left.PropertyBagGroupID == right.PropertyBagGroupID
                and left.PropertyBagGroupModPackID == right.PropertyBagGroupModPackID
                and left.PropertyBagGroupType == right.PropertyBagGroupType
            )
        return left == right

    def matches_blueprint(self, blueprints: list[object], blueprint: object) -> bool:
        return any(self.blueprints_equal(candidate, blueprint) for candidate in blueprints)

    def poll(self, squads: list[SquadFixture | PoisonedOpponentSquad]) -> dict[str, bool]:
        completed: dict[str, bool] = {}
        for check_id, check in self.checks.items():
            active_count = 0
            for squad in squads:
                if squad.owner != check["player"]:
                    continue
                if not self.matches_blueprint(check["blueprints"], squad.blueprint):
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
                ("Have 3 active spearman", False, {"ids": ["unit_spearman_2_eng", "unit_spearman_3_eng", "unit_spearman_4_eng"], "count": 3}),
                ("Have 1 active longbowman", False, {"ids": ["unit_archer_2_eng", "unit_archer_3_eng", "unit_archer_4_eng"], "count": 1}),
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
        self.assertIn("pbgs = Units_ResolvePBGs(check.payload.ids)", activate)
        self.assertIn("Rule_AddInterval(Units_Poll", activate)
        self.assertIn("Units_Poll()", activate)

    def test_resolves_every_unit_family_blueprint_at_activation_not_each_poll(self) -> None:
        resolver = function_body(self.source, "Units_ResolvePBGs")
        self.assertIn("BP_GetSquadBlueprint", resolver)
        start = self.source.index("function Units_Poll")
        end = self.source.index("function Units_Activate", start + 1)
        poll = self.source[start:end]
        self.assertNotIn("BP_GetSquadBlueprint", poll)
        self.assertIn("state.pbgs", poll)

    def test_matches_squad_blueprints_by_pbg_tuple_value(self) -> None:
        matcher = function_body(self.source, "Units_BlueprintsEqual")
        self.assertIn("left.PropertyBagGroupID == right.PropertyBagGroupID", matcher)
        self.assertIn("left.PropertyBagGroupModPackID == right.PropertyBagGroupModPackID", matcher)
        self.assertIn("left.PropertyBagGroupType == right.PropertyBagGroupType", matcher)
        matcher = function_body(self.source, "Units_MatchesPBG")
        self.assertIn("Units_BlueprintsEqual(candidate, pbg)", matcher)
        scan = function_body(self.source, "Units_ScanSquad")
        self.assertIn("Units_MatchesPBG(state.pbgs, Squad_GetBlueprint(squad)) == false", scan)

    def test_recomputes_human_owned_living_canonical_squads_before_each_threshold(self) -> None:
        scan = function_body(self.source, "Units_ScanSquad")
        owner = "Squad_GetPlayerOwner(squad) ~= state.player"
        blueprint = "Units_MatchesPBG(state.pbgs, Squad_GetBlueprint(squad)) == false"
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

    def test_poll_batches_completion_updates_around_state_traversal(self) -> None:
        poll = function_body(self.source, "Units_Poll")
        self.assertIn("BuildOrder_BeginCheckUpdates()", poll)
        self.assertIn("BuildOrder_EndCheckUpdates()", poll)
        self.assertLess(poll.index("BuildOrder_BeginCheckUpdates()"), poll.index("pairs(UNITS_STATE)"))
        self.assertLess(poll.index("pairs(UNITS_STATE)"), poll.index("BuildOrder_EndCheckUpdates()"))

    def test_deactivation_is_idempotent_and_removes_only_the_shared_poll_rule_after_last_check(self) -> None:
        deactivate = function_body(self.source, "Units_Deactivate")
        self.assertIn("if state == nil then", deactivate)
        self.assertIn("UNITS_STATE[check.id] = nil", deactivate)
        self.assertIn("if next(UNITS_STATE) == nil and UNITS_POLLING then", deactivate)
        self.assertIn("Rule_Remove(Units_Poll)", deactivate)


class UnitsPollingBehaviorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.model = UnitsPollingModel()
        self.model.activate("spears", "human", ["spearman"], 2)

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

    def test_starting_scout_counts_when_its_pbg_tuple_matches_by_value(self) -> None:
        expected_scout = PbgFixture(199733, 0, 0)
        starting_scout = PbgFixture(199733, 0, 0)
        self.model.activate("scouts", "human", [expected_scout], 1)

        self.assertEqual(
            self.model.poll([SquadFixture("human", starting_scout)]),
            {"spears": False, "scouts": True},
        )

    def test_simultaneous_descriptors_remain_independent_when_one_is_removed(self) -> None:
        self.model.activate("archers", "human", ["archer"], 1)
        squads = [SquadFixture("human", "spearman"), SquadFixture("human", "spearman"), SquadFixture("human", "archer")]
        self.assertEqual(self.model.poll(squads), {"spears": True, "archers": True})
        self.model.deactivate("spears")
        self.assertTrue(self.model.polling)
        self.assertEqual(self.model.poll(squads), {"archers": True})
        self.model.deactivate("archers")
        self.model.deactivate("archers")
        self.assertFalse(self.model.polling)
        self.assertEqual(self.model.poll(squads), {})

    def test_owned_living_spearman_tiers_count_as_one_family_and_reverse_when_lost(self) -> None:
        dark_age = PbgFixture(101, 7, 2)
        feudal_age = PbgFixture(102, 7, 2)
        castle_age = PbgFixture(103, 7, 2)
        self.model.activate("family", "human", [dark_age, feudal_age, castle_age], 2)

        dark_spearman = SquadFixture("human", PbgFixture(101, 7, 2))
        feudal_spearman = SquadFixture("human", PbgFixture(102, 7, 2))
        castle_spearman = SquadFixture("human", PbgFixture(103, 7, 2))
        opponent_spearman = SquadFixture("opponent", PbgFixture(103, 7, 2))
        unrelated_owned_squad = SquadFixture("human", PbgFixture(404, 7, 2))

        self.assertEqual(
            self.model.poll([dark_spearman, feudal_spearman, opponent_spearman]),
            {"spears": False, "family": True},
        )
        feudal_spearman.owner = "opponent"
        self.assertEqual(
            self.model.poll([dark_spearman, feudal_spearman, opponent_spearman, unrelated_owned_squad]),
            {"spears": False, "family": False},
        )
        self.assertEqual(
            self.model.poll([dark_spearman, castle_spearman]),
            {"spears": False, "family": True},
        )
        castle_spearman.alive = False
        self.assertEqual(
            self.model.poll([dark_spearman, castle_spearman]),
            {"spears": False, "family": False},
        )


if __name__ == "__main__":
    unittest.main()
