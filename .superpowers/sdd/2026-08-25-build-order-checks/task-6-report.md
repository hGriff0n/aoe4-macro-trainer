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

## Fix round 1/5: review coverage and idempotent activation

Changes:

- Added contract coverage that a queue can return true only inside the stored-player owner guard and only after matching an upgrade queue item type and the requested canonical PBG. This covers matching opponent and unrelated queue rejection.
- Added independent completion coverage: completed research is the fallback, and queue inspection is gated by `state.queued`.
- Added lifecycle coverage for duplicate activation, duplicate completion/late polling, idempotent deactivation, and multiple simultaneous descriptors sharing one polling rule.
- Made activation idempotent for a live `check.id`, preventing an accidental duplicate activation from replacing the existing state or adding work.

RED before the SCAR change:

```text
python -m unittest tests.test_build_order_upgrades -v
FAIL test_duplicate_activation_is_idempotent_for_one_check
AssertionError: 'if UPGRADES_STATE[check.id] ~= nil then' not found in Upgrades_Activate
Ran 9 tests ... FAILED (failures=1)
```

GREEN:

```text
python -m unittest tests.test_build_order_upgrades -v
Ran 9 tests ... OK
```

Final validation before the fix commit:

```text
python -m unittest tests.test_build_order_upgrades -v
Ran 9 tests ... OK

python -m unittest discover -s tests -v
Ran 72 tests ... OK

check_code assets/scar/build_orders/checks/upgrades.scar
unknown calls: local helpers plus parser token `or`; low-confidence APIs: none; missing locdb: none

git diff --check
(no output)
```

## Fix round 2/5: executable upgrade behavior contract

The prior round's source contracts were retained for SCAR/API shape, but its
review scenarios are now exercised by `UpgradeHandlerModel`, a test-only Python
model of the handler boundary. The executable tests prove that:

- matching opponent queues and unrelated queue type/PBG entries do not complete;
- completed research completes a normal descriptor independently of queue state;
- queued descriptors complete only for matching `PITEM_Upgrade` or
  `PITEM_PlayerUpgrade` entries owned by the stored player;
- duplicate activation keeps the original active state;
- repeated deactivation and a late poll cannot complete a removed check; and
- two active check IDs remain independent while sharing one polling lifecycle.

RED before the harness existed:

```text
python -m unittest tests.test_build_order_upgrades -v
ERROR: seven BuildOrderUpgradeBehaviorTests
NameError: name 'UpgradeHandlerModel' is not defined
Ran 12 tests ... FAILED (errors=7)
```

GREEN after adding the harness:

```text
python -m unittest tests.test_build_order_upgrades -v
Ran 12 tests ... OK
```

The SCAR handler is unchanged in this round, so its prior `check_code` result
remains applicable; no new SCAR API call was introduced.

Final full validation for this round:

```text
python -m unittest discover -s tests -v
Ran 75 tests ... OK

git diff --check
(no output)
```

## Event-audit follow-up: completion events and activation reconciliation

The GRI-83 runtime probe established that completed research emits
`GE_UpgradeComplete` with the canonical upgrade PBG. The executor is
polymorphic: it can be a direct player (`executer.PlayerID`) or an entity
(`executer.EntityID`) whose owner must be resolved. Both observed successful
upgrades emitted `GE_UpgradeCancelled` immediately before completion, so the
handler deliberately does not subscribe to cancellation and latches a matching
completion.

The handler now:

- reconciles already-completed human research through `Player_HasUpgrade` when
  the descriptor activates;
- subscribes to `GE_UpgradeComplete` only while an incomplete upgrade descriptor
  is active;
- rejects opponent, unowned, pre-activation, and noncanonical-PBG signals;
- compares all three PBG tuple fields after resolving ownership;
- retains the existing player-owned production-queue query only for incomplete
  descriptors with `queued: true`; and
- never treats `GE_UpgradeStart` as proof of queue insertion.

Actual user cancellation was not probed. The implementation therefore makes no
claim about cancellation semantics beyond ensuring the observed paired
Cancel-to-Complete sequence cannot undo or suppress completion.

TDD RED before the handler change:

```text
python -m unittest tests.test_build_order_upgrades.BuildOrderUpgradeHandlerContractTests
Ran 9 tests ... FAILED (failures=1, errors=4)
```

Focused GREEN after the event handler and executable ownership/event model:

```text
python -m unittest tests.test_build_order_upgrades -v
Ran 22 tests ... OK
```

Final static validation (the mod was not built):

```text
python -m unittest discover -s tests -v
Ran 85 tests ... OK

check_code assets/scar/build_orders/checks/upgrades.scar
low-confidence APIs: none; missing locdb: none

git diff --check
(no errors)
```

Updated main-task validation request:

```text
Issue: GRI-59
Branch: codex/gri-59-upgrades-check
Worktree: E:\Docs\github\aoemod\aoe4-macro-trainer\.worktrees\gri-59-upgrades-check
Commit: supplied in the agent handoff after commit
Fixture/selection: Human and opponent with the same completed upgrade objective; a separate queued upgrade behind another production item if the civilization permits it.
Human actions: Let startup settle, activate the objective, complete the requested upgrade, and separately place a requested queued upgrade behind an existing item.
Opponent guard: Have the opponent complete the same upgrade before the human. The human objective must remain incomplete.
Expected UI: Pre-activation/startup signals do not complete the objective; the matching human completion latches once despite the observed paired cancellation event; already-completed human research reconciles immediately on activation.
Limitations: GE_UpgradeStart is not used for queued semantics. Queue insertion behind another item and genuine cancellation remain unverified in-game; queued detection is limited to the existing player-owned entity production-queue query.
```
