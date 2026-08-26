import tempfile
import unittest
from pathlib import Path

from tools.build_orders.compiler import compile_directory


ROOT = Path(__file__).resolve().parents[1]
UPGRADES = ROOT / "assets" / "scar" / "build_orders" / "checks" / "upgrades.scar"


def function_body(source: str, name: str) -> str:
    start = source.index(f"function {name}") if f"function {name}" in source else source.index(f"local function {name}")
    next_function = source.find("\nfunction ", start + 1)
    next_local_function = source.find("\nlocal function ", start + 1)
    endings = [index for index in (next_function, next_local_function) if index != -1]
    return source[start:min(endings) if endings else len(source)]


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

    def test_matching_opponent_or_unrelated_queue_cannot_complete_check(self) -> None:
        scan = function_body(self.source, "Upgrades_HasQueuedResearch")
        self.assertRegex(
            scan,
            r"if entity ~= nil and Entity_GetPlayerOwner\(entity\) == state\.player then"
            r"(?s:.*?)"
            r"if \(itemType == PITEM_Upgrade or itemType == PITEM_PlayerUpgrade\)"
            r"(?s:.*?)and Entity_GetProductionQueueItem\(entity, index\) == state\.upgrade then"
            r"(?s:.*?)return true",
        )
        self.assertIn("return false", scan)

    def test_completed_research_is_fallback_and_queue_scan_is_queued_only(self) -> None:
        complete = function_body(self.source, "Upgrades_TryComplete")
        self.assertIn("Upgrades_IsCompletedResearch(state)", complete)
        self.assertIn("state.queued and Upgrades_HasQueuedResearch(state)", complete)
        self.assertLess(
            complete.index("Upgrades_IsCompletedResearch(state)"),
            complete.index("Upgrades_HasQueuedResearch(state)"),
        )

    def test_duplicate_activation_is_idempotent_for_one_check(self) -> None:
        activate = function_body(self.source, "Upgrades_Activate")
        self.assertIn("if UPGRADES_STATE[check.id] ~= nil then", activate)
        self.assertLess(
            activate.index("if UPGRADES_STATE[check.id] ~= nil then"),
            activate.index("UPGRADES_STATE[check.id] = {"),
        )

    def test_multiple_checks_share_polling_and_late_or_duplicate_calls_are_safe(self) -> None:
        complete = function_body(self.source, "Upgrades_TryComplete")
        poll = function_body(self.source, "Upgrades_Poll")
        deactivate = function_body(self.source, "Upgrades_Deactivate")
        self.assertIn("if state == nil or state.completed then", complete)
        self.assertIn("for _, state in pairs(UPGRADES_STATE) do", poll)
        self.assertIn("if state == nil then", deactivate)
        self.assertIn("if next(UPGRADES_STATE) == nil and UPGRADES_POLLING then", deactivate)


if __name__ == "__main__":
    unittest.main()
