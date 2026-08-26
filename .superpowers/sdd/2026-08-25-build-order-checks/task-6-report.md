# GRI-59 Upgrade Check Report

## Research evidence

Completed research is queried with the stored `context.localPlayer` handle:

- `BP_GetUpgradeBlueprint(String pbgShortname)` → upgrade property bag; official API: `official_api/Essence_ScarFunctions.api:477`; official usage: `official_scar/cardinal.scar:620`.
- `Player_HasUpgrade(PlayerID pPlayer, ScarUpgradePBG upgradePBG)` → whether that player purchased the upgrade; official API: `official_api/Essence_ScarFunctions.api:1335`; official usage: `official_scar/cardinal.scar:620` and `official_scar/missionomatic/missionomatic_conditionlist.scar:446`.

Queued research is reliably observable only through the stored player’s entity producers:

- `Player_GetEntities(Player& player)` → the player’s entity group; official API: `official_api/Essence_ScarFunctions.api:1284`; official usage: `official_scar/gameplay/chatcheats.scar:333` and `official_scar/player.scar:183`.
- `Entity_GetProductionQueueSize(EntityID entity)` → queue length; official API: `official_api/Essence_ScarFunctions.api:675`.
- `Entity_GetProductionQueueItemType(EntityID entity, Integer index)` → `PITEM_Upgrade` / `PITEM_PlayerUpgrade` classification; official API: `official_api/Essence_ScarFunctions.api:674`; official usage: `official_scar/training/abbasidtrainingconditions.scar:186`.
- `Entity_GetProductionQueueItem(EntityID entity, Integer index)` → queued item PBG; official API: `official_api/Essence_ScarFunctions.api:673`; official usage: `official_scar/missionomatic/missionomatic_utility.scar:1404` and `official_scar/training/abbasidtrainingconditions.scar:187`.
- `Entity_GetPlayerOwner(EntityID entity)` → authoritative owner guard for every entity from the group; official API: `official_api/Essence_ScarFunctions.api:671`.
- `EGroup_GetEntityAt(EGroupID group, Integer index)` is iterated one-based with `EGroup_Count`; official source example: `official_scar/ai/combat_fitness_util.scar:233`.

The handler accepts a queued match only after both the player-scoped entity query and explicit owner equality guard, then compares the queue type and canonical upgrade PBG. It also treats already-completed research as satisfying a queued descriptor, because completion proves the player reached the requested research state. No unsupported queued fallback or auto-completion is used.

## TDD evidence

RED, before production changes:

```text
python -m unittest tests.test_build_order_upgrades -v
FAIL test_presents_completed_optional_and_queued_upgrade_checks
  expected "Research wheelbarrow"; got "wheelbarrow"
ERROR setUpClass
  upgrades.scar did not exist
```

GREEN focused check:

```text
python -m unittest tests.test_build_order_upgrades -v
Ran 5 tests ... OK
```

The test fixture was moved from the shared Windows temp directory into a temporary directory beneath the worktree after a repeat run hit an OS access-denied error for a newly created shared-temp directory. This did not alter production behavior.

## Static checks

- Focused: `python -m unittest tests.test_build_order_upgrades -v` (5/5 passed).
- Existing compiler coverage: `python -m unittest tests.test_build_order_compiler -v` (11/11 passed).
- `check_code` on `assets/scar/build_orders/checks/upgrades.scar`: no low-confidence APIs. It recognizes all external AoE calls. Its only listed unknown calls are the three local helper functions, `or` (parser artifact), and the two project-owned engine functions `BuildOrder_RegisterHandler` / `BuildOrder_SetCheckComplete`.

## In-game validation request

Issue: GRI-59
Branch: codex/gri-59-upgrades-check
Worktree: E:\Docs\github\aoemod\aoe4-macro-trainer\.worktrees\gri-59-upgrades-check
Commit: pending static-suite completion and commit
Fixture/selection: An English build order with `upgrades: [{id: wheelbarrow}, {id: horticulture, queued: true}, {id: fitted_leatherwork, optional: true}]` in separate steps as needed to observe each transition.
Human actions: Complete Wheelbarrow; then place Horticulture into a human-owned mill queue; then optionally research Fitted Leatherwork.
Opponent guard: Before each matching human action, have an opponent complete Wheelbarrow and queue Horticulture. Neither action may complete or advance the human player’s objective.
Expected UI: `Research wheelbarrow`; `Queue horticulture for research`; `[Optional] Research fitted_leatherwork`. Completed and queued checks latch complete while their step is active. The optional descriptor does not block advancement.
Limitations: Queued research is detected only when the requested upgrade is present in a currently observable production queue of a player-owned entity. Player-scoped upgrade queues with no entity producer are not exposed by the verified APIs and therefore cannot satisfy a queued descriptor until completion is visible through `Player_HasUpgrade`.
