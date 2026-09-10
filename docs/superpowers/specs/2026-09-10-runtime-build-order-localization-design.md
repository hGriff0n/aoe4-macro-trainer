# Runtime Build-Order Localization Design

## Context

The datastore compiler currently assembles English objective titles and stores them beside each check payload. The runtime then tries to convert those arbitrary strings to `LocString` values. PR #22 avoided that conversion for one Abbasid build order by mapping its exact English strings to dedicated locdb entries, but all other build orders fall back to `LOC(rawText)`. In a packaged game, that fallback can display the visible `LOC:` development prefix.

The exact-title map also makes localization depend on one build order's content. New or edited build orders cannot reuse it, even though each check already has a stable kind and normalized payload from which its title can be produced.

## Goals

- Generate all standard check titles from reusable localization templates at runtime.
- Resolve entity, squad, and upgrade names from the game's own localized UI data using canonical IDs already stored in check payloads.
- Preserve authored build-order names, custom step titles, and hints exactly as written.
- Stop storing compiler-generated check titles and generated step titles in the datastore.
- Give every build order identical display semantics without per-build-order localization entries.
- Remove the possibility of `LOC:` appearing in build-order objectives.

## Non-goals

- Maintaining schema-version-1 datastore compatibility.
- Translating authored build-order names, custom step titles, or hint text.
- Reintroducing the abandoned in-game build-order editor.
- Mutating packaged locdb entries at runtime. SCAR exposes no supported localization-entry setter, and external datastore compilation occurs after the mod is packaged.

## Ownership and Data Flow

The compiler remains responsible for syntax validation, semantic validation, and identity normalization. It converts author-facing aliases into the canonical entity, squad, and upgrade IDs required by runtime checks. It does not assemble player-facing check text.

Presentation moves to the SCAR check modules, beside the execution logic that already interprets each payload. Every registered handler may provide:

```lua
{
    formatTitle = Check_FormatTitle,
    activate = Check_Activate,
    deactivate = Check_Deactivate,
}
```

`objective_engine.scar` asks the handler for a `LocString` before calling `Obj_Create`. It then activates the handler as it does today. Hints register a presentation-only handler, eliminating the current misleading missing-handler log. The `optional` field remains completion-flow metadata; it does not cause the engine to add presentation text globally.

This is deliberately runtime inference rather than a datastore presentation recipe. The payload already encodes each formatting decision, and a second template/argument representation would duplicate that information.

## Datastore Schema Version 2

Schema version 2 removes `title` from checks:

```lua
{
    id = "rus-2tc:2:1",
    kind = "built",
    optional = false,
    payload = {
        count = 1,
        id = "ebps/races/rus/buildings/kremlin",
    },
}
```

Step records contain `title` only when the YAML author explicitly supplied one. If the field is absent, the runtime derives the title from the one-based step index using a localized `Step #%1COUNT%` template. This keeps generated step titles out of the datastore while retaining custom titles verbatim.

Build-order `title` remains required because it is authored selector content. Hint text remains in `payload.text`. No generated title exists in the Python model or serialized datastore.

The parser and runtime loader accept schema version 2 only. Existing datastores are regenerated rather than migrated.

## Localization Primitives

A shared SCAR helper layer provides the following operations:

- Wrap authored ANSI text with a generic `%1TEXT%` localization format instead of calling `LOC(rawText)`.
- Format generated step numbers with `Step #%1COUNT%`.
- Resolve an entity ID with `BP_GetEntityBlueprint` and `BP_GetEntityUIInfo(...).screenName`.
- Resolve a squad ID with `BP_GetSquadBlueprint` and `BP_GetSquadUIInfo(..., race).screenName`.
- Resolve an upgrade ID with `BP_GetUpgradeBlueprint` and `BP_GetUpgradeUIInfo(...).screenName`.
- Join localized allocation fragments with a localized separator template.
- Join localized alternative targets with a localized `or` template.
- Apply `[Optional] %1TEXT%` compositionally when a formatter's current copy explicitly labels the check optional.

The runtime uses localized `screenName` values directly. It must not round-trip them through `Loc_ToAnsi`, because doing so would discard the player's selected game language before formatting.

Squad-family payloads contain every canonical member ID for completion semantics. Presentation resolves the first member's `screenName`; members of a semantic family are expected to share the player-facing unit name.

Resource names and grammatical connective text live in the mod locdb. Numeric payload values are passed to `Loc_FormatText` as values rather than being rendered by Python.

## Check Formatting

Each check module implements the formats it owns while preserving current display semantics:

- `resources`: `Collect at least %1COUNT% %2RESOURCE%`
- `vils`: `Assign %1ALLOCATIONS%` or `No %1RESOURCE% villagers`
- `rallypoint`: `Rally to %1RESOURCE%`
- `built`: `Build %1TARGET%` for one target or `Build %1COUNT% %2TARGET%` for a larger count
- `age_up`: `Age Up: %1TARGET%`; `payload.trigger` selects entity UI data for construction-based age-ups and upgrade UI data for upgrade-based age-ups
- `upgrades`: `Research %1UPGRADE%` or `Queue %1UPGRADE% for research`
- `produce`: `Produce %1COUNT% %2UNIT%`, `Queue %1COUNT% %2UNIT%`, or `Constantly produce %1UNIT%`
- `buildings`: the localized building name alone, matching current behavior
- `units`: `Have %1COUNT% active %2UNIT%`
- `hints`: `[HINT] %1TEXT%`

Authored custom step titles use the generic raw-text wrapper. Generated step titles use the numbered template. Build-order names remain authored strings in the selector, whose UI already accepts them directly.

Localized target-list and allocation-list helpers support variable input sizes by composing two-value localized join templates recursively. This avoids dynamic locdb slot allocation and avoids assembling English separators in SCAR.

## Failure Behavior

The compiler continues to reject unknown identities, so missing runtime blueprints should normally indicate a game-data mismatch. If blueprint lookup, UI-info lookup, or `screenName` resolution fails, the formatter:

1. Logs the check kind and canonical ID for diagnosis.
2. Displays the canonical ID through the safe raw-text wrapper.
3. Never calls `LOC` on arbitrary text.

If a registered check kind lacks `formatTitle`, the objective engine logs the configuration error and uses a static localized unavailable-check title. Required checks retain their normal completion behavior; presentation failure does not silently alter execution semantics.

## Locdb Changes

The exact-English lookup table is removed. Existing Abbasid-specific locdb IDs 143 through 172 are reassigned as reusable template slots where possible, adding new IDs only if the complete generic set exceeds those 30 entries. The reusable entries cover:

- raw authored text, custom steps, generated steps, hints, and optional checks;
- resource names, resource-count fragments, allocation joins, and alternative joins;
- every action variant listed in Check Formatting;
- invalid or unavailable presentation fallbacks.

The English locdb provides the current English wording. Other language locdb files can translate the templates independently, while game object names come from the base game's localization.

## Verification

Tests will be written before implementation changes and will cover:

- schema-version-2 serialization and strict parsing;
- absence of check titles and generated step titles in serialized data;
- preservation of build-order titles, custom step titles, and hint payload text;
- every formatter branch, including optional, queued, constant-production, no-collect, and alternative-target variants;
- entity, squad, and upgrade `screenName` resolution without `Loc_ToAnsi`;
- generated step numbering and raw custom-title/hint wrappers;
- invalid-ID and missing-formatter fallbacks;
- removal of the Abbasid exact-title map and `LOC(rawText)` fallback.

End-to-end verification compiles the real build-order directory into a fresh schema-version-2 datastore, runs the complete automated test suite, builds the `.aoe4mod` package, and verifies both a formerly mapped Abbasid order and an unmapped Rus order in game.
