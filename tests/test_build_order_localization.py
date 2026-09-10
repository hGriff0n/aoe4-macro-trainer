import csv
import unittest
from pathlib import Path

from tests.scar_runtime import LuaResults, ScarRuntime


ROOT = Path(__file__).resolve().parents[1]
LOCALIZATION_PATH = ROOT / "assets" / "scar" / "build_orders" / "localization.scar"
LOCDB_PATH = ROOT / "assets" / "locdb" / "Macro Trainer_en.csv"
LOC_PREFIX = "$dfb5645698a84afb91cf7a2dfb0f4a4e:"


EXPECTED_LOCDB = {
    143: ("Raw authored build-order text.", "%1TEXT%"),
    144: ("Generated build-order step title.", "Step #%1COUNT%"),
    145: ("Build-order hint title.", "[HINT] %1TEXT%"),
    146: ("Optional check title wrapper.", "[Optional] %1TEXT%"),
    147: ("Unavailable check title.", "Build-order check unavailable"),
    148: ("Build-order resource name.", "food"),
    149: ("Build-order resource name.", "gold"),
    150: ("Build-order resource name.", "wood"),
    151: ("Build-order resource name.", "stone"),
    152: ("Resource allocation fragment.", "%1COUNT% %2RESOURCE%"),
    153: ("Resource allocation separator.", "%1TEXT% | %2TEXT%"),
    154: ("Alternative target separator.", "%1TEXT% or %2TEXT%"),
    155: ("Resource collection check.", "Collect at least %1COUNT% %2RESOURCE%"),
    156: ("Villager assignment check.", "Assign %1ALLOCATIONS%"),
    157: ("No-collection villager check.", "No %1RESOURCE% villagers"),
    158: ("Rally-point check.", "Rally to %1RESOURCE%"),
    159: ("Single-building construction check.", "Build %1TARGET%"),
    160: ("Counted-building construction check.", "Build %1COUNT% %2TARGET%"),
    161: ("Age-up check.", "Age Up: %1TARGET%"),
    162: ("Research check.", "Research %1UPGRADE%"),
    163: ("Queued research check.", "Queue %1UPGRADE% for research"),
    164: ("Production check.", "Produce %1COUNT% %2UNIT%"),
    165: ("Queued production check.", "Queue %1COUNT% %2UNIT%"),
    166: ("Constant production check.", "Constantly produce %1UNIT%"),
    167: ("Active-unit count check.", "Have %1COUNT% active %2UNIT%"),
}


class BuildOrderLocalizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assertTrue(LOCALIZATION_PATH.exists(), "localization helper is missing")
        self.runtime = ScarRuntime(LOCALIZATION_PATH.read_text(encoding="utf-8"))
        self.formatted: list[tuple[object, ...]] = []
        self.logs: list[str] = []
        self.loc_to_ansi_calls: list[object] = []
        self.entity_ui_calls: list[str] = []
        self.squad_ui_calls: list[tuple[str, str]] = []
        self.upgrade_ui_calls: list[str] = []

        def format_text(key, *arguments):
            result = (key, *arguments)
            self.formatted.append(result)
            return result

        def pcall(function, *arguments):
            try:
                return LuaResults((True, function(*arguments)))
            except Exception as error:
                return LuaResults((False, str(error)))

        self.runtime.globals.update(
            {
                "Loc_FormatText": format_text,
                "Loc_Empty": lambda: ("empty",),
                "Loc_ToAnsi": lambda value: self.loc_to_ansi_calls.append(value),
                "pcall": pcall,
                "print": self.logs.append,
                "tostring": str,
                "BP_GetEntityBlueprint": lambda identifier: {"id": identifier},
                "BP_GetEntityUIInfo": self.entity_ui_info,
                "BP_GetSquadBlueprint": lambda identifier: {"id": identifier},
                "BP_GetSquadUIInfo": self.squad_ui_info,
                "BP_GetUpgradeBlueprint": lambda identifier: {"id": identifier},
                "BP_GetUpgradeUIInfo": self.upgrade_ui_info,
                "Player_GetRace": lambda player: f"race:{player}",
            }
        )

    def entity_ui_info(self, blueprint):
        identifier = blueprint["id"]
        self.entity_ui_calls.append(identifier)
        names = {
            "building_kremlin": "localized Kremlin",
            "building_stable": "localized Stable",
            "building_archery_range": "localized Archery Range",
        }
        return {"screenName": names.get(identifier, f"localized {identifier}")}

    def squad_ui_info(self, blueprint, race):
        identifier = blueprint["id"]
        self.squad_ui_calls.append((identifier, race))
        return {"screenName": "localized Spearman"}

    def upgrade_ui_info(self, blueprint):
        identifier = blueprint["id"]
        self.upgrade_ui_calls.append(identifier)
        return {"screenName": "localized Wheelbarrow"}

    def test_raw_text_uses_the_generic_authored_text_slot(self) -> None:
        self.assertEqual(
            self.runtime.call("BuildOrder_RawText", "Авторский текст"),
            (f"{LOC_PREFIX}143", "Авторский текст"),
        )

    def test_join_localized_preserves_order_and_handles_empty_values(self) -> None:
        self.assertEqual(
            self.runtime.call(
                "BuildOrder_JoinLocalized",
                ["first", "second", "third"],
                f"{LOC_PREFIX}154",
            ),
            (
                f"{LOC_PREFIX}154",
                (f"{LOC_PREFIX}154", "first", "second"),
                "third",
            ),
        )
        self.assertEqual(
            self.runtime.call("BuildOrder_JoinLocalized", [], f"{LOC_PREFIX}154"),
            ("empty",),
        )

    def test_resource_names_cover_every_supported_resource(self) -> None:
        for resource, slot in (
            ("food", 148),
            ("gold", 149),
            ("wood", 150),
            ("stone", 151),
        ):
            with self.subTest(resource=resource):
                self.assertEqual(
                    self.runtime.call("BuildOrder_ResourceName", resource),
                    f"{LOC_PREFIX}{slot}",
                )

    def test_entity_name_returns_the_locstring_without_ansi_conversion(self) -> None:
        context = {"localPlayer": "player"}

        self.assertEqual(
            self.runtime.call(
                "BuildOrder_GameName", "entity", "building_kremlin", context
            ),
            "localized Kremlin",
        )
        self.assertEqual(self.entity_ui_calls, ["building_kremlin"])
        self.assertEqual(self.loc_to_ansi_calls, [])

    def test_squad_name_uses_the_context_players_race(self) -> None:
        self.assertEqual(
            self.runtime.call(
                "BuildOrder_GameName",
                "squad",
                "unit_spearman_2_eng",
                {"localPlayer": "human"},
            ),
            "localized Spearman",
        )
        self.assertEqual(
            self.squad_ui_calls,
            [("unit_spearman_2_eng", "race:human")],
        )

    def test_upgrade_name_uses_upgrade_ui_info(self) -> None:
        self.assertEqual(
            self.runtime.call(
                "BuildOrder_GameName",
                "upgrade",
                "upgrade_wheelbarrow_eng",
                {"localPlayer": "human"},
            ),
            "localized Wheelbarrow",
        )
        self.assertEqual(self.upgrade_ui_calls, ["upgrade_wheelbarrow_eng"])

    def test_missing_or_failed_names_log_and_use_the_raw_wrapper(self) -> None:
        for failure_point in ("blueprint", "ui"):
            with self.subTest(failure_point=failure_point):
                if failure_point == "blueprint":
                    self.runtime.globals["BP_GetEntityBlueprint"] = lambda _id: 1 / 0
                else:
                    self.runtime.globals["BP_GetEntityBlueprint"] = lambda identifier: {
                        "id": identifier
                    }
                    self.runtime.globals["BP_GetEntityUIInfo"] = lambda _pbg: 1 / 0

                self.assertEqual(
                    self.runtime.call(
                        "BuildOrder_GameName",
                        "entity",
                        "building_missing",
                        {"localPlayer": "human"},
                    ),
                    (f"{LOC_PREFIX}143", "building_missing"),
                )
        self.assertEqual(len(self.logs), 2)
        self.assertTrue(all("building_missing" in message for message in self.logs))

    def test_target_names_preserve_oneof_order(self) -> None:
        result = self.runtime.call(
            "BuildOrder_TargetNames",
            {"oneof": ["building_stable", "building_archery_range"]},
            "entity",
            {"localPlayer": "human"},
        )

        self.assertEqual(
            result,
            (
                f"{LOC_PREFIX}154",
                "localized Stable",
                "localized Archery Range",
            ),
        )
        self.assertEqual(
            self.entity_ui_calls,
            ["building_stable", "building_archery_range"],
        )

    def test_target_names_resolve_a_single_id(self) -> None:
        result = self.runtime.call(
            "BuildOrder_TargetNames",
            {"id": "building_kremlin"},
            "entity",
            {"localPlayer": "human"},
        )

        self.assertEqual(result, "localized Kremlin")
        self.assertEqual(self.entity_ui_calls, ["building_kremlin"])

    def test_first_squad_name_uses_only_the_first_canonical_id(self) -> None:
        result = self.runtime.call(
            "BuildOrder_FirstSquadName",
            {"ids": ["unit_spearman_1_eng", "unit_spearman_2_eng"]},
            {"localPlayer": "human"},
        )

        self.assertEqual(result, "localized Spearman")
        self.assertEqual(
            self.squad_ui_calls,
            [("unit_spearman_1_eng", "race:human")],
        )


class BuildOrderLocalizationLocdbTests(unittest.TestCase):
    def test_locdb_slots_are_generic_and_obsolete_exact_titles_are_removed(self) -> None:
        with LOCDB_PATH.open(encoding="utf-8-sig", newline="") as source:
            rows = {int(row["ID"]): row for row in csv.DictReader(source)}

        for identifier, (notes, text) in EXPECTED_LOCDB.items():
            with self.subTest(identifier=identifier):
                self.assertEqual(rows[identifier]["Notes"], notes)
                self.assertEqual(rows[identifier]["Text"], text)
        self.assertFalse(any(identifier in rows for identifier in range(168, 173)))


if __name__ == "__main__":
    unittest.main()
