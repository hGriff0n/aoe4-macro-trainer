# Objective Title Localization Design

## Problem

The phase objectives currently pass `$4` and `$5` as their titles. Those are incomplete localization references: AoE4 mod-local strings require the mod's compact GUID namespace as well as the numeric string ID. The objective UI therefore renders `$4 No Key` instead of `NORMAL`, and similarly cannot resolve the paused-phase title.

## Approaches Considered

1. Use fully qualified mod localization keys. Pass `$dfb5645698a84afb91cf7a2dfb0f4a4e:4` for `NORMAL` and `$dfb5645698a84afb91cf7a2dfb0f4a4e:5` for `PAUSED`. This preserves the existing locdb entries and supports future translations. This is the selected approach.
2. Pass literal `NORMAL` and `PAUSED` strings. This would fix English rendering but bypass the mod's localization database.
3. Add a helper that creates ad hoc localized-string tables from literal text. This adds unnecessary code and still does not use the translation database.

## Design

Define named constants for the two fully qualified localization keys near the existing phase constants. Phase-transition functions pass those constants to `Mod_StartPhase`; objective lifecycle and timing behavior remain unchanged.

Screen positioning is explicitly out of scope. The mod will continue using AoE4's native objective UI and respect the placement selected by the player's HUD mode. Follow-up issue GRI-49 owns investigation of native placement controls.

## Validation

Update the SCAR contract tests first so they require the fully qualified keys and reject the bare `$4` and `$5` references. Run the focused test suite before and after the implementation. An in-game check should confirm that the two phases display `NORMAL` and `PAUSED`, without `No Key`, while their existing countdowns continue to work.
