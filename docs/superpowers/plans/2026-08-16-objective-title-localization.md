# Objective Title Localization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the normal and paused objective titles resolve from the mod localization database instead of displaying `No Key`.

**Architecture:** Keep the existing objective-per-phase lifecycle. Introduce two named SCAR constants containing fully qualified mod-local localization keys, then pass those constants into the unchanged `Mod_StartPhase` function.

**Tech Stack:** AoE4 SCAR/Lua, CSV locdb source, Python `unittest` contract tests.

## Global Constraints

- Use localization IDs 4 (`NORMAL`) and 5 (`PAUSED`) from `assets/locdb/Macro Trainer_en.csv`.
- Use compact mod GUID `dfb5645698a84afb91cf7a2dfb0f4a4e` from `Macro Trainer.aoe4mod`.
- Do not change native objective positioning or add custom UI.
- Do not change objective timers, phase durations, simulation rates, or lifecycle behavior.

---

### Task 1: Resolve phase objective titles through mod-local keys

**Files:**
- Modify: `tests/test_simspeed_cycle.py`
- Modify: `assets/scar/winconditions/Macro Trainer.scar`

**Interfaces:**
- Consumes: locdb IDs `4` and `5`; mod GUID `dfb56456-98a8-4afb-91cf-7a2dfb0f4a4e`.
- Produces: `NORMAL_PHASE_OBJECTIVE_TITLE` and `SLOW_PHASE_OBJECTIVE_TITLE`, each a fully qualified AoE4 localization-key string.

- [ ] **Step 1: Write the failing localization contract test**

Add this test to `SimspeedCycleContractTests`:

```python
def test_phase_titles_use_fully_qualified_mod_localization_keys(self) -> None:
    mod_namespace = "dfb5645698a84afb91cf7a2dfb0f4a4e"
    self.assertIn(
        f'NORMAL_PHASE_OBJECTIVE_TITLE = "${mod_namespace}:4"',
        self.source,
    )
    self.assertIn(
        f'SLOW_PHASE_OBJECTIVE_TITLE = "${mod_namespace}:5"',
        self.source,
    )
    self.assertNotRegex(self.source, r'Mod_StartPhase\("\$[45]"')
```

Update the existing phase assertions to require `NORMAL_PHASE_OBJECTIVE_TITLE` and `SLOW_PHASE_OBJECTIVE_TITLE` instead of literal `"$4"` and `"$5"` arguments.

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```powershell
python -m unittest tests.test_simspeed_cycle.SimspeedCycleContractTests.test_phase_titles_use_fully_qualified_mod_localization_keys -v
```

Expected: FAIL because neither named constant exists yet and the phase functions still pass bare localization IDs.

- [ ] **Step 3: Add the fully qualified localization constants**

In `Macro Trainer.scar`, immediately after the duration constants, add:

```lua
NORMAL_PHASE_OBJECTIVE_TITLE = "$dfb5645698a84afb91cf7a2dfb0f4a4e:4"
SLOW_PHASE_OBJECTIVE_TITLE = "$dfb5645698a84afb91cf7a2dfb0f4a4e:5"
```

Replace the three phase calls with:

```lua
Mod_StartPhase(NORMAL_PHASE_OBJECTIVE_TITLE, NORMAL_SPEED_DURATION_SECONDS, NORMAL_SIM_RATE, Mod_EnterSlowSpeed)
Mod_StartPhase(SLOW_PHASE_OBJECTIVE_TITLE, SLOW_SPEED_DURATION_SECONDS, SLOW_SIM_RATE, Mod_EnterNormalSpeed)
Mod_StartPhase(NORMAL_PHASE_OBJECTIVE_TITLE, NORMAL_SPEED_DURATION_SECONDS, NORMAL_SIM_RATE, Mod_EnterSlowSpeed)
```

- [ ] **Step 4: Run all tests and verify GREEN**

Run:

```powershell
python -m unittest discover -s tests -v
```

Expected: all tests PASS with no errors.

- [ ] **Step 5: Review the diff and commit the fix**

Run:

```powershell
git diff --check
git diff -- tests/test_simspeed_cycle.py "assets/scar/winconditions/Macro Trainer.scar"
git add -- tests/test_simspeed_cycle.py "assets/scar/winconditions/Macro Trainer.scar" docs/superpowers/plans/2026-08-16-objective-title-localization.md
git commit -m "fix: resolve phase objective localization"
```
