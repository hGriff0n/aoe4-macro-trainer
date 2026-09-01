# Build-Order Refactors Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove duplicated SCAR check plumbing, make age-up trigger selection compiler-owned with default support for every civilization, and replace the compiler's monolithic check dispatcher with a registry.

**Architecture:** A small SCAR support module will own blueprint comparison/resolution and polymorphic event-owner lookup while gameplay-specific handlers remain separate. Age-up descriptors will carry an explicit `trigger` chosen by the compiler, so runtime code no longer owns civilization support policy. The compiler will then dispatch through focused per-kind functions stored in `CHECK_COMPILERS`, with accepted check fields derived from the registry.

**Tech Stack:** Python 3, `unittest`, YAML compiler, AoE4 SCAR/Lua scripts.

**Spec:** User-approved scope in the 2026-08-31 task conversation; no separate specification file.

## Global Constraints

- Do not change, reject, implement, or otherwise alter the documented `built` or `buildings` functionality.
- Produce exactly three incremental implementation commits, one for each task below.
- Follow strict red-green-refactor: add a focused failing test, confirm the expected failure, implement the smallest production change, then run focused and full tests.
- Preserve every existing check's gameplay semantics, player-ownership filtering, event lifecycle, descriptor ordering, titles, optional flags, and payload fields except for the intentional addition of `age_up.payload.trigger`.
- All civilizations are supported by default for age-up checks; civilizations not explicitly upgrade-triggered use construction triggers.
- Keep `produce`, `units`, `built`, `age_up`, and `upgrades` as separate gameplay handlers; share only generic plumbing.
- Run `python -m unittest discover -s tests -v` before each commit.

---

### Task 1: Shared SCAR Check Utilities

**Files:**
- Create: `assets/scar/build_orders/check_support.scar`
- Modify: `assets/scar/winconditions/Macro Trainer.scar`
- Modify: `assets/scar/build_orders/checks/age_up.scar`
- Modify: `assets/scar/build_orders/checks/built.scar`
- Modify: `assets/scar/build_orders/checks/produce.scar`
- Modify: `assets/scar/build_orders/checks/units.scar`
- Modify: `assets/scar/build_orders/checks/upgrades.scar`
- Create: `tests/test_build_order_check_support.py`
- Modify: affected handler contract tests only where old private helper names are asserted

**Interfaces:**
- Consumes: SCAR PBG objects with `PropertyBagGroupID`, `PropertyBagGroupModPackID`, and `PropertyBagGroupType`; payloads shaped as either `{id = ...}` / `{oneof = {...}}` or `{ids = {...}}`; event contexts with direct-player or entity executers.
- Produces: `BuildOrder_BlueprintsEqual(left, right) -> bool`, `BuildOrder_MatchesAnyBlueprint(pbgs, pbg) -> bool`, `BuildOrder_ResolveBlueprints(ids, resolver) -> table`, `BuildOrder_ResolvePayloadBlueprints(payload, resolver) -> table`, and `BuildOrder_GetExecuterOwner(context) -> player|nil`.

- [ ] **Step 1: Write the failing support-module contract test**

Create a test that verifies the packaged root imports `build_orders/check_support.scar` exactly once after `objective_engine.scar` and before every check handler. Verify the support module exposes the five interfaces above, blueprint equality is nil-safe and compares the full three-field tuple, payload resolution supports both `id` and `oneof`, and executor ownership supports direct player and entity shapes. Verify each affected handler calls the shared interfaces rather than declaring its old `*_PBGsEqual`, `*_BlueprintsEqual`, `*_MatchesPBG`, `*_ResolvePBGs`, or `*_GetExecuterOwner` implementation.

- [ ] **Step 2: Run the focused test to verify RED**

Run: `python -m unittest tests.test_build_order_check_support -v`

Expected: FAIL because `check_support.scar` and its import do not exist.

- [ ] **Step 3: Add the shared module and migrate handlers**

Implement nil-safe tuple equality, `ipairs`-based list matching/resolution, payload `id`/`oneof` resolution, and the existing direct-player/entity executor-owner behavior. Import the module immediately after `objective_engine.scar`. Replace duplicated helpers in the five handlers without changing their state, observer, polling, or event behavior.

- [ ] **Step 4: Run focused and full tests to verify GREEN**

Run:

```powershell
python -m unittest tests.test_build_order_check_support tests.test_build_order_age_up tests.test_build_order_built tests.test_build_order_produce tests.test_build_order_units tests.test_build_order_upgrades tests.test_build_order_import_graph tests.test_build_order_objectives -v
python -m unittest discover -s tests -v
```

Expected: all tests pass with no warnings or errors.

- [ ] **Step 5: Commit Task 1**

```powershell
git add docs/superpowers/plans/2026-08-31-build-order-refactors.md assets/scar/build_orders/check_support.scar assets/scar/winconditions/'Macro Trainer.scar' assets/scar/build_orders/checks/age_up.scar assets/scar/build_orders/checks/built.scar assets/scar/build_orders/checks/produce.scar assets/scar/build_orders/checks/units.scar assets/scar/build_orders/checks/upgrades.scar tests/test_build_order_check_support.py tests/test_build_order_age_up.py tests/test_build_order_built.py tests/test_build_order_produce.py tests/test_build_order_units.py tests/test_build_order_upgrades.py tests/test_build_order_import_graph.py tests/test_build_order_objectives.py
git commit -m "refactor: share build-order check utilities"
```

### Task 2: Compiler-Owned Age-Up Trigger Strategy

**Files:**
- Modify: `tools/build_orders/compiler.py`
- Modify: `assets/scar/build_orders/checks/age_up.scar`
- Modify: `tests/test_build_order_age_up.py`
- Modify: `tests/test_build_order_compiler.py`
- Modify: emitter/build tests only where exact age-up payload output is asserted

**Interfaces:**
- Consumes: the existing `UPGRADE_AGE_UP_CIVS` exception set and canonical age-up identity payloads.
- Produces: every compiled age-up payload includes `trigger: "upgrade"` for explicit exceptions and `trigger: "construction"` for every other civilization; the SCAR handler stores and dispatches on `check.payload.trigger` without a supported-civilization allowlist.

- [ ] **Step 1: Write failing compiler and runtime tests**

Add literal payload expectations for both an upgrade-triggered civilization and a construction-triggered civilization. Add a custom identity catalog fixture containing a new/future civilization with one entity age-up identity and assert compilation succeeds with `trigger == "construction"`. Update the runtime contract to require payload-trigger dispatch and to reject any `AGE_UP_SUPPORTED_CIVS`, unsupported-state, unsupported-log, or runtime civilization allowlist behavior.

- [ ] **Step 2: Run focused tests to verify RED**

Run: `python -m unittest tests.test_build_order_age_up tests.test_build_order_compiler -v`

Expected: FAIL because age-up payloads lack `trigger` and runtime still contains the support allowlist.

- [ ] **Step 3: Compile trigger metadata and simplify runtime dispatch**

Add a compiler helper that returns `"upgrade"` only for `UPGRADE_AGE_UP_CIVS` and `"construction"` otherwise. Use the same decision for identity category and emitted payload. In SCAR, resolve the blueprint with `BP_GetUpgradeBlueprint` only when payload trigger is `"upgrade"`; otherwise default to `BP_GetEntityBlueprint`. Store a boolean or trigger on handler state and use it for baseline checks, event filtering, and observer registration. Remove `AGE_UP_SUPPORTED_CIVS`, unsupported state, unsupported logging, and runtime dependence on `context.civ`.

- [ ] **Step 4: Run focused and full tests to verify GREEN**

Run:

```powershell
python -m unittest tests.test_build_order_age_up tests.test_build_order_compiler tests.test_build_order_build -v
python -m unittest discover -s tests -v
```

Expected: all tests pass and generated SCAR payload expectations include the trigger.

- [ ] **Step 5: Commit Task 2**

```powershell
git add tools/build_orders/compiler.py assets/scar/build_orders/checks/age_up.scar tests/test_build_order_age_up.py tests/test_build_order_compiler.py tests/test_build_order_build.py
git commit -m "refactor: compile age-up trigger strategy"
```

### Task 3: Registry-Based Check Compiler Dispatch

**Files:**
- Modify: `tools/build_orders/compiler.py`
- Modify: `tests/test_build_order_compiler.py`
- Modify: per-kind compiler tests only if imports of moved private helpers change

**Interfaces:**
- Consumes: the existing validator, identity resolution, title generation, and `CheckDescriptor` behavior from Tasks 1-2.
- Produces: `CHECK_COMPILERS`, a mapping from every existing documented check kind to a focused compiler callable; `CHECK_FIELDS`, derived from the registry keys; `_check_descriptors` reduced to registry lookup and dispatch.

- [ ] **Step 1: Write the failing registry invariant test**

Add a test that imports `CHECK_COMPILERS` and asserts its keys are exactly the current documented check kinds in a literal set, including the intentionally deferred `built` and `buildings` entries. Assert `CHECK_FIELDS == set(CHECK_COMPILERS)` so adding or removing a compiler cannot silently desynchronize accepted step fields.

- [ ] **Step 2: Run the focused test to verify RED**

Run: `python -m unittest tests.test_build_order_compiler -v`

Expected: ERROR or FAIL because `CHECK_COMPILERS` does not exist.

- [ ] **Step 3: Extract focused per-kind compiler functions and registry dispatch**

Create small per-kind functions for `vils`, `resources`, `rallypoint`, `built`, `age_up`, `upgrades`, `produce`, `buildings`, `units`, and `hints`. Share narrowly scoped helpers for structure/age-up entries and counted identity entries, but keep kind-specific title/default/optional behavior explicit. Define `CHECK_COMPILERS` after the functions, derive `CHECK_FIELDS = set(CHECK_COMPILERS)`, and make `_check_descriptors` look up and invoke the selected callable. Remove unreachable `vils` branches and the unused `no_collect` parameter from `_resource_checks`. Preserve descriptor order and exact validation paths/messages.

- [ ] **Step 4: Run focused and full tests to verify GREEN**

Run:

```powershell
python -m unittest tests.test_build_order_compiler tests.test_build_order_vils tests.test_build_order_resources tests.test_build_order_age_up tests.test_build_order_upgrades tests.test_build_order_produce tests.test_build_order_units tests.test_build_order_hints -v
python -m unittest discover -s tests -v
```

Expected: all tests pass with unchanged user-visible behavior.

- [ ] **Step 5: Commit Task 3**

```powershell
git add tools/build_orders/compiler.py tests/test_build_order_compiler.py tests/test_build_order_vils.py tests/test_build_order_resources.py tests/test_build_order_age_up.py tests/test_build_order_upgrades.py tests/test_build_order_produce.py tests/test_build_order_units.py tests/test_build_order_hints.py
git commit -m "refactor: dispatch check compilers through registry"
```
