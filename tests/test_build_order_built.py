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

    def test_registers_only_the_construction_complete_event_once(self) -> None:
        register = function_body(self.source, "Built_EnsureEventRegistered")
        self.assertIn("if BUILT_EVENT_REGISTERED then", register)
        self.assertIn(
            "Rule_AddGlobalEvent(Built_OnConstructionComplete, GE_ConstructionComplete)",
            register,
        )
        self.assertIn("BUILT_EVENT_REGISTERED = true", register)
        self.assertNotIn("GE_ConstructionStart", self.source)
        self.assertNotIn("GE_ConstructionWorkerStart", self.source)
        self.assertNotIn("GE_ConstructionCancelled", self.source)
        self.assertNotIn("GE_EntityKilled", self.source)
        self.assertNotIn("GE_BuildItemComplete", self.source)

    def test_checks_owner_before_blueprint_and_accepts_id_or_oneof(self) -> None:
        callback = function_body(self.source, "Built_OnConstructionComplete")
        owner = "context.player == state.player"
        blueprint = "Built_MatchesPBG(state.pbgs, context.pbg)"
        self.assertIn(owner, callback)
        self.assertIn(blueprint, callback)
        self.assertLess(callback.index(owner), callback.index(blueprint))
        matcher = function_body(self.source, "Built_MatchesPBG")
        self.assertIn("ipairs(pbgs)", matcher)

    def test_completion_event_batches_updates_around_state_traversal(self) -> None:
        callback = function_body(self.source, "Built_OnConstructionComplete")
        self.assertIn("BuildOrder_BeginCheckUpdates()", callback)
        self.assertIn("BuildOrder_EndCheckUpdates()", callback)
        self.assertLess(callback.index("BuildOrder_BeginCheckUpdates()"), callback.index("pairs(BUILT_STATE)"))
        self.assertLess(callback.index("pairs(BUILT_STATE)"), callback.index("BuildOrder_EndCheckUpdates()"))

    def test_resolves_and_compares_the_complete_canonical_pbg_tuple(self) -> None:
        resolve = function_body(self.source, "Built_ResolvePBGs")
        self.assertIn("BP_GetEntityBlueprint(payload.id)", resolve)
        self.assertIn("BP_GetEntityBlueprint(candidate)", resolve)

        equal = function_body(self.source, "Built_BlueprintsEqual")
        self.assertIn("PropertyBagGroupID", equal)
        self.assertIn("PropertyBagGroupModPackID", equal)
        self.assertIn("PropertyBagGroupType", equal)

    def test_resolves_entity_blueprints_only_during_activation(self) -> None:
        activate = function_body(self.source, "Built_Activate")
        self.assertIn("pbgs = Built_ResolvePBGs(check.payload)", activate)

        callback = function_body(self.source, "Built_OnConstructionComplete")
        self.assertNotIn("BP_GetEntityBlueprint", callback)
        self.assertIn("Built_MatchesPBG(state.pbgs, context.pbg)", callback)

    def test_only_matching_human_completed_buildings_decrement_and_latch(self) -> None:
        callback = function_body(self.source, "Built_OnConstructionComplete")
        self.assertIn("local entityID = context.entity.EntityID", callback)
        self.assertIn("if state.seen[entityID] ~= true", callback)
        self.assertIn("state.seen[entityID] = true", callback)
        self.assertIn("state.remaining = state.remaining - 1", callback)
        self.assertIn("if state.remaining == 0 then", callback)
        self.assertIn("BuildOrder_SetCheckComplete(checkID, true)", callback)
        self.assertIn("if state ~= nil and state.remaining > 0 then", callback)

    def test_baselines_existing_completed_buildings_without_counting_them(self) -> None:
        snapshot = function_body(self.source, "Built_SnapshotEntity")
        self.assertIn("Entity_GetPlayerOwner(entity) == state.player", snapshot)
        self.assertIn("Entity_IsBuilding(entity)", snapshot)
        self.assertIn("Entity_GetBuildingProgress(entity) >= 1.0", snapshot)
        self.assertIn("state.seen[Entity_GetID(entity)] = true", snapshot)
        self.assertNotIn("Built_OnConstructionComplete", snapshot)

        activate = function_body(self.source, "Built_Activate")
        snapshot_call = "EGroup_ForEach(Player_GetEntities(player), Built_SnapshotEntity)"
        self.assertIn(snapshot_call, activate)
        self.assertLess(activate.index("BUILT_STATE[check.id] = {"), activate.index(snapshot_call))
        self.assertLess(activate.index("Built_EnsureEventRegistered()"), activate.index(snapshot_call))

    def test_deactivation_ignores_late_events_and_is_idempotent(self) -> None:
        deactivate = function_body(self.source, "Built_Deactivate")
        self.assertIn("if state == nil then", deactivate)
        self.assertIn("BUILT_STATE[check.id] = nil", deactivate)
        self.assertIn("if next(BUILT_STATE) == nil and BUILT_EVENT_REGISTERED then", deactivate)
        self.assertIn("Rule_RemoveGlobalEvent(Built_OnConstructionComplete)", deactivate)
        self.assertIn("BUILT_EVENT_REGISTERED = false", deactivate)

        callback = function_body(self.source, "Built_OnConstructionComplete")
        self.assertIn("if state ~= nil and state.remaining > 0 then", callback)
        self.assertNotIn("Built_Update", self.source)
        self.assertNotIn("Rule_Add(", self.source)


if __name__ == "__main__":
    unittest.main()
