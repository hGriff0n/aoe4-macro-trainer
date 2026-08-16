# Precomputed Phase Durations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Display `SLOW` during the slow phase and make the objective countdown equal the rounded-up simulation-time transition delay.

**Architecture:** Compute both immutable phase durations once in `Mod_Start` and store them in `_mod`. Pass each stored whole-second duration through `Mod_StartPhase` to both the native objective timer and the transition rule.

**Tech Stack:** AoE4 SCAR/Lua, CSV locdb source, Python `unittest` contract tests.

## Global Constraints

- Calculate durations only in `Mod_Start`.
- Round fractional simulation-time durations up with `math.ceil`.
- Use one `phaseDuration` value for `Objective_StartTimer` and `Rule_AddOneShot`.
- Localized slow-phase title must be exactly `SLOW`.
- Do not change objective positioning or add custom UI.

---

### Task 1: Precompute and reuse whole-second phase durations

**Files:**
- Modify: `tests/test_simspeed_cycle.py`
- Modify: `assets/scar/winconditions/Macro Trainer.scar`
- Modify: `assets/locdb/Macro Trainer_en.csv`

**Interfaces:**
- Consumes: `NORMAL_SPEED_DURATION_SECONDS`, `SLOW_SPEED_DURATION_SECONDS`, `NORMAL_SIM_RATE`, and `SLOW_SIM_RATE`.
- Produces: `_mod.normalPhaseDuration`, `_mod.slowPhaseDuration`, and `Mod_StartPhase(title, phaseDuration, simRate, nextRule)`.

- [ ] **Step 1: Write failing contract assertions**

Update `test_phase_rates_and_rule_delays_preserve_real_time` to require these startup calculations:

```python
self.assertIn(
    "_mod.normalPhaseDuration = math.ceil(NORMAL_SPEED_DURATION_SECONDS * NORMAL_SIM_RATE / NORMAL_SIM_RATE)",
    start,
)
self.assertIn(
    "_mod.slowPhaseDuration = math.ceil(SLOW_SPEED_DURATION_SECONDS * SLOW_SIM_RATE / NORMAL_SIM_RATE)",
    start,
)
```

Require phase calls to pass `_mod.normalPhaseDuration` or `_mod.slowPhaseDuration`. Require `Mod_StartPhase` to pass `phaseDuration` to both timer APIs, and require the locdb assertion for ID 5 to end in `SLOW` while rejecting `PAUSED`.

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```powershell
python -m unittest tests.test_simspeed_cycle.SimspeedCycleContractTests.test_phase_rates_and_rule_delays_preserve_real_time tests.test_simspeed_cycle.SimspeedCycleContractTests.test_each_phase_replaces_the_standard_objective_silently -v
```

Expected: FAIL because durations are still calculated inside `Mod_StartPhase`, the objective timer uses `realDuration`, and locdb ID 5 is `PAUSED`.

- [ ] **Step 3: Implement startup precomputation and shared duration use**

Add nil duration fields to `_mod`. In `Mod_Start`, assign:

```lua
_mod.normalPhaseDuration = math.ceil(NORMAL_SPEED_DURATION_SECONDS * NORMAL_SIM_RATE / NORMAL_SIM_RATE)
_mod.slowPhaseDuration = math.ceil(SLOW_SPEED_DURATION_SECONDS * SLOW_SIM_RATE / NORMAL_SIM_RATE)
```

Pass the appropriate stored duration from every phase entry point. Change the helper signature to:

```lua
function Mod_StartPhase(title, phaseDuration, simRate, nextRule)
```

Remove `Mod_GetCompensatedRuleDelay`, `realDuration`, and `ruleDelay`. Use:

```lua
_mod.phaseDeadline = _mod.phaseStartTime + phaseDuration
Objective_StartTimer(objective, COUNT_DOWN, phaseDuration, 0)
Rule_AddOneShot(nextRule, phaseDuration)
```

Change locdb ID 5 text from `PAUSED` to `SLOW`.

- [ ] **Step 4: Run the complete test suite and verify GREEN**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -m unittest discover -s tests -v
```

Expected: all tests PASS without errors.

- [ ] **Step 5: Review and commit**

Run:

```powershell
git diff --check
git diff -- tests/test_simspeed_cycle.py "assets/scar/winconditions/Macro Trainer.scar" "assets/locdb/Macro Trainer_en.csv"
git add -- tests/test_simspeed_cycle.py "assets/scar/winconditions/Macro Trainer.scar" "assets/locdb/Macro Trainer_en.csv" docs/superpowers/plans/2026-08-16-precomputed-phase-durations.md
git commit -m "fix: align phase objective timers"
```
