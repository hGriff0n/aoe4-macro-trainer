# Game Identity Catalog Design

## Scope

Add a committed, generated catalog of Age of Empires IV buildings, units, and upgrades. Build-order YAML continues to use concise human-readable identifiers, while the build-order compiler validates each identifier for the selected civilization and emits the canonical identifier accepted by SCAR's blueprint lookup functions.

The catalog is shared infrastructure for GRI-83. It also removes the temporary `age_up.capability` field introduced on the GRI-57 branch. Age-up detection is selected from the build order's civilization instead of author-supplied mechanism metadata.

## Goals

- Keep build-order YAML readable and independent of numeric PBG IDs.
- Reject unknown, wrong-category, wrong-civilization, and ambiguous identifiers before SCAR generation.
- Resolve one human-readable identifier differently for different civilizations when their canonical blueprints differ.
- Let SCAR resolve canonical identifiers to engine-owned PBG tuples with `BP_GetEntityBlueprint`, `BP_GetSquadBlueprint`, or `BP_GetUpgradeBlueprint`.
- Keep normal builds reproducible and independent of a sibling repository, live MCP server, or local game-data database.
- Keep event-versus-polling decisions out of the identity catalog.

## Non-Goals

- The catalog does not decide how an objective is detected.
- The catalog does not expose a YAML `capability`, blueprint category, PBG number, or civilization override.
- Normal mod builds do not refresh the catalog automatically.
- Localization, icons, balance values, costs, and other game metadata are not included unless a later issue gives them an explicit consumer.

## YAML Contract

Authors continue to use human-readable IDs:

```yaml
civ: abbasid
title: Example
steps:
  - age_up:
      id: economic_wing
  - produce:
      id: scout
      count: 2
  - upgrades:
      - id: wheelbarrow
```

`id` and every value in `oneof` use the same catalog-backed validation. IDs are case-sensitive normalized slugs using lowercase ASCII and underscores. The compiler does not accept raw PBG integers or author-supplied canonical `attribName` values as a bypass.

The compiler and catalog do not provide aliases for earlier guessed shorthand IDs. Existing build-order sources are migrated to normalized official base IDs; for example, `hospitallers` becomes `knights_hospitaller` and `antioch` becomes `principality_of_antioch`.

The schema contains no `capability` field. A build order never describes whether its age-up is a landmark, an upgrade, or some other engine mechanism.

## Committed Catalog

The generated catalog is committed under the build-order tooling so tests and builds can load it without external state. Its logical key is:

```text
(build-order civilization, blueprint category, human-readable ID)
```

The three supported categories are:

- `entity`: buildings and conventional landmarks resolved with `BP_GetEntityBlueprint`;
- `squad`: produced or currently controlled units resolved with `BP_GetSquadBlueprint`; and
- `upgrade`: technologies and upgrade-based age-ups resolved with `BP_GetUpgradeBlueprint`.

Each leaf contains only the canonical SCAR lookup string. The human-readable key is the official `baseId` normalized from kebab case to the underscore form already used by build-order YAML; for example, `town-center` becomes `town_center`. For example, the human-readable unit ID `scout` can resolve to a different civilization-specific `unit_scout_...` identifier for each civilization. Content shared by multiple civilizations is expanded under each applicable civilization during generation rather than relying on runtime fallback rules.

The serialized file has a schema version and deterministic source metadata followed by sorted civilization, category, and ID mappings. Source timestamps and machine-specific paths are excluded so identical source data produces a byte-identical file.

Duplicate keys with different canonical identifiers are generation errors, including collisions introduced by ID normalization. All official building, unit, and technology records assigned to a supported playable civilization must be represented. A relevant base-data entry that lacks a civilization, category, human-readable base ID, or canonical SCAR identifier fails refresh; it is never skipped or guessed into the catalog. Records outside those three categories or outside supported playable civilizations are not build-order identities and are excluded.

## Catalog Refresh

An explicit developer command reads the official base-data records exposed by the local AoE4 data tooling and regenerates the committed catalog. The refresh adapter consumes the source fields equivalent to:

- normalized `baseId` as the human-readable ID;
- `attribName` as the canonical SCAR identifier;
- `civs` as the applicable civilization codes; and
- the source category/type as entity, squad, or upgrade.

A small committed civilization map translates official short codes to the build-order civilization IDs used by `Player_GetRaceName` and the YAML schema. Unknown civilization codes fail refresh with a diagnostic so newly added civilizations cannot be silently omitted.

Refresh validates the complete generated structure before replacing the committed file. Normal compile and build commands only read the committed catalog. They fail clearly if the file is missing, malformed, or has an unsupported schema version.

## Compiler Resolution

The compiler loads the catalog once for a directory compilation. It first parses the build-order civilization, then validates each objective identifier using a category selected by objective semantics:

| Objective | Catalog category |
| --- | --- |
| `built` and `buildings` | `entity` |
| `produce` and `units` | `squad` |
| `upgrades` | `upgrade` |
| `age_up` | civilization-selected `entity` or `upgrade` |

Age-up category selection is a static compiler rule keyed by build-order civilization. Abbasids, Ayyubids, Templars, and Golden Horde use the upgrade category; conventional landmark civilizations use the entity category. The exact strings in this rule are the same canonical civilization IDs accepted by the compiler and emitted into `BUILD_ORDER_CATALOG`.

The compiler resolves each YAML `id` or `oneof` item independently and writes its canonical SCAR identifier into the existing descriptor payload. No extra runtime identity record and no `capability` value are emitted.

A validation failure reports the source file, precise YAML path, build-order civilization, objective kind, expected catalog category, and rejected human-readable ID. The compiler distinguishes an unknown civilization from an identifier that is unknown for an otherwise valid civilization.

## Runtime Contract

`BuildOrder_Start` retains the selected build record, whose `civ` field is the authoritative civilization ID for objective behavior. The objective-engine context exposes that value to handlers as `context.civ`; handlers continue to use `context.localPlayer` as the only authoritative player handle.

Handlers resolve the compiler-emitted canonical IDs during activation and retain the resulting PBG tuples in per-check state. Event callbacks compare those tuples and still verify that the event belongs to the human player before completing an objective.

The age-up handler selects its adapter from `context.civ`:

- upgrade-age civilizations subscribe to the verified human-player upgrade-completion signal and compare `BP_GetUpgradeBlueprint` tuples;
- conventional landmark civilizations subscribe to the verified human-player construction-completion signal and compare `BP_GetEntityBlueprint` tuples.

The civilization-to-adapter table is runtime behavior and remains in `age_up.scar`, not in the identity catalog or YAML. Unsupported civilizations fail closed: the required objective remains incomplete and a diagnostic is logged. There is no `non_building` auto-optional path and no capability-based dispatch.

## GRI-57 Migration

The GRI-57 branch removes `capability` from:

- `docs/build_order_schema.yaml`;
- compiler permitted fields and payload construction;
- generated descriptor expectations;
- runtime state and adapter dispatch; and
- focused tests and fixtures.

Normalized human-readable IDs such as `economic_wing`, `knights_hospitaller`, and `khan_and_torguuds` are resolved through the catalog using their build order's civilization. Incorrect test fixtures must set the intended civilization rather than override detection through YAML.

Any established shorthand that is not the normalized official base ID is updated at its source rather than retained as a catalog alias. GRI-57 fixtures therefore use `knights_hospitaller`, `principality_of_antioch`, and the other normalized IDs emitted by the catalog generator.

Catalog validation also exposes category mistakes rather than masking them. Templar age selections such as `knights_hospitaller` are upgrades, not buildings, so redundant `built` checks for those selections are removed. A Templar `age_up` check previously used for `town_center` construction is migrated to a `built` check because `town_center` is an entity identity, not an upgrade identity.

## Error Handling

Catalog errors are build-time failures. The compiler does not emit unresolved human IDs, silently choose the first ambiguous record, or fall back to another civilization.

Runtime lookup failures are defensive errors for stale or corrupt generated data. A handler logs the check ID, civilization, objective kind, and canonical identifier, leaves the check incomplete, and avoids registering a callback that can never match.

All player filters remain mandatory. Identity resolution cannot weaken the GRI-83 requirement that opponent actions never mutate human objectives.

## Testing

Catalog tests cover deterministic serialization, source-category conversion, civilization mapping, shared IDs, per-civilization canonical IDs, duplicate conflicts, incomplete source rows, and unknown civilization codes.

Compiler tests cover each objective-to-category mapping; `id` and `oneof`; shared human IDs resolving differently by civilization; unknown civilization, identifier, and category errors; exact YAML paths; canonical payload emission; malformed or incompatible catalog files; and rejection of `capability`.

Runtime contract tests require `context.civ`, civilization-based age-up dispatch, the appropriate `BP_Get*Blueprint` call, cached PBG comparison, human-player filtering, unsupported-civilization failure, and absence of capability dispatch.

The full Python suite runs on the common base and on every updated issue branch. Sub-agents continue to queue Content Editor validation through the main task and do not build their worktrees proactively.

## Rollout

The catalog loader, generator, compiler validation, engine context addition, schema documentation, and shared tests land on `codex/gri-83-objective-checks`. Check branches then incorporate that common-base commit and update their focused expectations. GRI-57 additionally replaces capability dispatch with civilization dispatch for Abbasids, Ayyubids, Templars, Golden Horde, and conventional landmark civilizations.

No combined suite-to-main PR or event-probe PR is created as part of this work. Existing per-check PRs continue to target the common GRI-83 base.

## Alternatives Rejected

Compiling numeric PBG IDs was rejected because it couples generated output to a particular game-data version and makes payloads opaque. Generating a complete SCAR-side identity catalog was rejected because the engine already owns canonical blueprint resolution. Refreshing on every build was rejected because it makes builds depend on external local state. Author-supplied capability metadata was rejected because detection is determined by civilization and does not belong in build-order content.
