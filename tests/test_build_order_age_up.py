import re
import tempfile
import unittest
from pathlib import Path

from tools.build_orders.compiler import BuildOrderValidationError, compile_directory


ROOT = Path(__file__).resolve().parents[1]
AGE_UP_HANDLER = ROOT / "assets" / "scar" / "build_orders" / "checks" / "age_up.scar"
SCAR_ROOT = ROOT / "assets" / "scar"
MAIN_WINCONDITION = SCAR_ROOT / "winconditions" / "Macro Trainer.scar"


def packaged_import_graph(root: Path) -> list[Path]:
    pending = [root]
    visited: list[Path] = []
    imported_edges: list[Path] = []
    while pending:
        source = pending.pop()
        if source in visited:
            continue
        visited.append(source)
        for target in re.findall(r'import\("([^"]+)"\)', source.read_text(encoding="utf-8")):
            imported = SCAR_ROOT / target
            if imported.exists():
                imported_edges.append(imported)
                pending.append(imported)
    return imported_edges


class AgeUpCompilerTests(unittest.TestCase):
    def compile_check(self, check: str, civ: str = "english"):
        with tempfile.TemporaryDirectory() as temp:
            fixture = Path(temp) / "age_up.yaml"
            fixture.write_text(
                f"civ: {civ}\n"
                "title: Age Up\n"
                "steps:\n"
                f"  - age_up: {check}\n",
                encoding="utf-8",
            )
            return compile_directory(Path(temp)).build_orders[0].steps[0].checks[0]

    def test_normalized_age_up_ids_compile_to_canonical_upgrade_ids(self) -> None:
        cases = (
            ("abbasid", "economic_wing", "upgrade_add_economy_wing"),
            ("templar", "knights_hospitaller", "upgrade_age_dark_com_1_tem"),
            ("golden_horde", "khan_and_torguuds", "upgrade_tent_dark_1_khan_mon_ha_gol"),
        )
        for civ, human_id, canonical in cases:
            with self.subTest(civ=civ):
                check = self.compile_check(f"{{id: {human_id}}}", civ=civ)
                self.assertFalse(check.optional)
                self.assertEqual(check.payload, {"id": canonical})

    def test_ayyubid_age_up_uses_upgrade_catalog_category(self) -> None:
        check = self.compile_check("{id: feudal_economic_wing_growth}", civ="ayyubids")
        self.assertEqual(
            check.payload,
            {"id": "upgrade_add_economy_wing_dark_a_abb_ha_01"},
        )

    def test_conventional_age_up_uses_entity_catalog_category(self) -> None:
        check = self.compile_check("{id: council_hall}", civ="english")
        self.assertEqual(
            check.payload,
            {"id": "building_landmark_age1_westminster_hall_eng"},
        )

    def test_rejects_removed_capability_field(self) -> None:
        with self.assertRaisesRegex(BuildOrderValidationError, "age_up.capability: unknown field"):
            self.compile_check("{id: council_hall, capability: landmark}")


class AgeUpHandlerContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = AGE_UP_HANDLER.read_text(encoding="utf-8")

    def test_runtime_dispatches_on_context_civ_without_capability(self) -> None:
        self.assertIn("civ = context.civ", self.source)
        self.assertIn("AgeUp_UsesUpgradeEvent(state.civ)", self.source)
        self.assertNotIn("capability", self.source)

    def test_packaged_wincondition_reaches_age_up_handler_once_after_engine(self) -> None:
        graph = packaged_import_graph(MAIN_WINCONDITION)
        root_source = MAIN_WINCONDITION.read_text(encoding="utf-8")
        engine_import = 'import("build_orders/objective_engine.scar")'
        handler_import = 'import("build_orders/checks/age_up.scar")'
        startup_import = 'import("build_orders/startup.scar")'

        self.assertEqual(graph.count(AGE_UP_HANDLER), 1)
        self.assertEqual(root_source.count(handler_import), 1)
        self.assertLess(root_source.index(engine_import), root_source.index(handler_import))
        self.assertLess(root_source.index(handler_import), root_source.index(startup_import))

    def test_packaged_import_graph_retains_duplicate_transitive_edges(self) -> None:
        global SCAR_ROOT
        with tempfile.TemporaryDirectory() as temp:
            temporary_root = Path(temp)
            root = temporary_root / "root.scar"
            age_handler = temporary_root / "checks" / "age_up.scar"
            root.write_text('import("first.scar")\nimport("second.scar")\n', encoding="utf-8")
            (temporary_root / "first.scar").write_text(
                'import("checks/age_up.scar")\n', encoding="utf-8"
            )
            (temporary_root / "second.scar").write_text(
                'import("checks/age_up.scar")\n', encoding="utf-8"
            )
            age_handler.parent.mkdir()
            age_handler.write_text("", encoding="utf-8")
            original_root = SCAR_ROOT
            try:
                SCAR_ROOT = temporary_root
                graph = packaged_import_graph(root)
            finally:
                SCAR_ROOT = original_root

        self.assertEqual(graph.count(age_handler), 2)

    def test_upgrade_civilizations_are_explicit(self) -> None:
        for civ in ("abbasid", "ayyubids", "templar", "golden_horde"):
            self.assertIn(f"{civ} = true", self.source)

    def test_activation_caches_pbg_tuples_using_civilization_selected_resolver(self) -> None:
        self.assertIn("AgeUp_ResolvePBGs(check.payload, civ)", self.source)
        self.assertIn("pbgs =", self.source)
        self.assertIn("BP_GetUpgradeBlueprint", self.source)
        self.assertIn("BP_GetEntityBlueprint", self.source)
        self.assertNotIn("BP_GetUpgradeBlueprint(state.payload", self.source)
        self.assertNotIn("BP_GetEntityBlueprint(state.payload", self.source)

    def test_construction_start_uses_observed_context_fields_and_filters_human_first(self) -> None:
        self.assertIn("function AgeUp_OnConstructionStart", self.source)
        self.assertIn("function AgeUp_OnUpgradeStart", self.source)
        handler = self.source[
            self.source.index("function AgeUp_OnConstructionStart"):
            self.source.index("function AgeUp_OnUpgradeStart")
        ]
        owner = "context.player ~= state.player"
        identity = "AgeUp_MatchesPBG(state.pbgs, context.pbg)"
        self.assertIn("context.player", handler)
        self.assertIn("context.pbg", handler)
        self.assertIn("context.entity", handler)
        self.assertIn(owner, handler)
        self.assertIn(identity, handler)
        self.assertLess(handler.index(owner), handler.index(identity))

    def test_construction_start_latches_one_foundation_once_by_entity_id(self) -> None:
        self.assertIn("function AgeUp_OnConstructionStart", self.source)
        self.assertIn("function AgeUp_OnUpgradeStart", self.source)
        handler = self.source[
            self.source.index("function AgeUp_OnConstructionStart"):
            self.source.index("function AgeUp_OnUpgradeStart")
        ]
        self.assertIn("context.entity.EntityID", handler)
        self.assertIn("state.seenFoundations", handler)
        self.assertIn("state.seenFoundations[entityID]", handler)

    def test_upgrade_start_uses_upgrade_context_and_filters_human_first(self) -> None:
        self.assertIn("function AgeUp_OnUpgradeStart", self.source)
        handler = self.source[self.source.index("function AgeUp_OnUpgradeStart"):]
        owner = "owner ~= state.player"
        identity = "AgeUp_MatchesPBG(state.pbgs, context.upgrade)"
        self.assertIn("context.upgrade", handler)
        self.assertNotIn("context.pbg", handler)
        self.assertIn(owner, handler)
        self.assertIn(identity, handler)
        self.assertLess(handler.index(owner), handler.index(identity))

    def test_upgrade_executor_resolver_accepts_direct_player_shape(self) -> None:
        self.assertIn("function AgeUp_OnUpgradeStart", self.source)
        resolver = self.source[
            self.source.index("function AgeUp_GetExecuterOwner"):
            self.source.index("function AgeUp_OnUpgradeStart")
        ]
        self.assertIn("context.executer.PlayerID ~= nil", resolver)
        self.assertIn("return context.executer", resolver)

    def test_upgrade_executor_resolver_accepts_entity_shape(self) -> None:
        self.assertIn("function AgeUp_OnUpgradeStart", self.source)
        resolver = self.source[
            self.source.index("function AgeUp_GetExecuterOwner"):
            self.source.index("function AgeUp_OnUpgradeStart")
        ]
        self.assertIn("context.executer.EntityID ~= nil", resolver)
        self.assertIn("return Entity_GetPlayerOwner(context.executer)", resolver)

    def test_upgrade_callback_rejects_opponent_executor_before_identity_match(self) -> None:
        self.assertIn("function AgeUp_OnUpgradeStart", self.source)
        handler = self.source[self.source.index("function AgeUp_OnUpgradeStart"):]
        self.assertIn("local owner = AgeUp_GetExecuterOwner(context)", handler)
        self.assertIn("if owner ~= state.player then", handler)
        self.assertLess(
            handler.index("if owner ~= state.player then"),
            handler.index("AgeUp_MatchesPBG(state.pbgs, context.upgrade)"),
        )

    def test_baselines_are_player_scoped(self) -> None:
        self.assertIn("Player_HasUpgrade(state.player, pbg)", self.source)
        self.assertIn("Player_GetEntities(state.player)", self.source)
        self.assertIn("Entity_GetPlayerOwner(entity) ~= state.player", self.source)

    def test_registers_only_needed_events_and_removes_last_listener(self) -> None:
        self.assertIn("Rule_AddGlobalEvent(AgeUp_OnConstructionStart, GE_ConstructionStart)", self.source)
        self.assertIn("Rule_AddGlobalEvent(AgeUp_OnUpgradeStart, GE_UpgradeStart)", self.source)
        self.assertIn("Rule_RemoveGlobalEvent(AgeUp_OnConstructionStart)", self.source)
        self.assertIn("Rule_RemoveGlobalEvent(AgeUp_OnUpgradeStart)", self.source)
        self.assertNotIn("GE_ConstructionWorkerStart", self.source)
        self.assertNotIn("GE_ConstructionComplete", self.source)
        self.assertNotIn("GE_UpgradeComplete", self.source)

    def test_unsupported_civilization_logs_and_remains_incomplete(self) -> None:
        self.assertIn("AgeUp: unsupported civilization", self.source)
        self.assertIn("return nil", self.source)


if __name__ == "__main__":
    unittest.main()
