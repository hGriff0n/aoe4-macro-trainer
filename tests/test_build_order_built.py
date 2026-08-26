import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILT_PATH = ROOT / "assets" / "scar" / "build_orders" / "checks" / "built.scar"


def function_body(source: str, name: str) -> str:
    match = re.search(
        rf"function {re.escape(name)}\([^)]*\)(.*?)(?=^function |\Z)",
        source,
        re.MULTILINE | re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"missing function {name}")
    return match.group(1)


class BuiltCheckContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = BUILT_PATH.read_text(encoding="utf-8")

    def test_registers_a_latched_per_check_handler(self) -> None:
        self.assertIn('BuildOrder_RegisterHandler("built", {', self.source)
        activate = function_body(self.source, "Built_Activate")
        self.assertIn("context.localPlayer", activate)
        self.assertIn("BUILT_STATE[check.id]", activate)
        self.assertIn("remaining = check.payload.count", activate)
        self.assertIn("seen = {}", activate)

    def test_checks_owner_before_blueprint_and_accepts_id_or_oneof(self) -> None:
        callback = function_body(self.source, "Built_OnConstructionComplete")
        owner = "Entity_GetPlayerOwner(entity) ~= state.player"
        blueprint = "Entity_GetBlueprint(entity)"
        self.assertIn(owner, callback)
        self.assertIn(blueprint, callback)
        self.assertLess(callback.index(owner), callback.index(blueprint))
        matcher = function_body(self.source, "Built_Matches")
        self.assertIn("state.payload.id", matcher)
        self.assertIn("state.payload.oneof", matcher)
        self.assertIn("ipairs(state.payload.oneof)", matcher)

    def test_only_matching_human_completed_buildings_decrement_and_latch(self) -> None:
        callback = function_body(self.source, "Built_OnConstructionComplete")
        self.assertIn("state.remaining = state.remaining - 1", callback)
        self.assertIn("if state.remaining == 0 then", callback)
        self.assertIn("BuildOrder_SetCheckComplete(checkID, true)", callback)
        self.assertIn("if state == nil or state.remaining == 0 then", callback)

        scan = function_body(self.source, "Built_ScanEntity")
        self.assertIn("Entity_IsBuilding(entity)", scan)
        self.assertIn("Entity_GetBuildingProgress(entity) >= 1.0", scan)
        self.assertIn("state.seen[entityID] ~= true", scan)
        self.assertIn("Built_OnConstructionComplete(checkID, entity)", scan)

    def test_scans_only_the_stored_player_entities_and_unregisters_idempotently(self) -> None:
        update = function_body(self.source, "Built_Update")
        self.assertIn("Player_GetEntities(state.player)", update)
        self.assertIn("EGroup_ForEach", update)

        deactivate = function_body(self.source, "Built_Deactivate")
        self.assertIn("if state == nil then", deactivate)
        self.assertIn("BUILT_STATE[check.id] = nil", deactivate)
        self.assertIn("if next(BUILT_STATE) == nil then", deactivate)
        self.assertIn("Rule_Remove(Built_Update)", deactivate)


if __name__ == "__main__":
    unittest.main()
