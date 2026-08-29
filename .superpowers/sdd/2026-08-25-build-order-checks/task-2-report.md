# GRI-55 `vils` check report

## Result

Implemented the reversible, human-player-scoped `vils` check. A YAML `vils` mapping now emits exactly one descriptor with canonical resource thresholds and a deterministic compact title. The SCAR handler polls the stored local player, combines all configured thresholds, reports both completion states, and removes its per-check polling rule on deactivation.

## TDD evidence

The recovered worktree contains the RED-to-GREEN contract tests in `tests/test_build_order_compiler.py`, `tests/test_build_order_build.py`, and `tests/test_build_order_vils.py`. The original interrupted agent's terminal RED output is not available in repository history, so that portion is reported honestly rather than reconstructed. The focused suite passed 18/18 and the full discovery suite passed 70/70 before this recovery; no source changes were made during recovery.

## API and usage evidence

The selected SCAR calls are `BuildOrder_SetCheckComplete`, `context.localPlayer`, `Player_GetNumGatheringSquads(player, resourceType)`, `Rule_Add`, and `Rule_Remove`, with `RT_Food`, `RT_Gold`, `RT_Wood`, and `RT_Stone`. Repository usage confirms the objective lifecycle and rule cleanup conventions. The AoE4 `check_code` run on `assets/scar/build_orders/checks/vils.scar` completed with no low-confidence or missing-localization issues. The prior official API MCP research transcript is not present in the recovered worktree, so exact MCP citation details cannot be reproduced here; the static checker result is retained as the available verification evidence.

## Validation request

Issue: GRI-55
Branch: codex/gri-55-vils-check
Worktree: E:\Docs\github\aoemod\aoe4-macro-trainer\.worktrees\gri-55-vils-check
Commit: 5aa5df3c3a0e29a168c04188ece1bd5d9c52ebcf
Fixture/selection: English — Villager split (`vils: {food: 7, gold: 3, wood: 4, stone: 2}`)
Human actions: Activate the build-order objective; assign the human player's villagers to 7 food, 3 gold, 4 wood, and 2 stone gatherers; then move one human villager below a threshold and back above it.
Opponent guard: Have an opponent assign matching villagers to the same four resource thresholds first; the human objective must remain incomplete until the human player's own thresholds are met.
Expected UI: One required child objective titled `7 F | 3 G | 4 W | 2 S`; it changes to complete only when every configured human-player threshold is met, and returns to incomplete when any threshold falls below its target.
Limitations: No verified API limitations.

## Static validation

- Focused tests: 18/18 passed.
- Full `python -m unittest discover -s tests -v`: 70/70 passed.
- AoE4 `check_code` for `vils.scar`: passed with no low-confidence or missing-localization issues.
- Content Editor mod build: intentionally not run on this issue worktree.

## Fix round: reproducible official API evidence

The AoE4 MCP official index was queried for the runtime calls used by this handler:

- `Player_GetNumGatheringSquads(Player& player, Integer type)`: high-confidence official API documentation, `official_api/Essence_ScarFunctions.api:1293`; described as returning the number of squads currently gathering a resource type. High-confidence official usage is `official_scar/training/coretrainingconditions.scar:28-31`, where `localPlayer = Game_GetLocalPlayer()` is passed with `RT_Food`, `RT_Wood`, `RT_Stone`, and `RT_Gold`.
- `Rule_Add(f, data, group)`: high-confidence official wrapper definition at `official_scar/rulesystem.scar:25`, annotated `@result Integer` and `@args LuaFunction f [, Table data, RuleGroup group]`. Official call usage includes `official_scar/camera.scar:145` and `official_scar/campaignpanel.scar:199`, both registering a Lua rule function with `Rule_Add(rule)`.
- `Rule_Remove(f)`: high-confidence official wrapper definition at `official_scar/rulesystem.scar:337`, annotated `@result Void` and `@args LuaFunction rule`, with the implementation noting it removes time rules. Official cleanup usage includes `official_scar/campaignpanel.scar:225` and `:950`, guarding with `Rule_Exists` before `Rule_Remove(rule)`.

These exact signatures and official-source paths justify the handler's stored-player polling and per-check time-rule lifecycle. `BuildOrder_SetCheckComplete` and `BuildOrder_RegisterHandler` are project-owned wrappers, not official engine APIs; their contracts are defined and tested in this repository (`assets/scar/build_orders/objective_engine.scar` and `tests/test_build_order_vils.py`).

## Validation feedback fix

Validation feedback: assigning one human villager to each required resource did not complete the check; the objective title displayed `F/G/W/S` shorthand rather than resource icons or names.

Root cause: `Player_GetNumGatheringSquads` is the documented, high-confidence API for the desired measurement and official training SCAR uses it with `RT_Food`, `RT_Wood`, `RT_Stone`, and `RT_Gold`. The handler's recurring update never ran because it passed an anonymous closure to `Rule_Add`; the runtime reports `Adding unnamed function as rule; this is not allowed`. The activation-time poll occurred before later villager assignment, exactly matching the observed behavior.

Fix: all active `vils` descriptors share the named `Vils_PollAll` rule. It registers once for the first active descriptor, polls every active descriptor, and removes itself only after the last descriptor deactivates. The compiler now emits readable full resource names (for example, `7 food villagers`) because this project's generated locdb/objective-title pipeline provides no supported resource-icon markup convention.

TDD and static evidence: the new shared-rule contract failed before the implementation because `Vils_PollAll` and its last-listener cleanup were absent; title expectations failed because the compiler still emitted shorthand. Focused tests passed 19/19 after the fix. Full discovery passed 72/72. `check_code` reported no low-confidence APIs or missing locdb IDs; its sole `Vils_Poll` finding is a false-positive project-local function reference.

New validation request: activate English — Villager split and assign the human player's villagers to the required food/gold/wood/stone thresholds after the objective is active. Confirm that the child completes, becomes incomplete after dropping any threshold, and that its text uses full resource names. Repeat with an opponent matching the split first; the human objective must remain incomplete until the human thresholds are met. Content Editor build intentionally not run by this subagent.

## Second validation feedback investigation

Validation feedback: the objective still did not complete. The requested presentation correction is that a split should not repeat `villagers` after every resource.

Evidence from the newest runtime session: `E:\Docs\My Games\Age of Empires IV\LogFiles\AoE4_08_29_08h-16m-45s\scarlog.2026-08-29.08-16-45.txt` contains only the SCAR error-log header, with no GRI-55 messages or errors. More importantly, the archive used by that session is byte-identical to this worktree's `archives\Macro_Trainer.sga` and was exported at `2026-08-28 21:01:45`, but the exported root `assets/scar/winconditions/Macro Trainer.scar` imports `generated/build_orders.scar`, `objective_engine.scar`, and `startup.scar` without importing `build_orders/checks/vils.scar`. Consequently the handler file never executes, `BuildOrder_RegisterHandler("vils", ...)` never runs, and the engine silently creates an objective without an active handler. This is the primary root cause of both failed validation attempts; it is independent of `Player_GetNumGatheringSquads` semantics.

Fix and diagnostic instrumentation: import `build_orders/checks/vils.scar` from the root wincondition SCAR. The handler now emits always-on `GRI55_VILS|POLL` records for every named poll, including check id, bound player, configured food/gold/wood/stone thresholds, and all four `Player_GetNumGatheringSquads` return values. It uses only named rules and `tostring` for safe value formatting. The counts have deliberately not been replaced: the official API and training-script references remain the strongest available evidence, but this build is needed to confirm real-session values.

Presentation: generated `vils` titles now read `1 food | 1 gold | 1 wood | 1 stone` (or the configured subset), without a repeated `villagers` suffix. No supported resource-icon markup was found in the project's existing locdb/objective-title pipeline.

TDD/static evidence: import, diagnostics, and compact-title expectations were added first and failed before the production changes. Focused tests passed 39/39; full discovery passed 74/74. `check_code` reported no low-confidence APIs or missing locdb IDs. Its `Vils_LogPoll` and `Vils_Poll` entries are project-local functions not indexed as official APIs.

New validation request: build this diagnostic commit through the main validation flow, select English — Villager split, and assign one human villager each to food, gold, wood, and stone after activation. Return the `GRI55_VILS|POLL` lines from the scarlog. They will establish whether each resource uses the expected `RT_*` argument/count; also confirm an opponent's gatherers do not affect the logged human-player counts. This is a diagnostic build, not a claimed behavioral fix.

## Diagnostic safety fix

Review identified that an unexpected `nil` (or another non-number) from `Player_GetNumGatheringSquads` would be safely printed but then crash on comparison, losing the diagnostic evidence. `Vils_Poll` now logs the raw four values first and normalizes each value through `Vils_CountOrZero` before threshold comparison. An unavailable value consequently evaluates as zero and leaves the objective incomplete instead of crashing the named shared rule.

TDD evidence: the focused contract test failed before `Vils_CountOrZero` existed, then passed after the change. Full discovery passed 75/75 and `git diff --check` passed. `check_code` reported no low-confidence API or missing localization findings; listed `Vils_CountOrZero`, `Vils_LogPoll`, and `Vils_Poll` are project-local function references.
