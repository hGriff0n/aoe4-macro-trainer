import tempfile
import unittest
from dataclasses import dataclass
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


@dataclass(frozen=True)
class QueueEntity:
    owner: str
    queue: tuple[tuple[str, str], ...]


@dataclass
class UpgradeCheckState:
    check_id: str
    player: str
    upgrade: str
    queued: bool
    completed: bool = False


class UpgradeHandlerModel:
    """Executable contract for the player-scoped upgrade handler boundary."""

    def __init__(self) -> None:
        self.entities: list[QueueEntity] = []
        self.researched: set[tuple[str, str]] = set()
        self.states: dict[str, UpgradeCheckState] = {}
        self.polling = False
        self.rule_add_count = 0
        self.rule_remove_count = 0

    def activate(self, check_id: str, player: str, upgrade: str, *, queued: bool) -> UpgradeCheckState:
        state = self.states.get(check_id)
        if state is not None:
            return state
        state = UpgradeCheckState(check_id, player, upgrade, queued)
        self.states[check_id] = state
        if not self.polling:
            self.polling = True
            self.rule_add_count += 1
        self._try_complete(state)
        return state

    def deactivate(self, check_id: str) -> None:
        if self.states.pop(check_id, None) is None:
            return
        if not self.states and self.polling:
            self.polling = False
            self.rule_remove_count += 1

    def poll(self) -> None:
        for state in list(self.states.values()):
            self._try_complete(state)

    def is_complete(self, check_id: str) -> bool:
        state = self.states.get(check_id)
        return state is not None and state.completed

    def _try_complete(self, state: UpgradeCheckState) -> None:
        if state.completed:
            return
        if (state.player, state.upgrade) in self.researched or (
            state.queued and self._has_queued_research(state)
        ):
            state.completed = True

    def _has_queued_research(self, state: UpgradeCheckState) -> bool:
        for entity in self.entities:
            if entity.owner != state.player:
                continue
            for item_type, upgrade in entity.queue:
                if item_type in {"PITEM_Upgrade", "PITEM_PlayerUpgrade"} and upgrade == state.upgrade:
                    return True
        return False


class BuildOrderUpgradeBehaviorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.model = UpgradeHandlerModel()

    def test_matching_opponent_queue_is_rejected(self) -> None:
        self.model.entities = [QueueEntity("opponent", (("PITEM_Upgrade", "wheelbarrow"),))]
        self.model.activate("queued", "human", "wheelbarrow", queued=True)

        self.assertFalse(self.model.is_complete("queued"))

    def test_unrelated_queue_type_or_upgrade_is_rejected(self) -> None:
        self.model.entities = [
            QueueEntity("human", (("PITEM_Spawn", "wheelbarrow"),)),
            QueueEntity("human", (("PITEM_Upgrade", "horticulture"),)),
        ]
        self.model.activate("queued", "human", "wheelbarrow", queued=True)

        self.assertFalse(self.model.is_complete("queued"))

    def test_completed_research_is_permitted_fallback(self) -> None:
        self.model.researched.add(("human", "wheelbarrow"))
        self.model.activate("completed", "human", "wheelbarrow", queued=False)

        self.assertTrue(self.model.is_complete("completed"))

    def test_queued_check_requires_matching_human_owned_entity_queue(self) -> None:
        self.model.entities = [QueueEntity("human", (("PITEM_PlayerUpgrade", "wheelbarrow"),))]
        self.model.activate("queued", "human", "wheelbarrow", queued=True)

        self.assertTrue(self.model.is_complete("queued"))

    def test_duplicate_activation_does_not_replace_live_state(self) -> None:
        first = self.model.activate("upgrade", "human", "wheelbarrow", queued=True)
        second = self.model.activate("upgrade", "opponent", "horticulture", queued=False)

        self.assertIs(first, second)
        self.assertEqual((second.player, second.upgrade, second.queued), ("human", "wheelbarrow", True))
        self.assertEqual(self.model.rule_add_count, 1)

    def test_repeated_deactivation_and_late_poll_cannot_complete_removed_check(self) -> None:
        self.model.activate("queued", "human", "wheelbarrow", queued=True)
        self.model.deactivate("queued")
        self.model.deactivate("queued")
        self.model.researched.add(("human", "wheelbarrow"))
        self.model.poll()

        self.assertFalse(self.model.is_complete("queued"))
        self.assertEqual(self.model.rule_remove_count, 1)

    def test_two_active_check_ids_coexist_independently(self) -> None:
        self.model.entities = [QueueEntity("human", (("PITEM_Upgrade", "horticulture"),))]
        self.model.activate("first", "human", "wheelbarrow", queued=True)
        self.model.activate("second", "human", "horticulture", queued=True)

        self.assertFalse(self.model.is_complete("first"))
        self.assertTrue(self.model.is_complete("second"))
        self.model.deactivate("second")
        self.assertTrue(self.model.polling)


if __name__ == "__main__":
    unittest.main()
