# Unit Family Identities Design

## Scope

Unit IDs used by `produce` and `units` represent gameplay unit families rather than one age-specific squad blueprint. A build-order author writes `spearman`, and the resulting check accepts every vetted Spearman tier available to the selected civilization.

This change does not alter entity, building, upgrade, or age-up identity resolution. It also does not alter how GRI-60 observes production queues/completions or how GRI-62 polls living squads.

## Problem

The current catalog maps each squad author ID to one canonical SCAR identifier. Official unit data often exposes one `baseId` with several age-tier `item_id` and `attribName` values. Consequently:

- YAML and objective text expose implementation IDs such as `spearman_1`;
- GRI-62 rejects a Feudal Spearman when its payload resolved to the Dark Age Spearman blueprint; and
- GRI-60 can reject a queued or completed member of the same gameplay family after an age-tier change.

Removing a trailing number in the compiler is not a safe solution. Numeric suffixes are not guaranteed to denote interchangeable age tiers, and the official data already supplies the authoritative family relationship through `baseId`.

## Catalog Schema

The committed identity catalog advances to schema version 2. Entity and upgrade categories retain their existing scalar identity behavior. Squad entries are grouped by normalized official `baseId` and contain:

```json
{
  "spearman": {
    "aliases": ["spearman", "spearman_1", "spearman_2", "spearman_3", "spearman_4"],
    "canonical_ids": [
      "unit_spearman_1_abb",
      "unit_spearman_2_abb",
      "unit_spearman_3_abb",
      "unit_spearman_4_abb"
    ]
  }
}
```

The generator derives the family key from official `baseId`, aliases from the normalized base ID and official item IDs, and canonical IDs from the corresponding `attribName` values. Lists are deduplicated and deterministically sorted.

Every alias within one civilization must resolve to exactly one family. Conflicting aliases, empty families, malformed normalized IDs, or duplicate aliases across families fail catalog generation/loading. The catalog contains identity information only; it does not add event, polling, capability, or detection-mechanism metadata.

## Catalog API

The loader exposes a squad-family resolution result containing:

- `family_id`: the normalized official base ID used for presentation;
- `canonical_ids`: a non-empty immutable tuple of canonical SCAR squad identifiers.

Both the family ID and its legacy age-specific aliases resolve to this same result. Thus existing YAML such as `spearman_1` remains valid but compiles with `spearman` presentation and family semantics. New and migrated YAML should use `spearman`.

Existing scalar resolution remains available for entity and upgrade categories. Calling scalar resolution for a multi-member squad family must not silently select one member.

## Compiler Contract

For `produce` and `units`, the compiler resolves the author ID as a squad family before constructing the title or runtime payload.

- Titles use `family_id`, humanized by replacing underscores with spaces.
- Runtime payloads contain `ids`, the complete list of canonical squad identifiers for that civilization and family.
- The YAML `count`, `constant`, and `queued` fields retain their current meanings.
- Author-facing or alias IDs are not emitted as runtime identity values.

Examples:

```text
units: [{id: spearman, count: 2}]
  -> Have 2 active spearman

produce: [{id: spearman, count: 2, queued: true}]
  -> Queue 2 spearmen
```

The existing catalog-safe unit-name inflection remains presentation-only. Canonical IDs and family membership never depend on English pluralization.

## Runtime Contract

GRI-60 and GRI-62 resolve every canonical payload ID with `BP_GetSquadBlueprint` during activation and cache the resulting PBG tuples.

Both handlers use structural PBG equality across:

- `PropertyBagGroupID`;
- `PropertyBagGroupModPackID`; and
- `PropertyBagGroupType`.

A squad or queue item matches when its PBG equals any cached family member.

GRI-60 retains its current event-driven behavior: human-owner command/completion filtering, named next-tick queue reconciliation, completion deduplication, cancellation reversal, and no periodic polling or unsupported `GE_BuildItemStart` dependency.

GRI-62 retains authoritative reversible polling. It enumerates only the bound human player's squads and verifies current ownership before family identity and alive-state checks. Opponent or converted-away squads never contribute.

## Migration and Compatibility

Repository and external validation build orders should migrate age-specific squad aliases to family IDs where the official catalog proves the relationship. The compiler continues accepting generated legacy aliases so existing build orders do not break immediately.

No heuristic suffix stripping is used for identity resolution. Units with distinct official base IDs remain distinct even if their names look related. Civilization-specific family membership is generated independently, so a canonical squad identifier from one civilization cannot satisfy another civilization's check.

## Testing

Catalog generation and loading tests cover:

- deterministic family and alias output from official rows;
- one-member families such as Scout;
- multi-tier families such as Spearman;
- alias-to-family resolution;
- alias conflicts and malformed family records; and
- unchanged entity/upgrade scalar resolution.

Compiler tests cover:

- family IDs and legacy aliases producing the same title and canonical `ids` payload;
- exact GRI-60 and GRI-62 title grammar;
- canonical member ordering; and
- unknown family errors at the exact YAML path.

Runtime contract and behavior tests cover:

- early- and later-age PBG members satisfying the same check;
- full three-field PBG comparison;
- multiple active descriptors;
- queue insertion/removal and completed production for any family member;
- reversible living-unit counts across family members;
- opponent and converted-away unit rejection; and
- unchanged observer/poll lifecycle cleanup.

Each issue branch receives its own static review. Subagents do not build the mod. The main thread builds GRI-60 and GRI-62 separately after their reviewed changes are ready, and the user validates both age-family behavior and displayed objective text.

## Rejected Alternatives

Suffix-based family inference was rejected because numeric suffixes do not reliably express gameplay-family equivalence.

A hand-maintained family override table was rejected because it duplicates official `baseId` relationships and is prone to incomplete civilization coverage.

Selecting one representative canonical blueprint was rejected because it recreates the current cross-age mismatch.
