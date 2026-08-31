# GRI-83 Validation Fixes Report

## Status and commit

Implementation commit: `50a05f2955afe097c4a5a4979d710d6175112313` (`fix: stabilize objective check advancement`).

The implementation adds synchronous check-update batching, updates vils/units display strings, and installs the temporary rallypoint auto-complete handler. No Content Editor build or push was performed.

## Fatal root cause

The Abbasid Eco 2TC step-3 failure was a same-callback table mutation. Step 3 contains one aggregate `vils` descriptor. `Vils_PollAll` traversed `VILS_STATE` with `pairs`; `Vils_Poll` completed that descriptor and called `BuildOrder_SetCheckComplete`; the setter synchronously called `BuildOrder_TryAdvance`; advancement deactivated step 3 (deleting the current `VILS_STATE` key and removing its poll), then activated step 4 (inserting a new vils key and adding the poll again). Control returned to the old generic-for traversal, whose implicit `next(VILS_STATE, oldKey)` failed with SCAR's fatal `invalid key to 'next'`.

The latest relevant persisted scarlog recorded the fatal at 2026-08-31 07:38:15 after step 3 became active. The persisted log did not retain Lua frames, but the complete synchronous code path was evidenced in:

- `assets/scar/build_orders/checks/vils.scar`: `Vils_PollAll` -> `Vils_Poll` -> `BuildOrder_SetCheckComplete`;
- `assets/scar/build_orders/objective_engine.scar`: setter -> `BuildOrder_TryAdvance` -> `BuildOrder_ClearActiveHierarchy` -> next-step activation; and
- the generated Abbasid Eco 2TC catalog: consecutive step-3 and step-4 vils descriptors, with step 4 initially incomplete.

The same structural risk existed in other polling, event, and reconciliation callbacks that called the setter while traversing mutable handler state.

## Fix design

`BuildOrder_BeginCheckUpdates()` increments a nesting depth. While the depth is positive, a true completion transition updates/latches the child objective and sets one `checkAdvancePending` flag instead of advancing. `BuildOrder_EndCheckUpdates()` decrements the depth and, only at the outermost end, clears the pending flag and attempts advancement exactly once. Direct setter behavior outside a batch remains immediate; the existing activation guard remains authoritative, and step activation still performs its final `BuildOrder_TryAdvance()`.

`BuildOrder_Stop()` resets both batch fields before cleanup. `BuildOrder_TryAdvance()` also defensively converts a direct in-batch attempt into the coalesced pending flag.

Balanced batches now surround every real callback/reconciliation traversal that can call `BuildOrder_SetCheckComplete`:

- vils and resources shared polling;
- units authoritative polling;
- built construction-complete events (after context validation);
- produce queued reconciliation and completion events;
- upgrades next-tick reconciliation, start events, and completion events; and
- age-up construction-start and upgrade-start events.

Activation-only baseline setters remain protected by `activatingHandlers` and do not traverse handler state in a production callback. Rallypoint activation likewise does not traverse state.

## Official rule-priority finding

The official Age of Empires IV scripting documentation describes `Rule_Add` as running every simulation tick, `Rule_AddOneShot` as running once after a delay, and the interval/global-event forms by trigger type. It exposes no priority parameter and states no deterministic ordering guarantee among rules scheduled for the same tick: <https://support.ageofempires.com/hc/en-us/articles/4437502402068-Scripting-for-Crafted-Maps> and <https://support.ageofempires.com/hc/en-us/articles/4424274153620-Editing-a-Script>.

Therefore a deferred rule or assumed rule priority/order cannot be used as a correctness boundary. The implemented boundary is synchronous and explicit: advancement happens only after the callback finishes its own traversal.

## Display and rallypoint changes

- Positive aggregate vils titles now start with `Assign`, including exact coverage for `Assign 1 food` and `Assign 1 food | 1 wood`; ordering remains food/gold/wood/stone. `No <resource> villagers` remains unchanged.
- Units titles are now `Have <count> active <family label>` without changing family resolution or runtime payloads.
- `rallypoint.scar` is a conspicuous temporary stub. Activation first requires non-nil `context.localPlayer`, then completes the descriptor. Deactivation is a no-op. The module has no player discovery, query, event, rule, polling, or state table and is imported exactly once immediately after the objective engine and before startup.

## TDD evidence

### RED

Tests were changed before production code and executed independently. Expected failures reproduced each missing behavior:

- objective engine: 3 failures for missing batch fields/APIs and missing shutdown reset;
- vils/resources/units/built/produce/upgrades/age-up: callback contract failures for missing begin/end boundaries (the age-up test helper was corrected after an initial test-only `NameError`, then produced the expected two missing-boundary failures);
- compiler/units/build: failures showing old `7 food`, old `Have 2 spearman active`, and old emitted localization text;
- rallypoint: `FileNotFoundError` because the handler module/import did not exist.

The executable engine model already specified the intended transition: state remains step 3 during traversal, outer End installs step 4, one poll remains registered, and the incomplete step-4 vils check does not advance.

### GREEN

After the minimum implementation:

- all focused engine, handler, compiler, import, rallypoint, and build-order build tests passed;
- the executable model passed consecutive-vils, nesting/coalescing, and shutdown-reset behavior;
- the full test suite passed 256 tests; and
- generate-only compilation of the external build-order directory exited 0.

## Files changed

Runtime:

- `assets/scar/build_orders/objective_engine.scar`
- `assets/scar/build_orders/checks/{vils,resources,units,built,produce,upgrades,age_up}.scar`
- `assets/scar/build_orders/checks/rallypoint.scar`
- `assets/scar/winconditions/Macro Trainer.scar`
- `tools/build_orders/compiler.py`

Tests:

- `tests/test_build_order_objectives.py`
- `tests/test_build_order_{vils,resources,units,built,produce,upgrades,age_up}.py`
- `tests/test_build_order_rallypoint.py`
- `tests/test_build_order_compiler.py`
- `tests/test_build_order_build.py`

Documentation:

- `docs/build_order_check_handlers.md`
- `docs/build_order_event_probe_findings.md`
- `docs/build_order_schema.yaml`
- `docs/superpowers/specs/2026-08-25-build-order-checks-design.md`
- `docs/superpowers/specs/2026-08-30-unit-family-identities-design.md`

Ignored generated localization artifacts were not manually edited.

## Verification commands and results

- Focused `python -m unittest discover -s tests -p 'test_build_order_<area>.py' -v` runs for objectives, vils, resources, units, built, produce, upgrades, age-up, compiler, build, import graph, and rallypoint: all passed.
- `python -m unittest discover -s tests -v`: `Ran 256 tests ... OK`. A final sandboxed retry was unable to write Windows `%TEMP%` and produced environment-only `PermissionError` results before assertions; the required host-temp rerun then passed all 256 tests in 0.853s. Its one exact sandbox-created worktree temp directory was verified to be under this worktree and removed.
- `git diff --check`: passed (only Git's existing LF/CRLF conversion notices appeared).
- `python tools/build_mod.py --build-orders 'E:\Docs\github\aoemod\build orders' --generate-only`: exited 0 with no stderr.
- Content Editor / EssenceLauncher: intentionally not invoked under the task constraint.

## Self-review

- Every Begin added to production has a matching End and occurs only after callback context early-return validation.
- No batching implementation uses `Rule_Add`, `Rule_AddOneShot`, priority, or execution-order assumptions.
- Existing player predicates remain before identity comparisons; built gained stricter nil context validation.
- Aggregate vils payload/cardinality, unit family IDs, constant-production behavior, and reconciled built/resources/upgrades semantics are unchanged.
- Rallypoint import ordering and absence of runtime observation machinery have shared import-edge and source-contract coverage.
- The worktree contained no unrelated tracked changes before this task.

## Concerns and follow-up

- An in-game Content Editor validation is still required to confirm the fatal no longer occurs when Abbasid Eco 2TC advances from step 3 to step 4; it was prohibited for this implementation task.
- Rallypoint completion is intentionally temporary and does not validate actual rally targets. It must remain conspicuously documented until target-to-resource classification is proven with human-player ownership filtering.
- The Python behavior model validates the batching contract and exact consecutive-vils lifecycle, while SCAR source-contract tests bind handlers to the public batch APIs. The repository has no standalone SCAR interpreter, so final runtime confirmation remains the planned playtest.
