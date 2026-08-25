# Build-Order Checks Design

## Scope

Implement Linear parent issue GRI-83 and its direct sub-issues:

- GRI-55: `vils`;
- GRI-56: `built`;
- GRI-57: `age_up`;
- GRI-58: `resources`;
- GRI-59: `upgrades`;
- GRI-60: `produce`;
- GRI-62: `units`;
- GRI-63: `hints`; and
- GRI-80: `rallypoint`.

The implementation extends the objective engine delivered by GRI-71. The schema's experimental `buildings` and `vils.no_collect` checks remain out of scope because GRI-83 has no child issue defining their production behavior.

## Non-Negotiable Player Scope

Every runtime check operates on the human player passed to `BuildOrder_Start`. Opponent actions must never satisfy, advance, reverse, or otherwise mutate a build-order objective.

Handlers receive the exact player handle through the active engine context. Polling handlers form their entity, squad, resource, or technology queries from that handle. Event handlers either register a player-scoped listener or compare the event owner/producer/player against that handle before examining the event's blueprint or action. A blueprint match without a player match is insufficient.

Static contract tests must demonstrate the player predicate for each handler. Manual validation includes an opponent performing the same action before the human player; the objective must remain incomplete.

## Engine Contract

The engine continues to register handlers by check kind. Each handler exposes:

```lua
local handler = {
	activate = function(check, objectiveID, context)
	end,
	deactivate = function(check, objectiveID, context)
	end,
}
BuildOrder_RegisterHandler("kind", handler)
```

`check` contains the stable generated `id`, `kind`, localized `title`, `optional` flag, and typed `payload`. `context.localPlayer` is the only player handle a production handler may observe. `objectiveID` is owned by the engine; handlers may update its state through the engine but may not delete it.

The engine adds `BuildOrder_SetCheckComplete(checkID, completed)`. It performs an idempotent transition and updates the child objective to `OS_Complete` or `OS_Incomplete`. A `false` transition never rewinds to an earlier step: reversible checks can uncomplete only while their own step remains active. `BuildOrder_NotifyComplete(checkID)` remains as a compatibility wrapper that calls `BuildOrder_SetCheckComplete(checkID, true)`.

After setting a required child complete, the engine evaluates advancement. Optional children never block advancement. Once a step advances, its handlers are deactivated and late callbacks for its old check IDs are ignored.

Activation occurs only after all child objectives for the step exist. Deactivation is idempotent and removes every rule, listener, temporary group, or other resource created by that activation. A handler must support more than one active descriptor of its kind without global-name collisions.

## Runtime Module Boundaries

Each issue owns one focused handler module under `assets/scar/build_orders/checks/`. A module contains its handler state, polling or event callbacks, lifecycle functions, and registration. Shared engine behavior stays in `objective_engine.scar`.

The common documentation branch establishes the reversible state API and handler contract tests. Sub-issue branches do not change another issue's handler module. Each branch may change compiler, emitter, fixtures, and their focused tests when its descriptor shape or presentation requires it.

The final integration branch owns the ordered imports of all handler modules. Sub-issue branches prove their module can be imported and registered but do not build the `.aoe4mod` package.

## Descriptor Cardinality and Payloads

The compiler emits deterministic descriptors in YAML field and list order.

- `vils` emits one required descriptor for the entire mapping. Its payload contains the configured resource thresholds. Its single title renders the four configured counts in `food | gold | wood | stone` order, omitting resources that were not set. The objective is reversible.
- `built` emits one required descriptor per list entry. Its payload preserves `id` or `oneof`, `count`, `vils`, and `location`. Completion is latched for the active step.
- `age_up` emits one required descriptor containing `id` or `oneof`, plus `vils` and `location`. Completion is latched when progress actually starts; queueing alone is insufficient.
- `resources` emits one required descriptor per configured resource in YAML order. Its payload contains `resource` and `count`. Each objective is reversible.
- `upgrades` emits one descriptor per list entry with `id` and `queued`. The descriptor's existing `optional` metadata controls parent advancement. Completed research is latched. Queued research completes when a supported player-scoped queue signal or query proves it.
- `produce` emits one descriptor per list entry with `id`, `count`, `constant`, and `queued`. Normal production counts human-player completion events and latches at the requested count. Queued and constant semantics must be backed by a supported player-scoped API; otherwise their displayed objective remains visibly non-blocking and the limitation is recorded during that issue's validation rather than silently simulating success.
- `units` emits one required descriptor per list entry with `id` and `count`. It polls living units controlled by the human player and is reversible.
- `hints` emits one optional descriptor per string. Its title is `[HINT] <hint>`. It has no runtime completion predicate and never blocks advancement.
- `rallypoint` emits one descriptor per configured town center. A one-item list displays `Rally new vils to <resource>`. Longer lists label the first as the main town center and subsequent items by one-based construction order. The handler considers only human-owned town centers and is reversible while the step is active.

## Presentation

Generated localization text is deterministic. Where supported by the normal objective title renderer, a resource, unit, building, technology, landmark, or town-center reference uses its official in-game icon or localized name. If an icon cannot be represented safely, the compiler emits an official localized display string when available and a readable identifier-derived fallback only when neither form is available.

Presentation lookup must not make gameplay correctness depend on localized text. Runtime matching uses canonical blueprint, technology, or resource identifiers stored in the payload.

## Capability-Limited Variants

GRI-57, GRI-59, GRI-60, and GRI-80 require API investigation because some civilizations or queue/rally systems may expose different signals. Each issue begins with official API and official-source usage research, records the chosen signal in its tests and report, and uses static polling only when no reliable scoped event exists.

A capability gap cannot be hidden by auto-completing a required objective. If a requested variant cannot be detected reliably, the branch keeps it visible and non-blocking with explicit presentation, documents the exact limitation, and requests user validation of that behavior. The final wording is chosen within the issue branch based on the verified API limitation.

## Testing

Every issue adds compiler/emitter tests for its exact title, optionality, cardinality, and payload. SCAR contract tests cover registration, activation, player scoping, completion behavior, cleanup, and coexistence of multiple descriptors.

Reversible checks test both incomplete-to-complete and complete-to-incomplete transitions. Latched event checks test ignored opponent events, ignored unrelated IDs, duplicate events, threshold completion, late callbacks after deactivation, and idempotent cleanup.

The main task runs the full Python suite on each ready branch. The AoE4 API checker validates added SCAR source. Sub-agents never invoke the Content Editor or build a mod package.

## Branch, Worktree, and Validation Workflow

The documentation/interface branch is `codex/gri-83-objective-checks`, based on commit `4930a9f` from `codex/gri-71-integration`. After the shared contract implementation is committed, every issue branch and worktree is created from the same resulting commit.

Each issue receives one persistent sub-agent and one worktree. Available agent slots limit execution concurrency but do not change branch isolation. An issue agent owns implementation, static tests, review fixes, and playtest fixes for that issue.

When static review passes, the agent queues a validation request containing:

- issue and branch;
- absolute worktree path;
- commit SHA;
- build-order fixture or selection;
- human-player actions;
- opponent actions that must be ignored;
- expected objective text and transitions; and
- known capability limitations.

The main task presents waiting requests. The user chooses one request, and only then does the main task build the mod from that request's worktree. The user reports the in-game result to the main task, which forwards it verbatim to the persistent issue agent. Failed validation returns to implementation and static review before being queued again.

Only branches with successful requested validation are integrated. The integration branch resolves shared compiler and import-list conflicts, runs the complete static suite, receives final code review, then queues a final combined mod build and playtest.

## Success Criteria

GRI-83 is complete when all nine child issue branches satisfy their Linear behavior, explicitly scope every check to the human player, pass static and API-contract validation, receive the requested in-game validation, and integrate without regressing the GRI-71 startup or objective lifecycle.
