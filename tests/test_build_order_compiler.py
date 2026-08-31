import tempfile
import unittest
from pathlib import Path

from tools.build_orders.compiler import BuildOrderValidationError, compile_directory
from tools.build_orders.identities import IdentityCatalog, SquadFamilyIdentity
from tools.build_orders.model import BuildOrder, Catalog, CheckDescriptor, Step, normalize_id


class BuildOrderCompilerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.identities = IdentityCatalog(
            {
                "abbasid": {
                    "entity": {},
                    "upgrade": {"economic_wing": "upgrade_add_economy_wing"},
                },
                "english": {
                    "entity": {
                        "archery_range": "building_archery_range_eng",
                        "barracks": "building_barracks_eng",
                        "council_hall": "building_landmark_age2_eng",
                        "house": "building_house_eng",
                        "outpost": "building_outpost_eng",
                        "council_hall_2": "building_landmark_age2_eng_2",
                        "palace_of_swabia_3": "building_landmark_age4_eng_3",
                        "stable": "building_stable_eng",
                        "town_center": "building_town_center_eng",
                    },
                    "upgrade": {
                        "horticulture": "upgrade_horticulture_eng",
                        "wheelbarrow": "upgrade_wheelbarrow_eng",
                        "wheelbarrow_1": "upgrade_wheelbarrow_eng_1",
                    },
                },
            },
            {
                "abbasid": {
                    "scout": SquadFamilyIdentity("scout", ("unit_scout_1_abb",)),
                },
                "english": {
                    "scout": SquadFamilyIdentity("scout", ("unit_scout_1_eng",)),
                    "spearman": SquadFamilyIdentity(
                        "spearman",
                        ("unit_spearman_1_eng", "unit_spearman_2_eng"),
                    ),
                    "spearman_1": SquadFamilyIdentity(
                        "spearman",
                        ("unit_spearman_1_eng", "unit_spearman_2_eng"),
                    ),
                    "spearman_2": SquadFamilyIdentity(
                        "spearman",
                        ("unit_spearman_1_eng", "unit_spearman_2_eng"),
                    ),
                    "siege_tank_2": SquadFamilyIdentity(
                        "siege_tank_2",
                        ("unit_siege_tank_2_eng",),
                    ),
                    "villager": SquadFamilyIdentity(
                        "villager",
                        ("unit_villager_1_eng", "unit_villager_2_eng"),
                    ),
                    "villager_2": SquadFamilyIdentity(
                        "villager",
                        ("unit_villager_1_eng", "unit_villager_2_eng"),
                    ),
                },
            },
        )

    def write(self, directory: Path, name: str, content: str) -> None:
        (directory / name).parent.mkdir(parents=True, exist_ok=True)
        (directory / name).write_text(content, encoding="utf-8")

    def compile(self, files: dict[str, str], identities=None) -> Catalog:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            for name, content in files.items():
                self.write(directory, name, content)
            return compile_directory(directory, identities=identities or self.identities)

    def compile_age(self, civ: str, identifier: str) -> CheckDescriptor:
        catalog = self.compile({
            "age.yaml": f"civ: {civ}\ntitle: Age\nsteps:\n  - age_up: {{id: {identifier}}}\n"
        })
        return catalog.build_orders[0].steps[0].checks[0]

    def test_resolves_each_check_category_to_canonical_payload(self) -> None:
        catalog = self.compile({"order.yaml": """civ: english
title: IDs
steps:
  - built: [{id: town_center}]
    produce: [{id: scout}]
    units: [{id: scout}]
    upgrades: [{id: wheelbarrow}]
    age_up: {id: council_hall}
"""}, identities=self.identities)
        payloads = [check.payload for check in catalog.build_orders[0].steps[0].checks]
        self.assertEqual(payloads[0]["id"], "building_town_center_eng")
        self.assertEqual(payloads[1]["ids"], ["unit_scout_1_eng"])
        self.assertEqual(payloads[2]["ids"], ["unit_scout_1_eng"])
        self.assertEqual(payloads[3]["id"], "upgrade_wheelbarrow_eng")
        self.assertEqual(payloads[4]["id"], "building_landmark_age2_eng")

    def test_age_up_category_depends_on_civilization(self) -> None:
        english = self.compile_age("english", "council_hall")
        abbasid = self.compile_age("abbasid", "economic_wing")
        self.assertEqual(english.payload["id"], "building_landmark_age2_eng")
        self.assertEqual(abbasid.payload["id"], "upgrade_add_economy_wing")

    def test_resolves_oneof_in_order_and_preserves_human_readable_title(self) -> None:
        check = self.compile({"order.yaml": """civ: english
title: Choice
steps:
  - built: [{oneof: [stable, archery_range]}]
"""}).build_orders[0].steps[0].checks[0]
        self.assertEqual(
            check.payload["oneof"],
            ["building_stable_eng", "building_archery_range_eng"],
        )
        self.assertEqual(check.title, "Built: stable or archery range")

    def test_family_ids_drive_squad_titles_and_payloads(self) -> None:
        checks = self.compile({"order.yaml": """civ: english
title: Readable IDs
steps:
  - built: [{id: palace_of_swabia_3}]
    age_up: {id: council_hall_2}
    upgrades: [{id: wheelbarrow_1, queued: true}]
    produce: [{id: villager_2, count: 2, constant: true, queued: true}]
    units: [{id: spearman_2, count: 3}]
"""}).build_orders[0].steps[0].checks

        self.assertEqual(
            [check.title for check in checks],
            [
                "Built: palace of swabia 3",
                "Age Up: council hall 2",
                "wheelbarrow 1",
                "Constantly produce villager",
                "Have 3 spearman active",
            ],
        )
        self.assertEqual(
            [check.payload["id"] for check in checks[:3]],
            [
                "building_landmark_age4_eng_3",
                "building_landmark_age2_eng_2",
                "upgrade_wheelbarrow_eng_1",
            ],
        )
        self.assertEqual(
            checks[3].payload["ids"],
            ["unit_villager_1_eng", "unit_villager_2_eng"],
        )
        self.assertEqual(
            checks[4].payload["ids"],
            ["unit_spearman_1_eng", "unit_spearman_2_eng"],
        )

    def test_compiles_family_and_legacy_squad_aliases_to_the_same_payloads(self) -> None:
        checks = self.compile({"order.yaml": """civ: english
title: Spearmen
steps:
  - produce:
      - {id: spearman, count: 2, constant: false, queued: true}
      - {id: spearman_1, count: 2, constant: false, queued: true}
    units:
      - {id: spearman, count: 2}
      - {id: spearman_2, count: 2}
"""}).build_orders[0].steps[0].checks
        expected_produce_payload = {
            "ids": ["unit_spearman_1_eng", "unit_spearman_2_eng"],
            "count": 2,
            "constant": False,
            "queued": True,
        }
        expected_units_payload = {
            "ids": ["unit_spearman_1_eng", "unit_spearman_2_eng"],
            "count": 2,
        }
        self.assertEqual(checks[0].payload, expected_produce_payload)
        self.assertEqual(checks[1].payload, expected_produce_payload)
        self.assertEqual(checks[2].payload, expected_units_payload)
        self.assertEqual(checks[3].payload, expected_units_payload)
        self.assertEqual(
            [check.title for check in checks],
            ["Queue 2 spearmen", "Queue 2 spearmen", "Have 2 spearman active", "Have 2 spearman active"],
        )

    def test_produce_title_retains_numeric_family_id_suffix(self) -> None:
        check = self.compile({"order.yaml": """civ: english
title: Numeric family
steps:
  - produce: [{id: siege_tank_2, queued: true}]
"""}).build_orders[0].steps[0].checks[0]

        self.assertEqual(check.title, "Queue 1 siege tank 2")

    def test_rejects_capability_and_reports_catalog_context(self) -> None:
        self.assert_invalid(
            "civ: english\ntitle: x\nsteps:\n  - age_up: {id: council_hall, capability: landmark}\n",
            "steps[0].age_up.capability: unknown field",
        )

    def test_reports_exact_squad_family_identity_error_paths(self) -> None:
        self.assert_invalid_exact(
            "civ: english\ntitle: x\nsteps:\n  - produce: [{id: economic_wing}]\n",
            "file.yaml: steps[0].produce[0].id: civilization 'english', produce check, "
            "expected squad ID 'economic_wing': unknown squad ID 'economic_wing' "
            "for civilization 'english'",
        )
        self.assert_invalid_exact(
            "civ: english\ntitle: x\nsteps:\n  - units: [{id: economic_wing}]\n",
            "file.yaml: steps[0].units[0].id: civilization 'english', units check, "
            "expected squad ID 'economic_wing': unknown squad ID 'economic_wing' "
            "for civilization 'english'",
        )

    def test_reports_exact_second_oneof_identity_error_path(self) -> None:
        self.assert_invalid_exact(
            "civ: english\ntitle: x\nsteps:\n  - built: [{oneof: [stable, economic_wing]}]\n",
            "file.yaml: steps[0].built[0].oneof[1]: civilization 'english', "
            "built check, expected entity ID 'economic_wing': unknown entity ID "
            "'economic_wing' for civilization 'english'",
        )

    def test_compiles_single_mapping_with_canonical_immutable_model(self) -> None:
        catalog = self.compile({"opening.yaml": """civ: English\ntitle: 2 TC\nsteps:\n  - title: Opening\n    vils:\n      food: 7\n"""})
        self.assertEqual(catalog, Catalog((BuildOrder("english-2-tc", "English", "2 TC", (Step("Opening", (CheckDescriptor("vils", "7 food", False, {"food": 7}),)),)),)))
        with self.assertRaises(Exception):
            catalog.build_orders[0].title = "changed"

    def test_vils_mapping_compiles_one_canonical_reversible_descriptor(self) -> None:
        catalog = self.compile({"opening.yaml": """civ: English
title: Villager split
steps:
  - vils: {stone: 2, wood: 4, gold: 3, food: 7}
"""})
        checks = catalog.build_orders[0].steps[0].checks
        self.assertEqual(
            checks,
            (
                CheckDescriptor(
                    "vils",
                    "7 food | 3 gold | 4 wood | 2 stone",
                    False,
                    {"food": 7, "gold": 3, "wood": 4, "stone": 2},
                ),
            ),
        )

    def test_compiles_list_documents_yaml_and_yml_in_sorted_file_order(self) -> None:
        catalog = self.compile({
            "zeta.yml": "- civ: French\n  title: Second\n  steps:\n    - hints: [last]\n",
            "alpha.yaml": "- civ: English\n  title: First\n  steps:\n    - hints: [first]\n- civ: Rus\n  title: Third\n  steps:\n    - hints: [third]\n",
        })
        self.assertEqual([item.id for item in catalog.build_orders], ["english-first", "rus-third", "french-second"])

    def test_preserves_step_check_and_list_order_and_expands_mapping_checks(self) -> None:
        catalog = self.compile({"order.yaml": """civ: English\ntitle: Order\nsteps:\n  - resources:\n      wood: 400\n      food: 200\n    hints: [first, second]\n"""})
        checks = catalog.build_orders[0].steps[0].checks
        self.assertEqual([(check.kind, check.payload) for check in checks], [("resources", {"resource": "wood", "count": 400}), ("resources", {"resource": "food", "count": 200}), ("hints", {"text": "first"}), ("hints", {"text": "second"})])

    def test_supports_all_documented_check_shapes(self) -> None:
        catalog = self.compile({"all.yaml": """civ: English\ntitle: All\nsteps:\n  - vils: {food: 7, no_collect: [gold]}\n    rallypoint: [food, wood]\n    built: [{id: barracks}, {oneof: [archery_range, stable]}]\n    age_up: {oneof: [council_hall, town_center], vils: 4, location: home}\n    upgrades: [{id: wheelbarrow, optional: true}]\n    produce: [{id: villager, count: 2, constant: true, queued: true}]\n    resources: {wood: 400}\n    buildings: [{id: barracks, count: 2}]\n    units: [{id: spearman, count: 3}]\n    hints: [Keep producing]\n"""})
        checks = catalog.build_orders[0].steps[0].checks
        self.assertEqual([check.kind for check in checks], ["vils", "vils", "rallypoint", "rallypoint", "built", "built", "age_up", "upgrades", "produce", "resources", "buildings", "units", "hints"])
        self.assertEqual(checks[1].payload, {"resource": "gold", "no_collect": True})
        self.assertEqual(
            checks[5].payload,
            {
                "oneof": ["building_archery_range_eng", "building_stable_eng"],
                "count": 1,
            },
        )
        self.assertEqual(checks[7].optional, True)

    def test_compiles_extended_built_and_upgrade_fields_with_defaults(self) -> None:
        catalog = self.compile({"extended.yaml": """civ: English
title: Extended
steps:
  - built:
      - id: barracks
        count: 2
        vils: 3
        location: forward
      - oneof: [stable, archery_range]
    upgrades:
      - id: wheelbarrow
        queued: true
      - id: horticulture
"""})
        checks = catalog.build_orders[0].steps[0].checks
        self.assertEqual(
            checks[0].payload,
            {
                "id": "building_barracks_eng",
                "count": 2,
                "vils": 3,
                "location": "forward",
            },
        )
        self.assertEqual(
            checks[1].payload,
            {
                "oneof": ["building_stable_eng", "building_archery_range_eng"],
                "count": 1,
            },
        )
        self.assertEqual(
            checks[2].payload,
            {"id": "upgrade_wheelbarrow_eng", "queued": True},
        )
        self.assertEqual(
            checks[3].payload,
            {"id": "upgrade_horticulture_eng", "queued": False},
        )

    def test_compiles_age_up_presentation_suffixes_in_stable_order(self) -> None:
        catalog = self.compile({"age-up.yaml": """civ: English
title: Age Up
steps:
  - age_up: {oneof: [council_hall, town_center], vils: 4, location: gold}
"""})
        check = catalog.build_orders[0].steps[0].checks[0]
        self.assertEqual(check.title, "Age Up: council hall or town center")
        self.assertFalse(check.optional)
        self.assertEqual(
            check.payload,
            {
                "oneof": ["building_landmark_age2_eng", "building_town_center_eng"],
                "vils": 4,
                "location": "gold",
            },
    def test_formats_built_titles_from_count_choice_and_presentation_hints(self) -> None:
        catalog = self.compile({"built.yaml": """civ: English
title: Built titles
steps:
  - built:
      - id: barracks
      - id: house
        count: 2
      - id: barracks
        count: 2
      - oneof: [stable, archery_range]
      - id: outpost
        count: 2
        vils: 3
        location: wood
"""})
        checks = catalog.build_orders[0].steps[0].checks
        self.assertEqual(
            [check.title for check in checks],
            [
                "Built: barracks",
                "Built: house",
                "Built: barracks",
                "Built: stable or archery range",
                "Built: outpost",
            ],
        )

    def test_rejects_invalid_extended_built_and_upgrade_fields(self) -> None:
        self.assert_invalid("civ: english\ntitle: x\nsteps:\n  - built: [{id: town_center, count: 0}]\n", "file.yaml: steps[0].built[0].count: must be a positive integer")
        self.assert_invalid("civ: english\ntitle: x\nsteps:\n  - built: [{id: town_center, vils: false}]\n", "file.yaml: steps[0].built[0].vils: must be a positive integer")
        self.assert_invalid('civ: english\ntitle: x\nsteps:\n  - built: [{id: town_center, location: ""}]\n', "file.yaml: steps[0].built[0].location: must be a non-empty string")
        self.assert_invalid('civ: english\ntitle: x\nsteps:\n  - upgrades: [{id: wheelbarrow, queued: "yes"}]\n', "file.yaml: steps[0].upgrades[0].queued: must be boolean")

    def test_normalizes_unicode_ids(self) -> None:
        self.assertEqual(normalize_id("Énglish", "2 TC!"), "english-2-tc")

    def assert_invalid(self, yaml: str, fragment: str) -> None:
        with self.assertRaises(BuildOrderValidationError) as caught:
            self.compile({"file.yaml": yaml})
        self.assertIn(fragment, str(caught.exception))

    def assert_invalid_exact(self, yaml: str, message: str) -> None:
        with self.assertRaises(BuildOrderValidationError) as caught:
            self.compile({"file.yaml": yaml})
        self.assertEqual(str(caught.exception), message)

    def test_rejects_invalid_schema_with_precise_paths(self) -> None:
        self.assert_invalid("civ: english\ntitle: x\nsteps:\n  - title: only\n", "file.yaml: steps[0]")
        self.assert_invalid("civ: english\ntitle: x\nsteps:\n  - resources: {iron: 2}\n", "file.yaml: steps[0].resources.iron")
        self.assert_invalid("civ: english\ntitle: x\nsteps:\n  - built: [{id: town_center, oneof: [council_hall]}]\n", "file.yaml: steps[0].built[0]")
        self.assert_invalid("civ: english\ntitle: x\nsteps:\n  - built: [{id: town_center}, {id: 1}]\n", "file.yaml: steps[0].built[1].id")
        self.assert_invalid("civ: english\ntitle: x\nsteps:\n  - units: [{id: scout, count: 0}]\n", "file.yaml: steps[0].units[0].count")
        self.assert_invalid("civ: english\ntitle: x\nunknown: true\nsteps:\n  - hints: [x]\n", "file.yaml: unknown")

    def test_rejects_duplicate_generated_slugs(self) -> None:
        self.assert_invalid("- civ: English\n  title: 2 TC\n  steps: [{hints: [a]}]\n- civ: english\n  title: 2-tc\n  steps: [{hints: [b]}]\n", "duplicate generated id 'english-2-tc'")

    def test_reports_nested_relative_paths_for_schema_and_yaml_errors(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            self.write(directory, "openings/english.yaml", "civ: english\ntitle: x\nsteps:\n  - resources: {iron: 2}\n")
            with self.assertRaises(BuildOrderValidationError) as schema_error:
                compile_directory(directory)
            self.assertIn("openings/english.yaml: steps[0].resources.iron", str(schema_error.exception))
            (directory / "openings/english.yaml").unlink()
            self.write(directory, "openings/malformed.yml", "civ: english\ntitle: [\n")
            with self.assertRaises(BuildOrderValidationError) as yaml_error:
                compile_directory(directory)
            self.assertIn("openings/malformed.yml: invalid YAML", str(yaml_error.exception))

    def test_rejects_unsupported_rallypoint_resources(self) -> None:
        self.assert_invalid("civ: english\ntitle: x\nsteps:\n  - rallypoint: [iron]\n", "file.yaml: steps[0].rallypoint[0]")


if __name__ == "__main__":
    unittest.main()
