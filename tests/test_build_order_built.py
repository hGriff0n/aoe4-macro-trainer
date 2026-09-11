import re
import unittest
from pathlib import Path

from tests.scar_runtime import ScarRuntime


ROOT = Path(__file__).resolve().parents[1]
BUILT_PATH = ROOT / "assets" / "scar" / "build_orders" / "checks" / "built.scar"
LOC = {
    "orJoin": "$dfb5645698a84afb91cf7a2dfb0f4a4e:154",
    "buildOne": "$dfb5645698a84afb91cf7a2dfb0f4a4e:159",
    "buildMany": "$dfb5645698a84afb91cf7a2dfb0f4a4e:160",
}


def formatter_runtime(source: str) -> tuple[ScarRuntime, list[tuple[str, tuple[str, ...]]]]:
    registration_stub = "function BuildOrder_RegisterHandler(kind, handler)\nend"
    runtime = ScarRuntime(registration_stub + "\n" + source)
    calls = []
    names = {
        "barracks": "Barracks",
        "stable": "Stable",
        "archery_range": "Archery Range",
    }

    def target_names(payload, kind, _context):
        if payload["oneof"] is not None:
            ids = tuple(payload["oneof"].array())
            calls.append((kind, ids))
            return (LOC["orJoin"], *(names[value] for value in ids))
        calls.append((kind, (payload["id"],)))
        return names[payload["id"]]

    runtime.globals["BuildOrder_TargetNames"] = target_names
    runtime.globals["Loc_FormatText"] = lambda key, *values: (key, *values)
    runtime.globals["Loc_ConvertNumber"] = lambda value: ("number", value)
    runtime.globals["BUILD_ORDER_LOC_KEYS"] = runtime.table(LOC)
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
        self.assertIn("formatTitle = Built_FormatTitle", self.source)

    def test_formatter_selects_single_counted_and_ordered_oneof_titles(self) -> None:
        runtime, calls = formatter_runtime(self.source)

        single = runtime.call(
            "Built_FormatTitle", {"payload": {"id": "barracks", "count": 1}}, {}
        )
        counted = runtime.call(
            "Built_FormatTitle", {"payload": {"id": "barracks", "count": 2}}, {}
        )
        oneof = runtime.call(
            "Built_FormatTitle",
            {"payload": {"oneof": ["stable", "archery_range"], "count": 1}},
            {},
        )

        self.assertEqual(single, (LOC["buildOne"], "Barracks"))
        self.assertEqual(counted, (LOC["buildMany"], ("number", 2), "Barracks"))
        self.assertEqual(oneof, (LOC["buildOne"], (LOC["orJoin"], "Stable", "Archery Range")))
        self.assertEqual(
            calls,
            [
                ("entity", ("barracks",)),
                ("entity", ("barracks",)),
                ("entity", ("stable", "archery_range")),
            ],
        )

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
        blueprint = "BuildOrder_MatchesAnyBlueprint(state.pbgs, context.pbg)"
        self.assertIn(owner, callback)
        self.assertIn(blueprint, callback)
        self.assertLess(callback.index(owner), callback.index(blueprint))
        self.assertIn("BuildOrder_MatchesAnyBlueprint", self.source)

    def test_completion_event_batches_updates_around_state_traversal(self) -> None:
        callback = function_body(self.source, "Built_OnConstructionComplete")
        self.assertIn("BuildOrder_BeginCheckUpdates()", callback)
        self.assertIn("BuildOrder_EndCheckUpdates()", callback)
        self.assertLess(callback.index("BuildOrder_BeginCheckUpdates()"), callback.index("pairs(BUILT_STATE)"))
        self.assertLess(callback.index("pairs(BUILT_STATE)"), callback.index("BuildOrder_EndCheckUpdates()"))

    def test_resolves_and_compares_the_complete_canonical_pbg_tuple(self) -> None:
        activate = function_body(self.source, "Built_Activate")
        self.assertIn(
            "BuildOrder_ResolvePayloadBlueprints(check.payload, BP_GetEntityBlueprint)",
            activate,
        )

    def test_resolves_entity_blueprints_only_during_activation(self) -> None:
        activate = function_body(self.source, "Built_Activate")
        self.assertIn(
            "pbgs = BuildOrder_ResolvePayloadBlueprints(check.payload, BP_GetEntityBlueprint)",
            activate,
        )

        callback = function_body(self.source, "Built_OnConstructionComplete")
        self.assertNotIn("BP_GetEntityBlueprint", callback)
        self.assertIn("BuildOrder_MatchesAnyBlueprint(state.pbgs, context.pbg)", callback)

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
