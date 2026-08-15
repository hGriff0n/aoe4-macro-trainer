# Compensated Phase Objectives Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement integer-rate compensated phase timing and a native objective countdown for each phase.

**Architecture:** A shared phase-entry helper owns objective cleanup/creation, rate selection, countdown initialization, and compensated transition scheduling. The two named rule callbacks supply phase-specific values and game-over cleanup tears down both rules and the active objective.

**Tech Stack:** AoE IV SCAR/Lua, locdb CSV, Python `unittest`

## Global Constraints

- Simulation rates must be integers from `1` through `8`, inclusive.
- Normal gameplay uses rate `8`; slowed gameplay uses rate `1`.
- Configured durations remain `45` and `15` real-world seconds.
- Do not add custom XAML or call `UI_SetPropertyValue`.
- Preserve unrelated workspace changes.

---

### Task 1: Define the Timing and Objective Contract

**Files:**
- Modify: `tests/test_simspeed_cycle.py`
- Modify: `assets/locdb/Macro Trainer_en.csv`

**Interfaces:**
- Produces: locdb IDs `4` (`NORMAL`) and `5` (`PAUSED`), plus tests for compensated phase timing and objective lifecycle.

- [ ] **Step 1: Write failing tests** requiring rates `8` and `1`, a `Mod_GetCompensatedRuleDelay` calculation, objective lifecycle calls, localized objective titles, and shared phase setup.
- [ ] **Step 2: Run** `python -m unittest tests.test_simspeed_cycle -v` and verify failure because the SCAR source still uses rate `0` and has no objectives.
- [ ] **Step 3: Add** localization rows `4` and `5` to the English project CSV.

### Task 2: Implement Compensated Phase Objectives

**Files:**
- Modify: `assets/scar/winconditions/Macro Trainer.scar`

**Interfaces:**
- Produces: `Mod_GetCompensatedRuleDelay(realDuration, simRate)`, `Mod_ClearPhaseObjective()`, and `Mod_StartPhase(title, duration, simRate, nextRule)`.
- Consumes: `Objective_Register`, `Objective_Start`, `Objective_StartTimer`, `Objective_StopTimer`, `Objective_Expire`, `Rule_AddOneShot`, and `Misc_SetSimRate`.

- [ ] **Step 1: Implement** the minimal shared helpers and route `Mod_Start`, `Mod_EnterSlowSpeed`, and `Mod_EnterNormalSpeed` through them.
- [ ] **Step 2: Run** `python -m unittest tests.test_simspeed_cycle -v` and verify all focused tests pass.
- [ ] **Step 3: Refactor** duplicated scheduling/cleanup only while tests remain green.

### Task 3: Validate and Export

**Files:**
- Verify: `assets/scar/winconditions/Macro Trainer.scar`
- Build: `Macro Trainer.aoe4mod`

**Interfaces:**
- Consumes: completed source and locdb data.
- Produces: API-validated SCAR and an exported mod package.

- [ ] **Step 1: Run** `$env:PYTHONDONTWRITEBYTECODE='1'; python -m unittest discover -s tests -v`.
- [ ] **Step 2: Run** the AoE4 SCAR checker and resolve unknown or low-confidence calls.
- [ ] **Step 3: Export** `Macro Trainer.aoe4mod` with the Content Editor CLI workflow.
- [ ] **Step 4: Review** `git diff` and confirm only scoped files changed.
