import re
import unittest
from pathlib import Path

from tools.build_orders.compiler import compile_directory


ROOT = Path(__file__).resolve().parents[1]
PRODUCE_HANDLER = ROOT / "assets" / "scar" / "build_orders" / "checks" / "produce.scar"


def function_body(source: str, name: str) -> str:
    match = re.search(
        rf"function {re.escape(name)}\([^)]*\)(.*?)(?=^function |\Z)",
        source,
        re.MULTILINE | re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"missing function {name}")
    return match.group(1)


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

    def test_registers_per_check_state_and_scans_human_squads(self) -> None:
        self.assertIn('BuildOrder_RegisterHandler("produce", {', self.source)
        activate = function_body(self.source, "Produce_Activate")
        self.assertIn("context.localPlayer", activate)
        self.assertIn("PRODUCE_STATE[check.id]", activate)
        self.assertIn("remaining = check.payload.count", activate)
        self.assertIn("seen = {}", activate)
        self.assertIn("Player_GetSquads(player)", activate)

    def test_normal_production_checks_owner_before_blueprint_and_counts_only_new_squads(self) -> None:
        scan = function_body(self.source, "Produce_ScanSquad")
        owner = "Squad_GetPlayerOwner(squad) ~= state.player"
        blueprint = "Squad_GetBlueprint(squad)"
        self.assertIn(owner, scan)
        self.assertIn(blueprint, scan)
        self.assertLess(scan.index(owner), scan.index(blueprint))
        self.assertIn("state.seen[squadID] ~= true", scan)
        self.assertIn("Produce_OnCompletedSquad(state.checkID, squad)", scan)

    def test_opponent_or_unrelated_squads_do_not_decrement_the_historical_counter(self) -> None:
        callback = function_body(self.source, "Produce_OnCompletedSquad")
        owner = "Squad_GetPlayerOwner(squad) ~= state.player"
        blueprint = "Squad_GetBlueprint(squad) ~= BP_GetSquadBlueprint(state.payload.id)"
        self.assertIn(owner, callback)
        self.assertIn(blueprint, callback)
        self.assertLess(callback.index(owner), callback.index(blueprint))
        self.assertIn("state.remaining = state.remaining - 1", callback)
        self.assertIn("if state.remaining == 0 then", callback)
        self.assertIn("BuildOrder_SetCheckComplete(checkID, true)", callback)

    def test_duplicate_late_and_baseline_squads_are_ignored(self) -> None:
        callback = function_body(self.source, "Produce_OnCompletedSquad")
        self.assertIn("if state == nil or state.remaining == 0 then", callback)
        snapshot = function_body(self.source, "Produce_SnapshotSquad")
        self.assertIn("local state = PRODUCE_SNAPSHOT_STATE", snapshot)
        self.assertIn("Squad_GetPlayerOwner(squad) ~= state.player", snapshot)
        self.assertIn("state.seen[Squad_GetID(squad)] = true", snapshot)
        self.assertNotIn("Produce_OnCompletedSquad", snapshot)

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
        constant = function_body(self.source, "Produce_ConstantSatisfied")
        self.assertIn("No documented player-scoped API can prove uninterrupted production", constant)
        self.assertIn("return false", constant)
        activate = function_body(self.source, "Produce_Activate")
        self.assertIn("check.payload.queued and check.payload.constant == false", activate)

    def test_deactivation_is_idempotent_and_late_polls_cannot_complete(self) -> None:
        deactivate = function_body(self.source, "Produce_Deactivate")
        self.assertIn("if state == nil then", deactivate)
        self.assertIn("PRODUCE_STATE[check.id] = nil", deactivate)
        self.assertIn("Rule_Remove(Produce_Poll)", deactivate)
        poll = function_body(self.source, "Produce_Poll")
        self.assertIn("for _, state in pairs(PRODUCE_STATE) do", poll)


if __name__ == "__main__":
    unittest.main()
