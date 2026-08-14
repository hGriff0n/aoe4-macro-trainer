# Valid SCAR Timer Rules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace invalid simspeed timer calls with documented AoE IV SCAR rule APIs.

**Architecture:** Preserve the existing callback cycle and change only its scheduling boundary. Delayed work uses `Rule_AddOneShot` with function references, while defensive cleanup uses `Rule_Remove` with the same references.

**Tech Stack:** AoE IV SCAR/Lua, Python `unittest`

## Global Constraints

- Keep `Misc_SetSimRate` from GRI-45.
- Preserve rates `8.0` and `0.0` and durations `45` and `15` seconds.
- Do not modify unrelated workspace changes.

---

### Task 1: Replace Legacy Timer Calls

**Files:**
- Modify: `tests/test_simspeed_cycle.py`
- Modify: `assets/scar/winconditions/Macro Trainer.scar`
- Modify: `docs/superpowers/specs/2026-08-11-simspeed-timer-cycle-design.md`
- Modify: `docs/superpowers/plans/2026-08-11-simspeed-timer-cycle.md`

**Interfaces:**
- Consumes: AoE IV SCAR `Rule_AddOneShot(FunctionName, Real delay)` and `Rule_Remove(FunctionName)`.
- Produces: The existing `Mod_Start`, `Mod_EnterSlowSpeed`, `Mod_EnterNormalSpeed`, and `Mod_OnGameOver` lifecycle behavior using valid rule APIs.

- [ ] **Step 1: Write the failing regression test**

Require calls such as `Rule_AddOneShot(Mod_EnterSlowSpeed, NORMAL_SPEED_DURATION_SECONDS)` and `Rule_Remove(Mod_EnterSlowSpeed)`. Reject `TimerAddOnce` and `TimerDel` anywhere in production SCAR.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `python -m unittest tests.test_simspeed_cycle -v`

Expected: FAIL because production still contains `TimerAddOnce` and `TimerDel`.

- [ ] **Step 3: Implement the minimal SCAR correction**

Replace each legacy registration and removal call with its documented rule equivalent, passing callback functions without quotes.

- [ ] **Step 4: Correct historical implementation documentation**

Replace legacy timer names, signatures, and command-string caveats with the documented rule APIs and function-reference behavior.

- [ ] **Step 5: Verify GREEN**

Run: `$env:PYTHONDONTWRITEBYTECODE='1'; python -m unittest discover -s tests -v`

Expected: all tests PASS.

- [ ] **Step 6: Build the mod**

Use the repository's `aoe4mod-build` skill to validate Content Editor CLI export.

- [ ] **Step 7: Review the final diff**

Confirm only GRI-46 source, tests, and documentation changed.
