import copy
import unittest

from tools.build_orders import compiler
from tests.test_build_order_importer import OVERLAY_BUILD


class BuildOrderNoteExtractorTests(unittest.TestCase):
    def translate_notes(self, *notes: str, civilization: str = "English"):
        document = copy.deepcopy(OVERLAY_BUILD)
        document["civilization"] = civilization
        document["build_order"][0]["notes"] = []
        document["build_order"][1]["notes"] = list(notes)
        return compiler.translate_overlay_document(document, "fixture.bo")

    def test_extracts_unconditional_building_completion_with_provenance(self) -> None:
        document = copy.deepcopy(OVERLAY_BUILD)
        document["civilization"] = "English"
        document["build_order"][0]["notes"] = []
        document["build_order"][1]["notes"] = [
            "Build 2 @building_military/barracks.webp@"
        ]

        translated = compiler.translate_overlay_document(document, "fixture.bo")

        self.assertEqual(
            translated["steps"][1],
            {
                "built": [{"id": "barracks", "count": 2}],
                "hints": ["Build 2 Barracks"],
            },
        )
        self.assertEqual(
            translated["import_metadata"]["extractions"],
            [
                {
                    "source_step": 1,
                    "source_note": 0,
                    "span": [0, 41],
                    "rule": "built.imperative.v1",
                    "target": "steps[1].built[0]",
                }
            ],
        )

    def test_second_building_means_one_new_completion_not_count_two(self) -> None:
        translated = self.translate_notes(
            "Build a second @building_economy/town-center.webp@"
        )

        self.assertEqual(
            translated["steps"][1]["built"],
            [{"id": "town_center"}],
        )

    def test_extracts_train_have_research_and_queued_research_rules(self) -> None:
        translated = self.translate_notes(
            "Train 3 @unit_infantry/spearman.webp@",
            "Have 4 @unit_ranged/longbowman.webp@",
            "Have 2 @building_military/barracks.webp@",
            "Research @technology_economy/wheelbarrow.webp@",
            "Queue research @technology_economy/textiles.webp@",
        )

        self.assertEqual(
            translated["steps"][1],
            {
                "produce": [{"id": "spearman", "count": 3}],
                "units": [{"id": "longbowman", "count": 4}],
                "buildings": [{"id": "barracks", "count": 2}],
                "upgrades": [
                    {"id": "wheelbarrow"},
                    {"id": "textiles", "queued": True},
                ],
                "hints": [
                    "Train 3 Spearman",
                    "Have 4 Longbowman",
                    "Have 2 Barracks",
                    "Research Wheelbarrow",
                    "Queue research Textiles",
                ],
            },
        )

    def test_extracts_rally_target_and_normalizes_food_sources(self) -> None:
        translated = self.translate_notes(
            "@resource/rally.webp@ -> @resource/resource_gold.webp@",
            "Rally -> @resource/sheep.webp@",
        )

        self.assertEqual(
            translated["steps"][1]["rallypoint"],
            ["gold", "food"],
        )

    def test_splits_resource_threshold_from_trailing_action(self) -> None:
        translated = self.translate_notes(
            "At 400 @resource/resource_wood.webp@, build a second "
            "@building_economy/town-center.webp@"
        )

        self.assertEqual(
            translated["steps"],
            [
                {
                    "title": "0:00",
                    "vils": {"food": 6},
                },
                {"resources": {"wood": 400}},
                {
                    "built": [{"id": "town_center"}],
                    "hints": [
                        "At 400 Wood, build a second Town Center"
                    ],
                },
            ],
        )
        self.assertEqual(
            [item["rule"] for item in translated["import_metadata"]["extractions"]],
            ["resources.threshold.v1", "built.imperative.v1"],
        )

    def test_guarded_clause_stays_hint_and_reports_diagnostic(self) -> None:
        translated = self.translate_notes(
            "Build @building_military/barracks.webp@ or "
            "@building_military/stable.webp@ against cavalry"
        )

        self.assertNotIn("built", translated["steps"][1])
        self.assertEqual(
            translated["import_metadata"]["diagnostics"][0]["code"],
            "guarded_clause",
        )

    def test_unknown_and_wrong_civilization_tokens_are_not_extracted(self) -> None:
        translated = self.translate_notes(
            "Build @building_economy/not-a-building.webp@"
        )

        self.assertNotIn("built", translated["steps"][1])
        self.assertEqual(
            translated["import_metadata"]["diagnostics"][0]["code"],
            "unresolved_identity",
        )

    def test_unused_icon_token_is_reported_without_changing_hint(self) -> None:
        translated = self.translate_notes(
            "Consider @building_military/barracks.webp@ later"
        )

        self.assertEqual(
            translated["steps"][1]["hints"],
            ["Consider Barracks later"],
        )
        self.assertEqual(
            translated["import_metadata"]["diagnostics"][0]["code"],
            "unused_token",
        )

    def test_villager_note_corroborates_structured_allocation_without_duplicate(self) -> None:
        document = copy.deepcopy(OVERLAY_BUILD)
        document["civilization"] = "English"
        document["build_order"][0]["notes"] = [
            "6 @unit_worker/villager.webp@ on @resource/sheep.webp@"
        ]
        document["build_order"] = document["build_order"][:1]

        translated = compiler.translate_overlay_document(document, "fixture.bo")

        self.assertEqual(translated["steps"][0]["vils"], {"food": 6})
        self.assertEqual(
            translated["import_metadata"]["extractions"][0]["rule"],
            "vils.corroboration.v1",
        )
        self.assertEqual(
            translated["import_metadata"]["extractions"][0]["target"],
            "steps[0].vils.food",
        )
        self.assertEqual(translated["import_metadata"]["diagnostics"], [])

    def test_conflicting_villager_note_reports_diagnostic_without_overwrite(self) -> None:
        document = copy.deepcopy(OVERLAY_BUILD)
        document["civilization"] = "English"
        document["build_order"][0]["notes"] = [
            "5 @unit_worker/villager.webp@ on @resource/sheep.webp@"
        ]
        document["build_order"] = document["build_order"][:1]

        translated = compiler.translate_overlay_document(document, "fixture.bo")

        self.assertEqual(translated["steps"][0]["vils"], {"food": 6})
        self.assertEqual(
            translated["import_metadata"]["diagnostics"][0]["code"],
            "conflicting_vils",
        )

    def test_malformed_token_is_diagnosed_and_never_extracted(self) -> None:
        translated = self.translate_notes(
            "Build @building_military/barracks.png@"
        )

        self.assertNotIn("built", translated["steps"][1])
        self.assertEqual(
            translated["import_metadata"]["diagnostics"][0]["code"],
            "malformed_token",
        )

    def test_civilization_specific_unit_must_resolve_for_selected_civ(self) -> None:
        translated = self.translate_notes(
            "Train @unit_ranged/longbowman.webp@",
            civilization="French",
        )

        self.assertNotIn("produce", translated["steps"][1])
        self.assertEqual(
            translated["import_metadata"]["diagnostics"][0]["code"],
            "unresolved_identity",
        )

    def test_known_source_identity_exception_resolves_exactly(self) -> None:
        translated = self.translate_notes(
            "Research @technology_templar/safepassage.webp@",
            civilization="Knights Templar",
        )

        self.assertEqual(
            translated["steps"][1]["upgrades"],
            [{"id": "safe_passage"}],
        )

    def test_zero_count_is_diagnosed_instead_of_emitting_invalid_yaml(self) -> None:
        translated = self.translate_notes(
            "Build 0 @building_military/barracks.webp@"
        )

        self.assertNotIn("built", translated["steps"][1])
        self.assertEqual(
            translated["import_metadata"]["diagnostics"][0]["code"],
            "invalid_count",
        )

    def test_second_threshold_in_source_step_is_left_for_review(self) -> None:
        translated = self.translate_notes(
            "At 400 @resource/resource_wood.webp@, build "
            "@building_military/barracks.webp@",
            "At 200 @resource/resource_wood.webp@, build "
            "@building_military/stable.webp@",
        )

        self.assertEqual(translated["steps"][1], {"resources": {"wood": 400}})
        self.assertEqual(
            translated["steps"][2]["built"],
            [{"id": "barracks"}],
        )
        self.assertEqual(
            translated["import_metadata"]["diagnostics"][0]["code"],
            "conflicting_threshold",
        )

    def test_unsafe_threshold_actions_never_emit_blocking_checks(self) -> None:
        notes = (
            "At 400 @resource/resource_wood.webp@, build "
            "@building_military/barracks.webp@ / @building_military/stable.webp@",
            "At 400 @resource/resource_wood.webp@, don't build "
            "@building_military/barracks.webp@",
            "At 400 @resource/resource_wood.webp@, build "
            "@building_military/barracks.webp@ vs. cavalry",
            "At 400 @resource/resource_wood.webp@, consider "
            "@building_military/barracks.webp@",
        )
        for note in notes:
            with self.subTest(note=note):
                translated = self.translate_notes(note)
                self.assertNotIn("resources", translated["steps"][1])
                self.assertNotIn("built", translated["steps"][1])

    def test_incomplete_token_shapes_are_diagnosed(self) -> None:
        for note in (
            "Build @building_military/barracks.webp",
            "Build @barracks.webp@",
        ):
            with self.subTest(note=note):
                translated = self.translate_notes(note)
                self.assertEqual(
                    translated["import_metadata"]["diagnostics"][0]["code"],
                    "malformed_token",
                )


if __name__ == "__main__":
    unittest.main()
