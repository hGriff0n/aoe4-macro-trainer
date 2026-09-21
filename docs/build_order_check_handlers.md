# Build-Order Check Handler Guide

This guide explains how to add a production check to the GRI-83 build-order objective engine. The binding architecture and acceptance criteria live in `docs/superpowers/specs/2026-08-25-build-order-checks-design.md`.

## Data Flow

The scar handler flow is controlled through `build_orders/objectives.scar`, specifically the `SetCurrentObjective`, `BuildOrder_Objectives_CheckCompletion`, and `CleanupCurrentObjective` functions.

1. Individual checks register their handles through the `BuildOrder_Objectives_RegisterCheckHandlers` function
	- Each `BuildOrder_Check_{check}_Register` function must call this
2. `SetCurrentObjective` is called to set up the next build order step
	1. For each check, `GetCheckHandle` grabs the registered handles
	2. `handles.activate` is called to setup the listeners/polling for that check. If `activate` returns False, then the check is skipped as the registration did not succeed
	3. `handles.format_check_text` is called to get the formatted loc text
	4. The AOE4 Objective object is created for the check sub objective
2. `BuildOrder_Objectives_CheckCompletion` is called each tick to run any polling checks and check objective completion status
	1. For each sub-objective, the check `poll_handle` is called if one is set. This returns whether the sub-objective is completed or not
	2. For event-based checks, the objective's status is compared to `OS_Complete` instead
	3. If all required sub-objectives are complete, then the engine marks the step objective complete and progresses to the next step via `BuildOrder_Objectives_NextStep`
3. `BuildOrder_Objectives_NextStep` first cleans up the current objective and then tries to load the next step, unless the current objective is the last one in the build order.
	1. `CleanupCurrentObjective` calls the `deactivate` handle for each check and deletes the objective hierarchy
	2. If there is a next step in the build order, the engine repeats at `SetCurrentObjective`
	3. Otherwise, `BuildOrder_Objectives_Stop` is called to disable the events and rules

## New Handler Creation

For adding a new check handler, you must:

1. Copy `assets/scar/build_orders/checks/.template.scar` to `assets/scar/build_orders/checks/<kind>.scar`
2. Replace `{check}` with `<kind>` in the new scar file
3. Delete polling handle if check is implemented via event listeners
	- Prefer using events over polling if possible
4. Implement using other checks as examples if needed
	- Make sure that the `Activate` and `Deactivate` handles still work if multiple checks of the same kind are registered in the same step
5. Import new check in `assets/scar/build_orders/objectives.scar` and append `BuildOrder_Check_{check}_Register` to the `BuildOrder_Objectives_OnInit` function

## Human-Player Filter

`check.player` is the authoritative gameplay player. Do not call `Game_GetLocalPlayer` inside a handler and do not search every player for a matching blueprint.

For polling:

- create or query groups owned by the stored player;
- ask resource and technology APIs about the stored player;
- verify that returned entities or squads are still controlled by the stored player when ownership can change; and
- count only matching canonical IDs after the owner constraint is established.

For events:

- prefer a listener registered for the stored player;
- otherwise compare the event player, owner, or producer with the stored player first;
- only then compare blueprint, technology, ability, or resource identifiers; and
- ignore events that lack enough ownership information to prove they came from the human player.

Every handler test includes an opponent event or opponent-owned matching entity and asserts that it cannot change the objective.

<!-- TODO: Use for todo? -->
## Completion APIs

Use the state-setting API for both latched and reversible checks:

```lua
BuildOrder_SetCheckComplete(check.id, predicateIsTrue)
```

For a latched event counter, call it with `true` once the human player's counter reaches its threshold. For a reversible polling check, call it after each poll with the current predicate result. Repeating the current state is safe and must not replay completion effects.

`BuildOrder_NotifyComplete(check.id)` is retained for compatibility, but new handlers should prefer the explicit state API.

The engine ignores unknown check IDs and repeated assignments of the current state. A transition to `true` marks the child objective complete and asks the engine to advance when all required checks are complete; a transition to `false` marks it incomplete without advancing.

An old callback may fire after a transition. The engine ignores unknown inactive check IDs, and the handler callback should also return immediately when its per-check state is absent.
