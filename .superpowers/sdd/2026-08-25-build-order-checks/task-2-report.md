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
Commit: 5ca4afc (report update follows in the final commit)
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
