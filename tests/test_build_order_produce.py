import re
import unittest
from pathlib import Path

from tools.build_orders.compiler import _pluralize_unit, compile_directory


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
    """Executable contract model for event-triggered production reconciliation."""

    def __init__(self) -> None:
        self.active: dict[str, dict[str, object]] = {}
        self.entities: dict[str, dict[str, object]] = {}
        self.pending_players: set[str] = set()
        self.next_tick_scheduled = False

    def set_queue(
        self,
        entity: str,
        owner: str,
        entries: list[tuple[int, int, int]],
        has_production_queue: bool = True,
    ) -> None:
        self.entities[entity] = {
            "owner": owner,
            "entries": entries,
            "has_production_queue": has_production_queue,
        }

    def activate(
        self,
        check_id: str,
        player: str,
        units: tuple[int, int, int] | list[tuple[int, int, int]],
        count: int,
        queued: bool,
        constant: bool = False,
    ) -> None:
        if isinstance(units, tuple):
            units = [units]
        self.active[check_id] = {
            "player": player,
            "units": units,
            "count": count,
            "queued": queued,
            "constant": constant,
            "remaining": count,
            "seen": set(),
            "completed": False,
        }
        if queued:
            self.reconcile(player)

    def schedule_reconciliation(self, player: str) -> None:
        self.pending_players.add(player)
        self.next_tick_scheduled = True

    def observe_command(self, entity: str | None) -> None:
        if entity is None:
            return
        source = self.entities.get(entity)
        if source is None or not source["has_production_queue"]:
            return
        owner = source["owner"]
        if any(state["queued"] and state["player"] == owner for state in self.active.values()):
            self.schedule_reconciliation(owner)

    def run_next_tick(self) -> None:
        pending = self.pending_players
        self.pending_players = set()
        self.next_tick_scheduled = False
        for player in pending:
            self.reconcile(player)

    def reconcile(self, player: str) -> None:
        for state in self.active.values():
            if not state["queued"] or state["player"] != player:
                continue
            matching = sum(
                entity["owner"] == player and unit in state["units"]
                for entity in self.entities.values()
                for unit in entity["entries"]
            )
            state["completed"] = matching >= state["count"]

    def observe_completion(
        self,
        player: str,
        unit: tuple[int, int, int],
        spawned_squad_id: int,
    ) -> None:
        for state in self.active.values():
            if state["queued"]:
                if player == state["player"]:
                    self.schedule_reconciliation(player)
                continue
            if state["completed"]:
                continue
            if player != state["player"]:
                continue
            if unit not in state["units"]:
                continue
            seen = state["seen"]
            if spawned_squad_id in seen:
                continue
            seen.add(spawned_squad_id)
            state["remaining"] -= 1
            state["completed"] = state["remaining"] == 0

    def deactivate(self, check_id: str) -> None:
        self.active.pop(check_id, None)


class ProduceCompilerTests(unittest.TestCase):
    def compile_checks(self, produce: str, civ: str = "English"):
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
            f"civ: {civ}\n"
            "title: Produce\n"
            "steps:\n"
            f"  - produce: {produce}\n",
            encoding="utf-8",
        )
        return compile_directory(directory).build_orders[0].steps[0].checks

    def test_renders_normal_production_with_canonical_family_payload(self) -> None:
        check = self.compile_checks("[{id: spearman_2, count: 3}]")[0]
        self.assertEqual(check.title, "Produce 3 spearmen")
        self.assertFalse(check.optional)
        self.assertEqual(
            check.payload,
            {
                "ids": ["unit_spearman_2_eng", "unit_spearman_3_eng", "unit_spearman_4_eng"],
                "count": 3,
            },
        )

    def test_renders_constant_production_as_a_non_blocking_author_hint(self) -> None:
        check = self.compile_checks("[{id: villager, constant: true}]")[0]
        self.assertEqual(
            check.title,
            "Constantly produce villager",
        )
        self.assertTrue(check.optional)
        self.assertEqual(
            check.payload,
            {"ids": ["unit_villager_1_nomad_eng"], "count": 1, "constant": True},
        )

    def test_renders_single_queued_unit(self) -> None:
        check = self.compile_checks("[{id: longbowman_2, queued: true}]")[0]
        self.assertEqual(check.title, "Queue 1 longbowman")
        self.assertFalse(check.optional)
        self.assertEqual(
            check.payload,
            {
                "ids": ["unit_archer_2_eng", "unit_archer_3_eng", "unit_archer_4_eng"],
                "count": 1,
                "queued": True,
            },
        )

    def test_renders_requested_queued_count(self) -> None:
        check = self.compile_checks(
            "[{id: archer_2, count: 2, queued: true}]", civ="Abbasid"
        )[0]
        self.assertEqual(check.title, "Queue 2 archers")
        self.assertFalse(check.optional)
        self.assertEqual(
            check.payload,
            {
                "ids": ["unit_archer_2_abb", "unit_archer_3_abb", "unit_archer_4_abb"],
                "count": 2,
                "queued": True,
            },
        )

    def test_queue_title_uses_catalog_safe_plural_display_names(self) -> None:
        cases = (
            ("Ottomans", "janissary_3", "Queue 2 janissaries"),
            ("Golden Horde", "shaman", "Queue 2 shamans"),
            ("English", "man_at_arms_2", "Queue 2 men at arms"),
        )

        for civilization, unit, expected_title in cases:
            with self.subTest(unit=unit):
                check = self.compile_checks(
                    f"[{{id: {unit}, count: 2, queued: true}}]", civ=civilization
                )[0]
                self.assertEqual(check.title, expected_title)

    def test_safe_pluralization_does_not_corrupt_family_labels(self) -> None:
        expected_plurals = {
            "archer": "archers",
            "spearman": "spearmen",
            "gilded man at arms": "gilded men at arms",
            "janissary": "janissaries",
            "shaman": "shamans",
            "wynguard footmen": "wynguard footmen",
            "wynguard raiders": "wynguard raiders",
            "landsknecht mercenaries": "landsknecht mercenaries",
            "nest of bees": "nest of bees",
            "clocktower nest of bees": "clocktower nest of bees",
            "samurai": "samurai",
            "streltsy": "streltsy",
        }

        for unit, expected_plural in expected_plurals.items():
            with self.subTest(unit=unit):
                self.assertEqual(_pluralize_unit(unit), expected_plural)

    def test_constant_precedes_queued_when_both_flags_are_set(self) -> None:
        check = self.compile_checks("[{id: villager, count: 2, constant: true, queued: true}]")[0]
        self.assertEqual(
            check.title,
            "Constantly produce villager",
        )
        self.assertTrue(check.optional)
        self.assertEqual(
            check.payload,
            {"ids": ["unit_villager_1_nomad_eng"], "count": 2, "constant": True, "queued": True},
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
            "  - units: [{id: spearman_2, count: 2}]\n"
            "    buildings: [{id: barracks, count: 1}]\n",
            encoding="utf-8",
        )
        checks = compile_directory(directory).build_orders[0].steps[0].checks
        self.assertEqual(
            checks[0].payload,
            {"ids": ["unit_spearman_2_eng", "unit_spearman_3_eng", "unit_spearman_4_eng"], "count": 2},
        )
        self.assertEqual(checks[1].payload, {"id": "building_unit_infantry_control_eng", "count": 1})


class ProduceHandlerContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = PRODUCE_HANDLER.read_text(encoding="utf-8")

    def test_registers_per_check_state_for_normal_completion(self) -> None:
        self.assertIn('BuildOrder_RegisterHandler("produce", {', self.source)
        activate = function_body(self.source, "Produce_Activate")
        self.assertIn("context.localPlayer", activate)
        self.assertIn("PRODUCE_STATE[check.id]", activate)
        self.assertIn("pbgs = Produce_ResolvePBGs(check.payload.ids)", activate)
        self.assertIn("remaining = check.payload.count", activate)
        self.assertIn("seen = {}", activate)
        self.assertNotIn("Player_GetSquads", self.source)
        self.assertNotIn("Produce_ScanNewSquads", self.source)

    def test_resolves_every_family_blueprint_once_at_activation(self) -> None:
        resolver = function_body(self.source, "Produce_ResolvePBGs")
        self.assertIn("for _, id in ipairs(ids) do", resolver)
        self.assertIn("table.insert(pbgs, BP_GetSquadBlueprint(id))", resolver)
        start = self.source.index("function Produce_OnBuildItemComplete")
        end = self.source.index("local function Produce_EnsureCommandEventRegistered", start + 1)
        callback = self.source[start:end]
        self.assertIn("Produce_MatchesPBG(state.pbgs, context.pbg)", callback)
        self.assertNotIn("context.pbg == state.pbgs", callback)
        self.assertNotIn("BP_GetSquadBlueprint", callback)

    def test_registers_only_the_proven_command_and_completion_events_once(self) -> None:
        completion = function_body(self.source, "Produce_EnsureCompletionEventRegistered")
        command = function_body(self.source, "Produce_EnsureCommandEventRegistered")
        self.assertIn("if PRODUCE_COMPLETION_EVENT_REGISTERED then", completion)
        self.assertIn(
            "Rule_AddGlobalEvent(Produce_OnBuildItemComplete, GE_BuildItemComplete)",
            completion,
        )
        self.assertIn("Rule_AddGlobalEvent(Produce_OnEntityCommandIssued, GE_EntityCommandIssued)", command)
        self.assertNotIn("EntityCommandType(3)", self.source)
        self.assertNotIn("EntityCommandType(5)", self.source)
        self.assertNotIn("EntityCommandType(16)", self.source)
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
        identity = "Produce_MatchesPBG(state.pbgs, context.pbg)"
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
        self.assertIn("EGroup_ForEach", queue)
        self.assertIn(owner, scan)
        self.assertIn(blueprint, scan)
        self.assertIn("Produce_MatchesPBG(state.pbgs, Entity_GetProductionQueueItem(entity, index))", scan)
        self.assertLess(scan.index(owner), scan.index(blueprint))
        self.assertIn("Entity_GetProductionQueueSize(entity)", scan)
        self.assertIn("queueCount >= state.payload.count", queue)

    def test_constant_variant_uses_normal_completion_state(self) -> None:
        activate = function_body(self.source, "Produce_Activate")
        self.assertNotIn("check.payload.constant", activate)
        self.assertIn("remaining = check.payload.count", activate)
        self.assertIn("Produce_UpdateObservers()", activate)

    def test_commands_validate_source_owner_before_scheduling_next_tick_reconciliation(self) -> None:
        callback = function_body(self.source, "Produce_OnEntityCommandIssued")
        self.assertIn("context.entity == nil or context.entity.EntityID == nil", callback)
        self.assertIn("Entity_GetPlayerOwner(context.entity)", callback)
        self.assertIn("Entity_HasProductionQueue(context.entity) == false", callback)
        self.assertIn("Produce_ScheduleQueueReconciliation(state.checkID)", callback)
        self.assertLess(
            callback.index("Entity_GetPlayerOwner(context.entity)"),
            callback.index("Produce_ScheduleQueueReconciliation(state.checkID)"),
        )

    def test_completion_reconciles_queued_human_state_without_a_producer_entity(self) -> None:
        callback = function_body(self.source, "Produce_OnBuildItemComplete")
        self.assertIn("context.player == state.player", callback)
        self.assertIn("Produce_ScheduleQueueReconciliation(state.checkID)", callback)
        self.assertLess(
            callback.index("context.player == state.player"),
            callback.index("Produce_ScheduleQueueReconciliation(state.checkID)"),
        )

    def test_queued_reconciliation_is_one_shot_coalesced_and_not_periodic(self) -> None:
        schedule = function_body(self.source, "Produce_ScheduleQueueReconciliation")
        next_tick = function_body(self.source, "Produce_ReconcileQueuedNextTick")
        self.assertIn("PRODUCE_RECOUNT_PENDING[checkID] == true", schedule)
        self.assertNotIn("PRODUCE_RECOUNT_PENDING[player]", schedule)
        self.assertIn("Rule_Add(Produce_ReconcileQueuedNextTick)", schedule)
        self.assertIn("Rule_RemoveMe()", next_tick)
        self.assertIn("PRODUCE_RECOUNT_PENDING = {}", next_tick)
        self.assertIn("pending[state.checkID] == true", next_tick)
        self.assertNotIn("pending[state.player]", next_tick)
        self.assertIn("Produce_QueueHasCount(state)", next_tick)
        self.assertNotIn("Produce_Poll", self.source)
        self.assertNotIn("Rule_Add(Produce_Poll)", self.source)

    def test_deactivation_is_idempotent_and_cleans_mixed_observers(self) -> None:
        deactivate = function_body(self.source, "Produce_Deactivate")
        self.assertIn("if state == nil then", deactivate)
        self.assertIn("PRODUCE_STATE[check.id] = nil", deactivate)
        self.assertIn("Produce_UpdateObservers()", deactivate)
        observers = function_body(self.source, "Produce_UpdateObservers")
        self.assertIn("Rule_Remove(Produce_ReconcileQueuedNextTick)", observers)
        self.assertIn("Rule_RemoveGlobalEvent(Produce_OnEntityCommandIssued)", observers)
        self.assertIn("Rule_RemoveGlobalEvent(Produce_OnBuildItemComplete)", observers)
        self.assertIn("PRODUCE_COMMAND_EVENT_REGISTERED = false", observers)
        self.assertIn("PRODUCE_COMPLETION_EVENT_REGISTERED = false", observers)


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

    def test_constant_author_hint_rejects_opponent_then_completes_on_matching_human_product(self) -> None:
        villager = (199747, 0, 1)
        self.harness.activate(
            "constant-villager",
            "human",
            villager,
            1,
            queued=False,
            constant=True,
        )
        self.harness.observe_completion("opponent", villager, 700)
        self.assertFalse(self.harness.active["constant-villager"]["completed"])
        self.harness.observe_completion("human", villager, 701)
        self.assertTrue(self.harness.active["constant-villager"]["completed"])

    def test_spearman_family_matches_cross_age_queue_and_completion_events(self) -> None:
        dark_age_spearman = (1, 0, 1)
        feudal_spearman = (2, 0, 1)
        castle_spearman = (3, 0, 1)
        archer = (4, 0, 1)
        spearmen = [dark_age_spearman, feudal_spearman, castle_spearman]

        self.harness.set_queue("human-barracks", "human", [dark_age_spearman])
        self.harness.set_queue("opponent-barracks", "opponent", [feudal_spearman])
        self.harness.activate("queued-spearman", "human", spearmen, 1, queued=True)
        self.assertTrue(self.harness.active["queued-spearman"]["completed"])
        self.harness.observe_command("human-barracks")
        self.harness.set_queue("human-barracks", "human", [])
        self.harness.run_next_tick()
        self.assertFalse(self.harness.active["queued-spearman"]["completed"])

        self.harness.activate("completed-spearmen", "human", spearmen, 2, queued=False)
        self.harness.observe_completion("human", archer, 600)
        self.harness.observe_completion("opponent", feudal_spearman, 601)
        self.harness.observe_completion("human", feudal_spearman, 602)
        self.assertFalse(self.harness.active["completed-spearmen"]["completed"])
        self.harness.observe_completion("human", castle_spearman, 603)
        self.assertTrue(self.harness.active["completed-spearmen"]["completed"])

    def test_duplicate_spawned_squad_counts_once_and_full_tuple_must_match(self) -> None:
        villager = (199747, 0, 1)
        self.harness.activate("normal", "human", villager, 2, queued=False)
        self.harness.observe_completion("human", villager, 50047)
        self.harness.observe_completion("human", villager, 50047)
        self.harness.observe_completion("human", (199747, 99, 1), 50048)
        self.assertFalse(self.harness.active["normal"]["completed"])
        self.harness.observe_completion("human", villager, 50048)
        self.assertTrue(self.harness.active["normal"]["completed"])

    def test_activation_baseline_counts_across_multiple_human_producers(self) -> None:
        archer = (1, 0, 1)
        self.harness.set_queue("tc", "human", [archer])
        self.harness.set_queue("barracks", "human", [archer])
        self.harness.set_queue("enemy-tc", "opponent", [archer, archer])
        self.harness.activate("queue", "human", archer, 2, queued=True)
        self.assertTrue(self.harness.active["queue"]["completed"])

    def test_command_reconciles_next_tick_after_sync_pre_mutation_queue_add(self) -> None:
        archer = (1, 0, 1)
        self.harness.set_queue("tc", "human", [])
        self.harness.activate("archers", "human", archer, 1, queued=True)
        self.harness.observe_command("tc")
        self.assertFalse(self.harness.active["archers"]["completed"])
        self.harness.set_queue("tc", "human", [archer])
        self.harness.run_next_tick()
        self.assertTrue(self.harness.active["archers"]["completed"])

    def test_command_reconciles_waiting_item_removal_and_active_cancellation(self) -> None:
        archer = (1, 0, 1)
        self.harness.set_queue("tc", "human", [archer, archer])
        self.harness.activate("archers", "human", archer, 2, queued=True)
        self.harness.observe_command("tc")
        self.harness.set_queue("tc", "human", [archer])
        self.harness.run_next_tick()
        self.assertFalse(self.harness.active["archers"]["completed"])
        self.harness.set_queue("tc", "human", [archer, archer])
        self.harness.reconcile("human")
        self.assertTrue(self.harness.active["archers"]["completed"])
        self.harness.observe_command("tc")
        self.harness.set_queue("tc", "human", [])
        self.harness.run_next_tick()
        self.assertFalse(self.harness.active["archers"]["completed"])

    def test_completion_reconciles_active_item_removal_and_rejects_opponent_completion(self) -> None:
        villager = (199747, 0, 1)
        self.harness.set_queue("tc", "human", [villager])
        self.harness.activate("villagers", "human", villager, 1, queued=True)
        self.assertTrue(self.harness.active["villagers"]["completed"])
        self.harness.observe_completion("opponent", villager, 900)
        self.assertFalse(self.harness.next_tick_scheduled)
        self.harness.observe_completion("human", villager, 901)
        self.harness.set_queue("tc", "human", [])
        self.harness.run_next_tick()
        self.assertFalse(self.harness.active["villagers"]["completed"])

    def test_unrelated_or_opponent_commands_are_harmless(self) -> None:
        archer = (1, 0, 1)
        self.harness.set_queue("barracks", "human", [archer])
        self.harness.set_queue("villager", "human", [], has_production_queue=False)
        self.harness.set_queue("enemy-barracks", "opponent", [archer])
        self.harness.activate("archers", "human", archer, 2, queued=True)
        self.harness.observe_command("villager")
        self.harness.observe_command("enemy-barracks")
        self.assertFalse(self.harness.next_tick_scheduled)

    def test_coalesces_distinct_players_and_deactivation_is_late_safe(self) -> None:
        archer = (1, 0, 1)
        self.harness.set_queue("human-tc", "human", [])
        self.harness.set_queue("ally-tc", "ally", [])
        self.harness.activate("human", "human", archer, 1, queued=True)
        self.harness.activate("ally", "ally", archer, 1, queued=True)
        self.harness.observe_command("human-tc")
        self.harness.observe_command("ally-tc")
        self.assertEqual(self.harness.pending_players, {"human", "ally"})
        self.harness.deactivate("human")
        self.harness.set_queue("ally-tc", "ally", [archer])
        self.harness.run_next_tick()
        self.assertNotIn("human", self.harness.active)
        self.assertTrue(self.harness.active["ally"]["completed"])


if __name__ == "__main__":
    unittest.main()
