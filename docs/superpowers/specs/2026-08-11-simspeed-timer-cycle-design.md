# Simspeed Timer Cycle Design

## Scope

Implement Linear issues GRI-34 and GRI-36 in the Macro Trainer win-condition SCAR script. The match starts at normal simulation speed and repeatedly alternates between normal and paused gameplay using temporary hardcoded test values.

## Constants

- Normal simulation rate: `8.0`
- Slow simulation rate: `0.0`
- Time at normal speed: `45` seconds
- Time at slow speed: `15` seconds

These values are intentionally hardcoded for testing and will be replaced with dynamic configuration in a later issue.

## Runtime Design

Add two named transition callbacks to `assets/scar/winconditions/Macro Trainer.scar`:

- `Mod_EnterSlowSpeed()` sets the simulation rate to `0.0` and schedules `Mod_EnterNormalSpeed()` after 15 seconds.
- `Mod_EnterNormalSpeed()` sets the simulation rate to `8.0` and schedules `Mod_EnterSlowSpeed()` after 45 seconds.

`Mod_Start()` initializes the cycle by explicitly setting the normal rate and scheduling the first slow-speed transition. Each transition uses `Rule_AddOneShot`, so callbacks schedule one another rather than relying on a fixed repeating interval.

Rule registrations pass callback function references such as `Mod_EnterSlowSpeed`, matching the official AoE IV scripting guide's `Rule_AddOneShot(FunctionName, Delay in seconds)` signature.

## Safety and Cleanup

Before registering a transition rule, remove any matching rule with `Rule_Remove` to prevent duplicate callbacks if initialization or scheduling is invoked more than once.

`Mod_OnGameOver()` removes both possible pending transition rules and restores the normal simulation rate. The implementation uses `Misc_SetSimRate`, not `setsimpause`, so UI input remains available according to GRI-32's findings.

## Known Risk

The requested slow rate is `0.0`. If AoE4's one-shot rules advance in simulation time rather than wall-clock time, entering rate zero may prevent the scheduled normal-speed callback from firing. GRI-34 and GRI-36 explicitly prescribe the zero-rate/timer combination, so the implementation will follow it and treat recovery from zero as an in-game validation point.

## Verification

1. Add a source-level automated check for the constants, transition callbacks, scheduling sequence, lifecycle initialization, duplicate-timer protection, and cleanup.
2. Run the check once before implementation to confirm it fails for the missing feature, then again after implementation to confirm it passes.
3. Run the completed SCAR through the AoE4 MCP `check_code` validator.
4. Build/export the `.aoe4mod` using the repository's AoE4 build workflow.
5. Playtest the built mod to validate timer command parsing and whether a timer can restore simulation from rate zero.
