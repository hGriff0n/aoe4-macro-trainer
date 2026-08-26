import tempfile
import unittest
from pathlib import Path

from tools.build_orders.compiler import compile_directory


ROOT = Path(__file__).resolve().parents[1]
UPGRADES = ROOT / "assets" / "scar" / "build_orders" / "checks" / "upgrades.scar"


class BuildOrderUpgradeCompilerTests(unittest.TestCase):
    def compile(self, yaml: str):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            path = Path(temp) / "order.yaml"
            path.write_text(yaml, encoding="utf-8")
            return compile_directory(path.parent).build_orders[0].steps[0].checks

    def test_presents_completed_optional_and_queued_upgrade_checks(self) -> None:
        checks = self.compile("""civ: English
title: Upgrade presentation
steps:
  - upgrades:
      - id: wheelbarrow
      - id: horticulture
        optional: true
      - id: fitted_leatherwork
        queued: true
""")

        self.assertEqual(
            [(check.title, check.optional, check.payload) for check in checks],
            [
                ("Research wheelbarrow", False, {"id": "wheelbarrow", "queued": False}),
                ("[Optional] Research horticulture", True, {"id": "horticulture", "queued": False}),
                ("Queue fitted_leatherwork for research", False, {"id": "fitted_leatherwork", "queued": True}),
            ],
        )


class BuildOrderUpgradeHandlerContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = UPGRADES.read_text(encoding="utf-8")

    def test_registers_upgrade_handler_with_per_check_state(self) -> None:
        self.assertIn('BuildOrder_RegisterHandler("upgrades", {', self.source)
        self.assertIn("UPGRADES_STATE[check.id]", self.source)
        self.assertIn("UPGRADES_STATE[check.id] = nil", self.source)

    def test_completed_research_queries_stored_player_before_canonical_upgrade(self) -> None:
        completed = self.source[self.source.index("local function Upgrades_IsCompletedResearch"):self.source.index("local function Upgrades_HasQueuedResearch")]
        activate = self.source[self.source.index("local function Upgrades_Activate"):self.source.index("local function Upgrades_Deactivate")]
        self.assertIn("local player = context.localPlayer", activate)
        self.assertIn("BP_GetUpgradeBlueprint(check.payload.id)", activate)
        self.assertIn("Player_HasUpgrade(state.player, state.upgrade)", completed)
        self.assertIn("queued = check.payload.queued", activate)

    def test_queued_research_only_scans_producers_owned_by_stored_player(self) -> None:
        scan = self.source[self.source.index("local function Upgrades_HasQueuedResearch"):self.source.index("local function Upgrades_Activate")]
        self.assertIn("Player_GetEntities(state.player)", scan)
        self.assertIn("Entity_GetPlayerOwner(entity) == state.player", scan)
        self.assertIn("Entity_GetProductionQueueSize(entity)", scan)
        self.assertIn("Entity_GetProductionQueueItemType(entity, index)", scan)
        self.assertIn("Entity_GetProductionQueueItem(entity, index) == state.upgrade", scan)
        self.assertIn("PITEM_Upgrade", scan)
        self.assertIn("PITEM_PlayerUpgrade", scan)

    def test_poll_latches_completion_and_cleanup_removes_its_shared_rule(self) -> None:
        self.assertIn("BuildOrder_SetCheckComplete(state.checkID, true)", self.source)
        self.assertIn("Rule_Remove(Upgrades_Poll)", self.source)
        self.assertIn("Rule_Add(Upgrades_Poll)", self.source)
        self.assertIn("for _, state in pairs(UPGRADES_STATE) do", self.source)
        self.assertIn("if state == nil then", self.source)


if __name__ == "__main__":
    unittest.main()
