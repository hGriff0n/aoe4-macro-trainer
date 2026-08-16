# Precomputed Phase Durations Design

## Problem

The slow phase runs at simulation rate 1, so its player-facing title must be `SLOW`, not `PAUSED`. Its transition rule currently waits for a compensated simulation-time delay while the objective countdown starts from the unscaled real-time duration, causing the displayed countdown and actual transition to disagree.

## Approaches Considered

1. Precompute both phase durations once in `Mod_Start`, store them in `_mod`, and reuse the stored values for every transition. This is the selected approach because phase settings do not change after startup.
2. Recalculate the compensated duration during every phase transition. This remains correct but repeats a calculation whose inputs are immutable during the match.
3. Define manually calculated duration constants. This avoids runtime arithmetic but can drift from the configured real durations or simulation rates when either changes.

## Design

At the beginning of `Mod_Start`, calculate each simulation-time phase duration with `math.ceil(realDuration * simRate / NORMAL_SIM_RATE)`. Store the results as `_mod.normalPhaseDuration` and `_mod.slowPhaseDuration`. With the current settings, these are 45 and 2 whole simulation seconds respectively.

Change `Mod_StartPhase` to accept a precomputed phase duration rather than a real duration. Pass that same duration to `Objective_StartTimer` and `Rule_AddOneShot`, making it the single authoritative value for both the displayed countdown and the actual transition. `Mod_EnterSlowSpeed` and `Mod_EnterNormalSpeed` reuse the stored durations without recalculation. Remove the obsolete per-transition compensation helper.

Change localization entry 5 from `PAUSED` to `SLOW`. Objective positioning and all other UI behavior remain out of scope.

## Validation

Contract tests will first fail unless startup precomputes both rounded-up durations, phase transitions consume the stored values, and both timer APIs receive the same `phaseDuration`. Tests will also require localization entry 5 to contain `SLOW` and reject the old `PAUSED` text. The complete test suite must pass before rebuilding the mod for in-game verification.
