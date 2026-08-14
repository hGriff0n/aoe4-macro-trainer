# Valid SCAR Timer Rules Design

## Problem

The simspeed cycle uses `TimerDel` and `TimerAddOnce`. AoE IV reports `TimerDel` as an invalid variable at runtime. The official AoE IV scripting guide documents `Rule_AddOneShot(FunctionName, delay)` for delayed callbacks and `Rule_Remove(FunctionName)` for cancellation.

## Design

Keep the existing two-callback cycle and the `Misc_SetSimRate` calls introduced by GRI-45. Replace every timer registration with `Rule_AddOneShot` and every timer cancellation with `Rule_Remove`. Pass callbacks as function references rather than strings.

`Mod_Start` removes and schedules `Mod_EnterSlowSpeed`. Each transition changes the sim rate, removes the opposite pending callback defensively, and schedules that callback once. `Mod_OnGameOver` removes both callbacks and restores normal speed.

## Testing

The source contract test must require the documented rule calls and reject both legacy timer identifiers. It must continue checking callback order, duration constants, and sim-rate behavior.

## Documentation

Correct the existing cycle design and implementation plan so they no longer recommend invalid timer APIs or string callbacks.
