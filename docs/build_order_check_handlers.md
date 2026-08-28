# Build-Order Check Handler Guide

This guide explains how to add a production check to the GRI-83 build-order objective engine. The binding architecture and acceptance criteria live in `docs/superpowers/specs/2026-08-25-build-order-checks-design.md`.

## Data Flow

1. `tools/build_orders/compiler.py` converts one YAML check into one or more `CheckDescriptor` values.
2. `tools/build_orders/emitters.py` writes those descriptors into `generated/build_orders.scar` with a stable check ID, localized title, optional flag, and typed payload.
3. `BuildOrder_ActivateStep` creates every child objective and then calls the registered handler's `activate` function.
4. The handler observes the engine-provided `context.localPlayer` and `context.civ`, then reports state through the engine.
5. Before step transition or game shutdown, the engine calls `deactivate` and then deletes the objective hierarchy.

## Handler Shape

Place each handler in `assets/scar/build_orders/checks/<kind>.scar`:

```lua
local KIND_STATE = {}

local function Kind_Activate(check, objectiveID, context)
	local player = context.localPlayer
	if player == nil then
		return
	end

	KIND_STATE[check.id] = {
		player = player,
		objectiveID = objectiveID,
		payload = check.payload,
	}
end

local function Kind_Deactivate(check, objectiveID, context)
	local state = KIND_STATE[check.id]
	if state == nil then
		return
	end

	-- Remove this check's rules, listeners, and temporary groups here.
	KIND_STATE[check.id] = nil
end

BuildOrder_RegisterHandler("kind", {
	activate = Kind_Activate,
	deactivate = Kind_Deactivate,
})
```

Use a per-check table keyed by `check.id`; one global Boolean or counter breaks steps containing multiple checks of the same kind. Prefix callbacks and rule names with the check kind and derive unique runtime names from the stable check ID when the SCAR API requires named rules.

## Human-Player Filter

`context.localPlayer` is the authoritative gameplay player. Do not call `Game_GetLocalPlayer` inside a handler and do not search every player for a matching blueprint.

`context.civ` is the authoritative normalized civilization ID for the selected build order. Use it for civilization-specific behavior such as choosing the appropriate event mechanism; do not derive it from an entity, the currently observed player race, or check payload data.

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

## Completion APIs

Use the state-setting API for both latched and reversible checks:

```lua
BuildOrder_SetCheckComplete(check.id, predicateIsTrue)
```

For a latched event counter, call it with `true` once the human player's counter reaches its threshold. For a reversible polling check, call it after each poll with the current predicate result. Repeating the current state is safe and must not replay completion effects.

`BuildOrder_NotifyComplete(check.id)` is retained for compatibility, but new handlers should prefer the explicit state API.

The engine ignores unknown check IDs and repeated assignments of the current state. A transition to `true` marks the child objective complete and asks the engine to advance when all required checks are complete; a transition to `false` marks it incomplete without advancing.

An old callback may fire after a transition. The engine ignores unknown inactive check IDs, and the handler callback should also return immediately when its per-check state is absent.

## Activation and Cleanup

Activation may run again for a later step with the same check kind. It must initialize a fresh counter or predicate and must not reuse results from a prior step.

Deactivation must be safe when called more than once. Remove handler-owned rules and listeners before discarding state. Do not delete or hide the child objective; the engine owns it. Do not advance steps directly; the engine decides advancement after required children are complete.

## Compiler Responsibilities

The compiler, not the runtime handler, owns:

- descriptor cardinality;
- default values;
- schema validation;
- deterministic title text;
- optional metadata; and
- canonical payload keys.

The runtime handler owns only the gameplay predicate and its lifecycle. Do not parse presentation text to recover an ID or count.

For every compiler change, test the exact descriptor sequence, title, optional flag, and payload. For every emitter change, test the exact SCAR representation and localization output.

## Static Validation

Before requesting an in-game build, an issue branch must pass:

```powershell
python -m unittest discover -s tests -v
```

Run the AoE4 SCAR API checker over every added or changed SCAR module. Resolve unknown and low-confidence calls with official API documentation and official-source usage. A sub-agent stops after these static checks and sends a validation request to the main task; it does not invoke the Content Editor.

## Validation Request

Send the main task a request in this format:

```text
Issue: GRI-XX
Branch: codex/gri-XX-...
Worktree: E:\absolute\path\to\worktree
Commit: <full SHA>
Fixture/selection: <build order and civilization>
Human actions: <ordered actions>
Opponent guard: <matching opponent action that must be ignored>
Expected UI: <exact objective text and state changes>
Limitations: <verified API limitations, or "none">
```

The main task queues the request. It builds this worktree only after the user selects it. Playtest feedback returns through the main task to the same issue agent.
