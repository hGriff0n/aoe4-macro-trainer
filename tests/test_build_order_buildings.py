import re
import unittest
from dataclasses import dataclass
from pathlib import Path

from tests.scar_runtime import ScarRuntime


ROOT = Path(__file__).resolve().parents[1]
SCAR_ROOT = ROOT / "assets" / "scar"
BUILDINGS_HANDLER = SCAR_ROOT / "build_orders" / "checks" / "buildings.scar"
MAIN_WINCONDITION = SCAR_ROOT / "winconditions" / "Macro Trainer.scar"


def formatter_runtime(source: str) -> tuple[ScarRuntime, list[tuple[str, str]]]:
    registration_stub = "function BuildOrder_RegisterHandler(kind, handler)\nend"
    runtime = ScarRuntime(registration_stub + "\n" + source)
    calls = []

    def game_name(kind, identifier, _context):
        calls.append((kind, identifier))
        return "Town Center"

    runtime.globals["BuildOrder_GameName"] = game_name
    return runtime, calls


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
class BuildingFixture:
    owner: str
    blueprint: object
    is_building: bool = True
    progress: float = 1.0


class PoisonedOpponentBuilding:
    def __init__(self, owner: str) -> None:
        self.owner = owner

    @property
    def is_building(self) -> bool:
        raise AssertionError("building type must not be read before opponent ownership is rejected")

    @property
    def progress(self) -> float:
        raise AssertionError("building progress must not be read before opponent ownership is rejected")

    @property
    def blueprint(self) -> object:
        raise AssertionError("blueprint must not be read before opponent ownership is rejected")


class BuildingsPollingModel:
    """Executable contract for the live, reversible buildings threshold."""

    def __init__(self) -> None:
        self.checks: dict[str, dict[str, object]] = {}
        self.polling = False

    def activate(self, check_id: str, player: str, blueprint: object, count: int) -> None:
        self.checks[check_id] = {"player": player, "blueprint": blueprint, "count": count}
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

    def poll(self, entities: list[BuildingFixture | PoisonedOpponentBuilding]) -> dict[str, bool]:
        completed: dict[str, bool] = {}
        for check_id, check in self.checks.items():
            matching_count = 0
            for entity in entities:
                if entity.owner != check["player"]:
                    continue
                if entity.is_building is False:
                    continue
                if entity.progress < 1.0:
                    continue
                if not self.blueprints_equal(check["blueprint"], entity.blueprint):
                    continue
                matching_count += 1
            completed[check_id] = matching_count >= check["count"]
        return completed


class BuildingsHandlerContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = BUILDINGS_HANDLER.read_text(encoding="utf-8") if BUILDINGS_HANDLER.exists() else ""
        cls.main_source = MAIN_WINCONDITION.read_text(encoding="utf-8")

    def test_registers_the_advertised_buildings_handler_and_imports_it(self) -> None:
        self.assertTrue(BUILDINGS_HANDLER.exists(), "buildings handler is missing")
        self.assertIn('BuildOrder_RegisterHandler("buildings", {', self.source)
        self.assertIn('import("build_orders/checks/buildings.scar")', self.main_source)
        self.assertIn("formatTitle = Buildings_FormatTitle", self.source)

    def test_formatter_returns_the_localized_entity_name_without_count_copy(self) -> None:
        runtime, calls = formatter_runtime(self.source)

        title = runtime.call(
            "Buildings_FormatTitle",
            {"payload": {"id": "town_center", "count": 3}},
            {},
        )

        self.assertEqual(title, "Town Center")
        self.assertEqual(calls, [("entity", "town_center")])

    def test_every_advertised_nonoptional_kind_has_an_imported_handler(self) -> None:
        advertised = (
            "vils",
            "rallypoint",
            "built",
            "age_up",
            "upgrades",
            "produce",
            "resources",
            "buildings",
            "units",
        )
        for kind in advertised:
            with self.subTest(kind=kind):
                path = SCAR_ROOT / "build_orders" / "checks" / f"{kind}.scar"
                source = path.read_text(encoding="utf-8") if path.exists() else ""
                self.assertTrue(path.exists(), f"{kind} is compiled but has no handler")
                self.assertIn(
                    f'BuildOrder_RegisterHandler("{kind}", {{',
                    source,
                    f"{kind} handler is not registered",
                )
                self.assertIn(f'import("build_orders/checks/{kind}.scar")', self.main_source)

    def test_activation_resolves_a_single_building_pbg_and_starts_shared_polling(self) -> None:
        activate = function_body(self.source, "Buildings_Activate")
        self.assertIn("local player = context.localPlayer", activate)
        self.assertIn("pbg = Buildings_ResolvePBG(check.payload.id)", activate)
        self.assertIn("BUILDINGS_STATE[check.id]", activate)
        self.assertIn("Rule_AddInterval(Buildings_Poll", activate)
        self.assertIn("Buildings_Poll()", activate)

    def test_scan_rejects_opponents_before_building_state_or_blueprint(self) -> None:
        scan = function_body(self.source, "Buildings_ScanEntity")
        owner = "Entity_GetPlayerOwner(entity) ~= state.player"
        building = "Entity_IsBuilding(entity) == false"
        progress = "Entity_GetBuildingProgress(entity) < 1.0"
        blueprint = "Buildings_MatchesPBG(state.pbg, Entity_GetBlueprint(entity)) == false"
        self.assertIn(owner, scan)
        self.assertIn(building, scan)
        self.assertIn(progress, scan)
        self.assertIn(blueprint, scan)
        self.assertLess(scan.index(owner), scan.index(building))
        self.assertLess(scan.index(owner), scan.index(progress))
        self.assertLess(scan.index(owner), scan.index(blueprint))

    def test_compares_complete_pbg_tuple_and_recomputes_threshold_each_poll(self) -> None:
        equal = function_body(self.source, "Buildings_BlueprintsEqual")
        self.assertIn("PropertyBagGroupID", equal)
        self.assertIn("PropertyBagGroupModPackID", equal)
        self.assertIn("PropertyBagGroupType", equal)

        poll = function_body(self.source, "Buildings_Poll")
        self.assertIn("state.count = 0", poll)
        self.assertIn("EGroup_ForEach(Player_GetEntities(state.player), Buildings_ScanEntity)", poll)
        self.assertIn("state.count >= state.payload.count", poll)
        self.assertIn("BuildOrder_BeginCheckUpdates()", poll)
        self.assertIn("BuildOrder_EndCheckUpdates()", poll)

    def test_deactivation_is_idempotent_and_removes_polling_after_the_last_check(self) -> None:
        deactivate = function_body(self.source, "Buildings_Deactivate")
        self.assertIn("if state == nil then", deactivate)
        self.assertIn("BUILDINGS_STATE[check.id] = nil", deactivate)
        self.assertIn("if next(BUILDINGS_STATE) == nil and BUILDINGS_POLLING then", deactivate)
        self.assertIn("Rule_Remove(Buildings_Poll)", deactivate)


class BuildingsPollingBehaviorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.model = BuildingsPollingModel()
        self.model.activate("houses", "human", "building_house", 2)

    def test_opponent_is_rejected_before_any_other_entity_property_is_observed(self) -> None:
        self.assertEqual(
            self.model.poll(
                [
                    BuildingFixture("human", "building_house"),
                    BuildingFixture("human", "building_house"),
                    PoisonedOpponentBuilding("opponent"),
                ]
            ),
            {"houses": True},
        )

    def test_incomplete_or_non_building_entities_do_not_count(self) -> None:
        self.assertEqual(
            self.model.poll(
                [
                    BuildingFixture("human", "building_house", progress=0.9),
                    BuildingFixture("human", "building_house", is_building=False),
                    BuildingFixture("human", "building_house"),
                ]
            ),
            {"houses": False},
        )

    def test_destruction_or_conversion_reverses_a_completed_threshold(self) -> None:
        first = BuildingFixture("human", "building_house")
        second = BuildingFixture("human", "building_house")
        self.assertEqual(self.model.poll([first, second]), {"houses": True})
        second.owner = "opponent"
        self.assertEqual(self.model.poll([first, second]), {"houses": False})

    def test_pbg_value_equality_counts_starting_buildings(self) -> None:
        expected = PbgFixture(101, 2, 3)
        actual = PbgFixture(101, 2, 3)
        self.model.activate("capital", "human", expected, 1)
        self.assertEqual(
            self.model.poll([BuildingFixture("human", actual)]),
            {"houses": False, "capital": True},
        )

    def test_simultaneous_descriptors_and_idempotent_deactivation_remain_independent(self) -> None:
        self.model.activate("barracks", "human", "building_barracks", 1)
        entities = [BuildingFixture("human", "building_house"), BuildingFixture("human", "building_house"), BuildingFixture("human", "building_barracks")]
        self.assertEqual(self.model.poll(entities), {"houses": True, "barracks": True})
        self.model.deactivate("houses")
        self.assertTrue(self.model.polling)
        self.assertEqual(self.model.poll(entities), {"barracks": True})
        self.model.deactivate("barracks")
        self.model.deactivate("barracks")
        self.assertFalse(self.model.polling)


if __name__ == "__main__":
    unittest.main()
