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
