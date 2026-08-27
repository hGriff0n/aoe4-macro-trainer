import re
import unittest
from pathlib import Path

from tools.build_orders.compiler import compile_directory


ROOT = Path(__file__).resolve().parents[1]
PRODUCE_HANDLER = ROOT / "assets" / "scar" / "build_orders" / "checks" / "produce.scar"


def function_body(source: str, name: str) -> str:
    match = re.search(
        rf"(?:local )?function {re.escape(name)}\([^)]*\)(.*?)(?=^(?:local )?function |\Z)",
        source,
        re.MULTILINE | re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"missing function {name}")
    return match.group(1)


class ProduceBehaviorHarness:
    """Executable contract model for audited production-completion semantics."""

    def __init__(self) -> None:
        self.active: dict[str, dict[str, object]] = {}

    def activate(
        self,
        check_id: str,
        player: str,
        unit: tuple[int, int, int],
        count: int,
        queued: bool,
    ) -> None:
        self.active[check_id] = {
            "player": player,
            "unit": unit,
            "count": count,
            "queued": queued,
            "remaining": count,
            "seen": set(),
            "completed": False,
        }

    def observe_completion(
        self,
        player: str,
        unit: tuple[int, int, int],
        spawned_squad_id: int,
    ) -> None:
        for state in self.active.values():
            if state["queued"] or state["completed"]:
                continue
            if player != state["player"]:
                continue
            if unit != state["unit"]:
                continue
            seen = state["seen"]
            if spawned_squad_id in seen:
                continue
            seen.add(spawned_squad_id)
            state["remaining"] -= 1
            state["completed"] = state["remaining"] == 0

    def poll_queues(
        self,
        check_id: str,
        entries: list[tuple[str, tuple[int, int, int]]],
    ) -> None:
        state = self.active.get(check_id)
        if state is None or not state["queued"]:
            return
        matching = sum(
            owner == state["player"] and unit == state["unit"]
            for owner, unit in entries
        )
        state["completed"] = matching >= state["count"]

    def deactivate(self, check_id: str) -> None:
        self.active.pop(check_id, None)


class ProduceCompilerTests(unittest.TestCase):
    def compile_checks(self, produce: str):
        directory = ROOT / "tests" / "fixtures" / "build_orders" / "produce"
        directory.mkdir(parents=True, exist_ok=True)
        fixture = directory / "produce.yaml"
        self.addCleanup(fixture.unlink, missing_ok=True)
        self.addCleanup(
            lambda: directory.rmdir()
            if directory.exists() and not any(directory.iterdir())
            else None
        )
        fixture.write_text(
            "civ: English\n"
            "title: Produce\n"
            "steps:\n"
            f"  - produce: {produce}\n",
            encoding="utf-8",
        )
        return compile_directory(directory).build_orders[0].steps[0].checks

    def test_renders_normal_production_with_explicit_defaults(self) -> None:
        check = self.compile_checks("[{id: spearman, count: 3}]")[0]
        self.assertEqual(check.title, "Produce 3 spearman")
        self.assertFalse(check.optional)
        self.assertEqual(
            check.payload,
            {"id": "spearman", "count": 3, "constant": False, "queued": False},
        )

    def test_renders_constant_production_as_an_explicit_non_blocking_limitation(self) -> None:
        check = self.compile_checks("[{id: villager, constant: true}]")[0]
        self.assertEqual(
            check.title,
            "Constantly produce villager [unsupported: continuous production]",
        )
        self.assertTrue(check.optional)
        self.assertEqual(
            check.payload,
            {"id": "villager", "count": 1, "constant": True, "queued": False},
        )

    def test_renders_single_queued_unit(self) -> None:
        check = self.compile_checks("[{id: archer, queued: true}]")[0]
        self.assertEqual(check.title, "Queue archer for production")
        self.assertFalse(check.optional)
        self.assertEqual(
            check.payload,
            {"id": "archer", "count": 1, "constant": False, "queued": True},
        )

    def test_renders_requested_queued_count(self) -> None:
        check = self.compile_checks("[{id: knight, count: 2, queued: true}]")[0]
        self.assertEqual(check.title, "Have 2 knight queued")
        self.assertFalse(check.optional)
        self.assertEqual(
            check.payload,
            {"id": "knight", "count": 2, "constant": False, "queued": True},
        )

    def test_constant_precedes_queued_when_both_flags_are_set(self) -> None:
        check = self.compile_checks("[{id: villager, count: 2, constant: true, queued: true}]")[0]
        self.assertEqual(
            check.title,
            "Constantly produce villager [unsupported: continuous production]",
        )
        self.assertTrue(check.optional)
        self.assertEqual(
            check.payload,
            {"id": "villager", "count": 2, "constant": True, "queued": True},
        )

    def test_produce_defaults_do_not_leak_into_other_counted_check_payloads(self) -> None:
        directory = ROOT / "tests" / "fixtures" / "build_orders" / "produce_payload_isolation"
        directory.mkdir(parents=True, exist_ok=True)
        fixture = directory / "checks.yaml"
        self.addCleanup(fixture.unlink, missing_ok=True)
        self.addCleanup(
            lambda: directory.rmdir()
            if directory.exists() and not any(directory.iterdir())
            else None
        )
        fixture.write_text(
            "civ: English\n"
            "title: Payload isolation\n"
            "steps:\n"
            "  - units: [{id: spearman, count: 2}]\n"
            "    buildings: [{id: barracks, count: 1}]\n",
            encoding="utf-8",
        )
        checks = compile_directory(directory).build_orders[0].steps[0].checks
        self.assertEqual(checks[0].payload, {"id": "spearman", "count": 2})
        self.assertEqual(checks[1].payload, {"id": "barracks", "count": 1})


class ProduceHandlerContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = PRODUCE_HANDLER.read_text(encoding="utf-8")

    def test_registers_per_check_state_for_normal_completion(self) -> None:
        self.assertIn('BuildOrder_RegisterHandler("produce", {', self.source)
        activate = function_body(self.source, "Produce_Activate")
        self.assertIn("context.localPlayer", activate)
        self.assertIn("PRODUCE_STATE[check.id]", activate)
        self.assertIn("BP_GetSquadBlueprint(check.payload.id)", activate)
        self.assertIn("remaining = check.payload.count", activate)
        self.assertIn("seen = {}", activate)
        self.assertNotIn("Player_GetSquads", self.source)
        self.assertNotIn("Produce_ScanNewSquads", self.source)

    def test_registers_only_the_audited_completion_event_once(self) -> None:
        register = function_body(self.source, "Produce_EnsureEventRegistered")
        self.assertIn("if PRODUCE_EVENT_REGISTERED then", register)
        self.assertIn(
            "Rule_AddGlobalEvent(Produce_OnBuildItemComplete, GE_BuildItemComplete)",
            register,
        )
        self.assertIn("PRODUCE_EVENT_REGISTERED = true", register)
        self.assertNotIn("GE_BuildItemStart", self.source)
        self.assertNotIn("GE_BuildItemCancelled", self.source)
        self.assertNotIn("GE_SquadProductionQueue", self.source)
        self.assertNotIn("GE_SquadSpawn", self.source)
        self.assertNotIn("GE_EntitySpawn", self.source)
        self.assertNotIn("GE_Ability", self.source)
        self.assertNotIn("GE_PlayerAddResource", self.source)

    def test_completion_filters_owner_before_full_canonical_identity(self) -> None:
        callback = function_body(self.source, "Produce_OnBuildItemComplete")
        owner = "context.player == state.player"
        identity = "Produce_BlueprintsEqual(state.blueprint, context.pbg)"
        self.assertIn(owner, callback)
        self.assertIn(identity, callback)
        self.assertLess(callback.index(owner), callback.index(identity))

        equal = function_body(self.source, "Produce_BlueprintsEqual")
        self.assertIn("PropertyBagGroupID", equal)
        self.assertIn("PropertyBagGroupModPackID", equal)
        self.assertIn("PropertyBagGroupType", equal)

    def test_completion_deduplicates_spawned_squad_and_latches_at_count(self) -> None:
        callback = function_body(self.source, "Produce_OnBuildItemComplete")
        self.assertIn("local squadID = context.spawnedSquad.SquadID", callback)
        self.assertIn("state.seen[squadID] ~= true", callback)
        self.assertIn("state.seen[squadID] = true", callback)
        self.assertIn("state.remaining = state.remaining - 1", callback)
        self.assertIn("if state.remaining == 0 then", callback)
        self.assertIn("BuildOrder_SetCheckComplete(checkID, true)", callback)

    def test_queued_variant_uses_only_owned_entity_queues(self) -> None:
        queue = function_body(self.source, "Produce_QueueHasCount")
        scan = function_body(self.source, "Produce_ScanQueueEntity")
        owner = "Entity_GetPlayerOwner(entity) ~= state.player"
        blueprint = "Entity_GetProductionQueueItem(entity, index)"
        self.assertIn("Player_GetEntities(state.player)", queue)
        self.assertIn(owner, scan)
        self.assertIn(blueprint, scan)
        self.assertLess(scan.index(owner), scan.index(blueprint))
        self.assertIn("Entity_GetProductionQueueSize(entity)", scan)
        self.assertIn("queueCount >= state.payload.count", queue)

    def test_constant_variant_is_explicitly_unsupported_and_never_completes(self) -> None:
        self.assertNotIn("Produce_ConstantSatisfied", self.source)
        activate = function_body(self.source, "Produce_Activate")
        self.assertIn("if check.payload.constant then", activate)
        self.assertIn("No verified signal or API proves uninterrupted production", activate)
        self.assertIn("return", activate)

    def test_deactivation_is_idempotent_and_late_polls_cannot_complete(self) -> None:
        deactivate = function_body(self.source, "Produce_Deactivate")
        self.assertIn("if state == nil then", deactivate)
        self.assertIn("PRODUCE_STATE[check.id] = nil", deactivate)
        self.assertIn("Produce_UpdateObservers()", deactivate)
        observers = function_body(self.source, "Produce_UpdateObservers")
        self.assertIn("Rule_Remove(Produce_Poll)", observers)
        self.assertIn("Rule_RemoveGlobalEvent(Produce_OnBuildItemComplete)", observers)
        self.assertIn("PRODUCE_EVENT_REGISTERED = false", observers)
        poll = function_body(self.source, "Produce_Poll")
        self.assertIn("for _, state in pairs(PRODUCE_STATE) do", poll)


class ProduceBehaviorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.harness = ProduceBehaviorHarness()

    def test_normal_completion_requires_two_matching_human_products(self) -> None:
        scout = (199733, 0, 1)
        villager = (199747, 0, 1)
        self.harness.activate("normal", "human", villager, 2, queued=False)
        self.harness.observe_completion("opponent", villager, 50046)
        self.harness.observe_completion("human", scout, 50046)
        self.harness.observe_completion("human", villager, 50047)
        self.assertFalse(self.harness.active["normal"]["completed"])
        self.harness.observe_completion("human", villager, 50048)
        self.assertTrue(self.harness.active["normal"]["completed"])

    def test_duplicate_spawned_squad_counts_once_and_full_tuple_must_match(self) -> None:
        villager = (199747, 0, 1)
        self.harness.activate("normal", "human", villager, 2, queued=False)
        self.harness.observe_completion("human", villager, 50047)
        self.harness.observe_completion("human", villager, 50047)
        self.harness.observe_completion("human", (199747, 99, 1), 50048)
        self.assertFalse(self.harness.active["normal"]["completed"])
        self.harness.observe_completion("human", villager, 50048)
        self.assertTrue(self.harness.active["normal"]["completed"])

    def test_queued_check_rejects_opponent_and_unrelated_entries_before_exact_threshold(self) -> None:
        self.harness.activate("queue", "human", (1, 0, 1), 2, queued=True)
        archer = (1, 0, 1)
        spearman = (2, 0, 1)
        self.harness.poll_queues("queue", [("opponent", archer), ("human", spearman), ("human", archer)])
        self.assertFalse(self.harness.active["queue"]["completed"])
        self.harness.poll_queues("queue", [("human", archer), ("human", archer)])
        self.assertTrue(self.harness.active["queue"]["completed"])

    def test_queue_poll_is_idempotent_late_safe_and_multiple_checks_coexist(self) -> None:
        self.harness.activate("archers", "human", (1, 0, 1), 2, queued=True)
        self.harness.activate("spearman", "human", (2, 0, 1), 1, queued=True)
        archer = (1, 0, 1)
        spearman = (2, 0, 1)
        self.harness.poll_queues("archers", [("human", archer), ("human", archer)])
        self.harness.poll_queues("archers", [("human", archer), ("human", archer)])
        self.assertTrue(self.harness.active["archers"]["completed"])
        self.assertFalse(self.harness.active["spearman"]["completed"])
        self.harness.deactivate("archers")
        self.harness.deactivate("archers")
        self.harness.poll_queues("archers", [("human", archer), ("human", archer)])
        self.assertNotIn("archers", self.harness.active)
        self.harness.poll_queues("spearman", [("human", spearman)])
        self.assertTrue(self.harness.active["spearman"]["completed"])


if __name__ == "__main__":
    unittest.main()
