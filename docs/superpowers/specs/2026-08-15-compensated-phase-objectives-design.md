# Compensated Phase Objectives Design

## Scope

Implement the approved solutions for GRI-47 and GRI-31 in the Macro Trainer win-condition script. The gameplay loop alternates between a normal phase at simulation rate `8` and a slowed planning phase at simulation rate `1`. Each phase is represented by a fresh standard AoE IV objective with a native countdown.

## Timing Model

- Simulation rates are integer values in the supported range `1..8`.
- Normal gameplay uses rate `8`; slowed gameplay uses rate `1`.
- Configured durations remain player-facing real-time seconds: normal `45`, slowed `15`.
- SCAR rule delays are compensated with `realDuration * phaseRate / NORMAL_SIM_RATE`. The normal transition is therefore scheduled after `45` simulation seconds and the slowed transition after `1.875` simulation seconds.
- The objective countdown receives the same player-facing duration used by the transition calculation. The objective timer and transition rule are initialized together at every phase change.

## Objective Lifecycle

Track the active phase objective in `_mod.phaseObjective`. At each phase transition:

1. If an objective is active, stop its timer and expire it with `showTitle=false` and `playIntel=false`.
2. Create a fresh objective table using the localized title for the new phase and `OT_Information`.
3. Register and start the objective without title-card or intel presentation.
4. Start its native countdown with `Objective_StartTimer(objective, COUNT_DOWN, realDuration, 0)`.
5. Set the new simulation rate and schedule the next transition with the compensated SCAR delay.

The localized player-facing titles are `NORMAL` and `PAUSED`. No custom XAML, named UI element, runtime title mutation, or `UI_SetPropertyValue` is introduced.

On game over, remove both transition rules, stop and silently expire the active objective, clear its reference, and restore rate `8`.

## Verification

Source-level tests enforce the supported rates, compensation formula, objective-per-phase lifecycle, localization references, transition ordering, and game-over cleanup. The final SCAR source is checked against the AoE4 API index and the mod is exported with the Content Editor CLI. In-game validation remains necessary to confirm the native countdown and automatic slowed-phase recovery track approximately 15 real-world seconds.
