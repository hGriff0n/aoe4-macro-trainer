# Simspeed Timer Cycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Macro Trainer gamemode alternate indefinitely between 45 seconds at simulation rate 8.0 and 15 seconds at simulation rate 0.0.

**Architecture:** Four temporary constants configure the two rates and durations. Two named one-shot timer callbacks set the next rate and schedule one another; lifecycle hooks initialize the cycle and remove pending timers on game over.

**Tech Stack:** AoE4 SCAR/Lua, Python `unittest` source-contract test, AoE4 modding MCP validation, AoE4 Content Editor CLI build.

## Global Constraints

- Normal simulation rate is exactly `8.0`.
- Slow simulation rate is exactly `0.0`.
- Normal duration is exactly `45` seconds.
- Slow duration is exactly `15` seconds.
- Use `setsimrate`, not `setsimpause`.
- Use `TimerAddOnce` with invocable command strings; each transition schedules the other.
- Delete a matching timer before adding it to prevent duplicates.
- On game over, delete both timers and restore normal simulation rate.
- Preserve the user's existing `.codex/config.toml` modification.

---

### Task 1: Implement and validate the simspeed cycle

**Files:**
- Create: `tests/test_simspeed_cycle.py`
- Modify: `assets/scar/winconditions/Macro Trainer.scar`

**Interfaces:**
- Consumes: AoE4 APIs `setsimrate(Real rate)`, `TimerAddOnce(String command, Real timeInSec)`, and `TimerDel(String command)`.
- Produces: SCAR callbacks `Mod_EnterSlowSpeed()` and `Mod_EnterNormalSpeed()`, initialized by `Mod_Start()` and cleaned up by `Mod_OnGameOver()`.

- [ ] **Step 1: Write the failing source-contract test**

Create a Python `unittest` that reads the production SCAR file and verifies the externally meaningful callback contract: the four exact test values exist; `Mod_Start()` sets normal speed and schedules slow mode; entering slow mode sets rate zero and schedules normal mode after 15 seconds; entering normal mode restores rate 8 and schedules slow mode after 45 seconds; both scheduling paths delete their matching timer first; game-over cleanup deletes both timers and restores normal speed; and `setsimpause` is absent.

- [ ] **Step 2: Run the test to verify it fails for the missing cycle**

Run: `python -m unittest tests.test_simspeed_cycle -v`

Expected: FAIL because the constants and transition callback functions do not exist.

- [ ] **Step 3: Implement the minimal SCAR cycle**

In the data section, add constants named `NORMAL_SIM_RATE`, `SLOW_SIM_RATE`, `NORMAL_SPEED_DURATION_SECONDS`, and `SLOW_SPEED_DURATION_SECONDS` with the exact global values. Add `Mod_EnterSlowSpeed()` and `Mod_EnterNormalSpeed()` functions. Each function sets its rate, deletes the timer command it is about to register, then registers the opposite callback with `TimerAddOnce`. Initialize normal speed and the first timer from `Mod_Start()`. Delete both command timers and restore `NORMAL_SIM_RATE` in `Mod_OnGameOver()`.

- [ ] **Step 4: Run the focused test to verify it passes**

Run: `python -m unittest tests.test_simspeed_cycle -v`

Expected: PASS with no failures or errors.

- [ ] **Step 5: Validate the full SCAR source with the AoE4 MCP**

Pass the complete modified `Macro Trainer.scar` source and its target path to `check_code`. Review every unknown or low-confidence call. `TimerAddOnce`, `TimerDel`, and `setsimrate` may be reported as low-confidence documented APIs because the MCP's official index has signatures but no usage samples; unknown-call findings are not acceptable.

- [ ] **Step 6: Run repository checks and inspect the diff**

Run: `python -m unittest discover -s tests -v`

Run: `git diff --check`

Run: `git diff -- assets/scar/winconditions/'Macro Trainer.scar' tests/test_simspeed_cycle.py`

Expected: all tests pass, whitespace check exits zero, and the diff contains only the planned cycle/test changes.

- [ ] **Step 7: Commit the implementation**

```powershell
git add -- 'assets/scar/winconditions/Macro Trainer.scar' 'tests/test_simspeed_cycle.py'
git commit -m "feat: add timed simspeed cycle"
```

### Task 2: Build the AoE4 mod package

**Files:**
- Input: `Macro Trainer.aoe4mod`
- Output: Content Editor build artifacts managed by the AoE4 toolchain.

**Interfaces:**
- Consumes: the committed SCAR implementation from Task 1 and absolute descriptor path `E:\\Docs\\github\\aoemod\\aoe4-macro-trainer\\Macro Trainer.aoe4mod`.
- Produces: an externally built AoE4 mod package suitable for in-game smoke testing.

- [ ] **Step 1: Confirm the descriptor and launcher paths exist**

Verify the absolute `.aoe4mod` path and `F:\\Program Files (x86)\\Steam\\steamapps\\common\\Age of Empires IV Content Editor\\EssenceLauncher.exe` exist.

- [ ] **Step 2: Display the exact required build command and obtain user confirmation**

```powershell
& 'F:\Program Files (x86)\Steam\steamapps\common\Age of Empires IV Content Editor\EssenceLauncher.exe' --build_mod 'E:\Docs\github\aoemod\aoe4-macro-trainer\Macro Trainer.aoe4mod' --auto_close_burn_window
```

- [ ] **Step 3: Run the confirmed build and record evidence**

Execute only the displayed command. Record the launcher exit code and relevant output. Do not claim the package built successfully unless the fresh command exits successfully.

- [ ] **Step 4: Report mandatory in-game checks**

Playtest that the match begins at normal rate, pauses after 45 seconds, resumes after 15 seconds, repeats, and accepts UI input while paused. Specifically validate that `TimerAddOnce` accepts the invocable command strings and advances while simulation rate is zero.
