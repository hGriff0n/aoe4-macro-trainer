import unittest
from pathlib import Path

from tools.build_orders.compiler import compile_directory


ROOT = Path(__file__).resolve().parents[1]
AGE_UP_HANDLER = ROOT / "assets" / "scar" / "build_orders" / "checks" / "age_up.scar"


class AgeUpCompilerTests(unittest.TestCase):
    def compile_check(self, check: str, civ: str = "English"):
        directory = ROOT / "tests" / "fixtures" / "build_orders" / "age_up"
        directory.mkdir(parents=True, exist_ok=True)
        fixture = directory / "age_up.yaml"
        self.addCleanup(fixture.unlink, missing_ok=True)
        self.addCleanup(lambda: directory.rmdir() if directory.exists() and not any(directory.iterdir()) else None)
        fixture.write_text(
            f"civ: {civ}\n"
            "title: Age Up\n"
            "steps:\n"
            f"  - age_up: {check}\n",
            encoding="utf-8",
        )
        return compile_directory(directory).build_orders[0].steps[0].checks[0]

    def test_renders_single_age_up_id(self) -> None:
        check = self.compile_check("{id: council_hall}")
        self.assertEqual(check.title, "Age up: council_hall")
        self.assertFalse(check.optional)
        self.assertEqual(check.payload, {"id": "council_hall"})

    def test_renders_oneof_with_slash_joined_ids(self) -> None:
        check = self.compile_check("{oneof: [council_hall, kings_palace]}")
        self.assertEqual(check.title, "Age up: council_hall / kings_palace")
        self.assertEqual(check.payload, {"oneof": ["council_hall", "kings_palace"]})

    def test_renders_villager_and_location_suffixes_in_order(self) -> None:
        check = self.compile_check("{id: council_hall, vils: 4, location: gold}")
        self.assertEqual(check.title, "Age up: council_hall with 4 vils on gold")
        self.assertEqual(check.payload, {"id": "council_hall", "vils": 4, "location": "gold"})

    def test_marks_golden_horde_non_building_age_up_as_visible_non_blocking_limitation(self) -> None:
        directory = ROOT / "tests" / "fixtures" / "build_orders" / "age_up_golden_horde"
        directory.mkdir(parents=True, exist_ok=True)
        fixture = directory / "age_up.yaml"
        self.addCleanup(fixture.unlink, missing_ok=True)
        self.addCleanup(lambda: directory.rmdir() if directory.exists() and not any(directory.iterdir()) else None)
        fixture.write_text(
            "civ: Golden Horde\n"
            "title: Age Up\n"
            "steps:\n"
            "  - age_up: {id: golden_horde_age_2, capability: non_building}\n",
            encoding="utf-8",
        )
        check = compile_directory(directory).build_orders[0].steps[0].checks[0]
        self.assertTrue(check.optional)
        self.assertEqual(check.title, "Age up: golden_horde_age_2 [unsupported: non-building progress]")

    def test_golden_horde_landmark_id_remains_required_without_capability_override(self) -> None:
        directory = ROOT / "tests" / "fixtures" / "build_orders" / "age_up_golden_horde_landmark"
        directory.mkdir(parents=True, exist_ok=True)
        fixture = directory / "age_up.yaml"
        self.addCleanup(fixture.unlink, missing_ok=True)
        self.addCleanup(lambda: directory.rmdir() if directory.exists() and not any(directory.iterdir()) else None)
        fixture.write_text(
            "civ: Golden Horde\n"
            "title: Age Up\n"
            "steps:\n"
            "  - age_up: {id: golden_horde_landmark}\n",
            encoding="utf-8",
        )
        check = compile_directory(directory).build_orders[0].steps[0].checks[0]
        self.assertFalse(check.optional)
        self.assertEqual(check.title, "Age up: golden_horde_landmark")

    def test_explicit_civilization_capability_scenarios(self) -> None:
        scenarios = (
            ("Knights Templar", "fortress-2", "landmark", False),
            ("Abbasid", "house-of-wisdom-2", "landmark", False),
            ("Golden Horde", "golden_horde_age_2", "non_building", True),
        )
        for civ, identifier, capability, optional in scenarios:
            with self.subTest(civ=civ):
                check = self.compile_check(
                    f"{{id: {identifier}, capability: {capability}}}", civ=civ
                )
                self.assertEqual(check.optional, optional)
                self.assertEqual(check.payload["capability"], capability)


class AgeUpHandlerContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = AGE_UP_HANDLER.read_text(encoding="utf-8")

    def test_registers_a_handler_and_keeps_per_check_state(self) -> None:
        self.assertIn('BuildOrder_RegisterHandler("age_up"', self.source)
        self.assertIn("AGE_UP_STATE[check.id]", self.source)
        self.assertIn("local player = context.localPlayer", self.source)

    def test_landmark_adapter_requires_owned_positive_construction_progress(self) -> None:
        self.assertIn("Player_GetEntities(state.player)", self.source)
        self.assertIn("EGroup_ForEach(entities, AgeUp_CheckLandmarkEntity)", self.source)
        self.assertIn("Entity_GetPlayerOwner(entity) ~= state.player", self.source)
        self.assertIn("Entity_GetBuildingProgress(entity) > 0", self.source)
        self.assertIn("AgeUp_LandmarkProgressStarted", self.source)

    def test_matches_any_configured_id_only_after_human_progress_starts(self) -> None:
        self.assertIn("AgeUp_MatchesID", self.source)
        self.assertIn("payload.oneof", self.source)
        self.assertIn("BuildOrder_SetCheckComplete(state.checkID, true)", self.source)
        self.assertNotIn("Entity_GetProductionQueue", self.source)

    def test_non_building_adapter_is_explicitly_unsupported_and_never_completes(self) -> None:
        self.assertIn("AgeUp_NonBuildingProgressStarted", self.source)
        self.assertIn("No documented player-scoped non-building age-up progress API", self.source)
        self.assertIn("return false", self.source)

    def test_dispatches_each_capability_to_its_matching_adapter(self) -> None:
        self.assertIn('state.payload.capability == "non_building"', self.source)
        self.assertIn("return AgeUp_NonBuildingProgressStarted(state)", self.source)
        self.assertIn("return AgeUp_LandmarkProgressStarted(state)", self.source)

    def test_two_active_checks_share_polling_but_keep_independent_state(self) -> None:
        self.assertIn("for _, state in pairs(AGE_UP_STATE) do", self.source)
        self.assertIn("AGE_UP_STATE[check.id] = nil", self.source)
        self.assertIn("if next(AGE_UP_STATE) == nil and AGE_UP_POLLING then", self.source)
        self.assertIn("Rule_Remove(AgeUp_Poll)", self.source)

    def test_deactivation_cleans_up_and_late_polls_ignore_removed_state(self) -> None:
        self.assertIn("AGE_UP_STATE[check.id] = nil", self.source)
        self.assertIn("Rule_Remove(AgeUp_Poll)", self.source)
        self.assertIn("if state == nil or state.completed then", self.source)


if __name__ == "__main__":
    unittest.main()
