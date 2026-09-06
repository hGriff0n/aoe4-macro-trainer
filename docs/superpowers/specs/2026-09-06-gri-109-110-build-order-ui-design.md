# GRI-109 and GRI-110 In-Game Build Order UI Design

## Context

This work implements GRI-109, the build-order selection screen shown at game start, and GRI-110, its in-game schema-driven build-order editor. The branch is based on PR #19 (`codex/gri-89-remove-bundled-path` at `082f4be`), where build orders are loaded only from the player's text datastore and the old bundled-build path has been removed.

The feature is local-player UI. It does not coordinate editor state or startup choices across multiplayer peers.

## Goals

- Pause on the next simulation tick and present a custom build-order selection screen at every game start.
- Let the player select a compatible stored build order, explicitly choose no build order, create a build order, or edit the selected build order.
- Provide a full single-column editor whose controls are derived from the build-order schema and operate on the runtime catalog as directly as practical.
- Discover civilization-appropriate buildings, units, technologies, and age-up options from the running game rather than from a bundled identity catalog.
- Persist create and edit operations by saving the complete modified runtime catalog.
- Track inferred age through the ordered steps so later selectors can omit choices unavailable in the build order's current age.

## Non-goals

- Restoring or extending the removed bundled build-order path.
- Persisting an author-YAML-shaped copy of each build order.
- Allowing the player to change civilization in the editor.
- Synchronizing the UI or its draft state between players.
- Adding an explicit delete-build-order workflow. Removing an old key during a rename is part of save, not a separate delete feature.
- Caching discovered game data across editor openings.

## User Flow

### Startup selection screen

After datastore loading completes, startup schedules the existing next-tick pause and opens a compact custom selector. The selector shows the local player's civilization and flag and lists only stored build orders whose `civ` matches that civilization. It also contains an explicit **No build order** entry.

The screen provides:

- **Edit**, enabled only when a stored order is selected;
- **Create**, which opens a blank editor draft for the current civilization;
- **Unpause**, which starts the selected order and the enabled gameplay cycle.

Unpausing with **No build order** selected requires confirmation. Declining keeps the selector open and the match paused. Confirming closes the UI and continues without starting the objective engine. The selection screen remains the only route that resumes the match.

If custom UI initialization fails, startup shows a minimal fallback error/confirmation dialog. It must allow the player either to remain paused or to continue without a build order, so an invisible or invalid UI cannot trap the match.

### Editor screen

Create or Edit replaces the selection screen; the game remains paused. The editor is a single scrollable column:

1. A sticky header shows the editable title, the read-only current civilization and flag, and the primary actions.
2. Build-order steps appear as reorderable, expandable cards.
3. Each expanded step contains its own reorderable, expandable check cards.
4. Add and delete controls progressively construct or remove steps, checks, objects, and list entries.

**Save** validates and persists the draft, returns to the selector, and selects the saved order. **Cancel** discards the draft and returns to the selector with its previous selection restored.

When editing an existing order, **Create copy** creates a new draft prepopulated from the original. Its initial title is `<title> (copy)`, or the next available numbered suffix such as `(copy 2)`. The copy has no original-ID association and does not modify the source order unless it is saved under a noncolliding ID.

## Architecture

The feature is divided into four modules with narrow responsibilities.

### Startup coordinator

`startup.scar` owns pausing, screen transitions, selected-order state, confirmation when no order is selected, objective-engine startup, and UI cleanup. It delegates rendering, editing, discovery, and persistence rather than embedding those concerns in the startup flow.

### Live discovery

A discovery module enumerates game property bags every time the editor opens. It produces a transient list used only by that editor instance; closing and reopening the editor performs discovery again.

The official APIs supporting this include:

- `BP_GetPropertyBagGroupCount` and `BP_GetPropertyBagGroupPathName` for enumerating property bags;
- `Player_GetRace` and the entity/squad race-extension APIs for civilization filtering;
- `BP_GetEntityUIInfo`, `BP_GetSquadUIInfo`, and `BP_GetUpgradeUIInfo` for display metadata;
- entity, squad, and upgrade type predicates and Cardinal type-to-blueprint helpers for category and age filtering; and
- `AI_CombatFitnessGetSquadArchetypeNames` and `AI_CombatFitnessGetSquadArchetypePBGs` for semantic unit-family grouping.

Each option exposed to the editor includes its canonical internal identifier or identifiers, kind, inferred minimum age, semantic family where applicable, localized display name, and icon reference. An item without usable age metadata is treated as Age I. An item without display information remains selectable and uses its internal ID as its label; a missing icon uses a neutral kind-specific placeholder. Discovery must not silently hide an otherwise valid civilization-compatible item solely because presentation metadata is missing.

The local civilization is always derived from `Player_GetRace(Game_GetLocalPlayer())`. It is displayed with its flag and is not editable.

### Schema-driven editor

The editor uses a declarative schema that describes primitive fields, enums, objects, optional fields, and lists. A recursive renderer maps those definitions to inline controls, expandable object cards, and vertically reorderable list cards. Check-specific game knowledge is supplied through field adapters rather than built into the recursive renderer.

Adapters provide:

- live building, technology, age-up, and unit-family selectors;
- a reusable alternative selector for `id`/`oneof` pairs;
- four simultaneous optional numeric inputs for `food`, `wood`, `gold`, and `stone` in `vils` and `resources` cards; and
- a separate four-resource multi-select for `vils.no_collect`.

The reusable alternatives adapter currently serves `built` and `age_up`. Exactly one selected option maps to `payload.id`; two or more map to the ordered `payload.oneof` array. Zero selections is invalid. The behavior is schema-driven so another check can adopt the same pair without bespoke UI logic.

Players select a semantic unit family, such as Spearman, rather than an age-specific unit variant. The adapter stores the runtime family payload containing the compatible canonical squad identifiers expected by the existing handlers.

### Catalog persistence

The existing `BUILD_ORDER_CATALOG` remains the single canonical stored model. It contains compiled runtime build orders, steps, and check descriptors. The editor maintains an isolated draft and a temporary presentation view; it does not persist a second author-format document.

Generic controls modify runtime descriptor fields directly where their shapes align. Presentation adapters translate the remaining structural differences:

- a villager card represents the aggregate resource-threshold descriptor plus any separate `no_collect` descriptors;
- a resources card represents the per-resource runtime descriptors;
- an alternatives control represents an `id` or `oneof` payload; and
- a unit selector represents the canonical unit-family identifier array.

Saving expands those presentation values into the ordinary runtime check descriptors and generates deterministic internal check IDs and titles. Cancel and UI close discard the isolated draft without mutating the catalog.

## Age Inference

Age inference is derived solely from ordered build-order steps:

1. The first step enters at Age I.
2. All selectors in a step use that step's entering age.
3. An `age_up` check increments the inferred age by one for the following step.
4. The age never advances in response to any other check.
5. Adding, deleting, or reordering steps recalculates every affected step immediately.
6. The inferred age is capped at the game's maximum supported age.

An `age_up` with either one `id` or multiple `oneof` choices still advances by exactly one age. All choices presented for that check must be valid ways for the current civilization to reach the same next age.

`Player_CanConstruct` may supplement discovery for the player's actual current age, but it cannot determine availability in hypothetical future steps while the match remains paused in Age I. Future-step filtering therefore uses property-bag type and age metadata.

## Save and Collision Semantics

Every editor draft records its `original_id` separately from editable content. The original ID is preserved throughout editing but is never blindly reused on save.

Save performs the following operations:

1. Validate the complete draft without mutating `BUILD_ORDER_CATALOG`.
2. Derive a fresh ID from the current civilization and normalized title.
3. Allow that ID when it equals `original_id`; this is a normal same-title edit and replaces its own entry.
4. If the derived ID differs, reject it only when it belongs to a different existing order.
5. Remove `original_id` when an edit was renamed.
6. Insert the validated runtime order under the derived ID.
7. Wrap the complete modified `BUILD_ORDER_CATALOG` with its datastore schema version and pass that whole table to `Game_StoreTableData`.
8. Persist that datastore with `Game_SaveTextDataStore`.

New and copied drafts have no `original_id`, so they cannot overwrite an existing order accidentally. Saving is never scoped to the recently created or edited order; create and edit mutate the in-memory catalog, then the entire catalog is stored and persisted.

The datastore APIs are fire-and-forget and expose no completion status. The UI may report successful validation and save dispatch, but it must not claim to have received a durability confirmation from the engine.

## Validation and Failure Handling

Save remains disabled while the draft is invalid. Errors appear beside the responsible field or card, and the draft remains intact. Validation covers at least:

- a nonempty normalized title;
- at least one step and at least one valid check per step;
- positive integer numeric fields when selected;
- nonempty required lists and alternative selections;
- mutually exclusive runtime `id` and `oneof` representations;
- live identifiers that resolve to the expected game-data kind;
- unit-family payloads containing at least one compatible canonical squad identifier; and
- collisions with a different catalog entry.

Datastore loading continues to skip invalid orders individually while retaining valid entries. A stored selection missing from current discovery remains visible using its saved internal ID, allowing the player to preserve or replace it. An empty discovery category displays an explicit empty state rather than silently removing the field.

All screens and pending rules are removed by the existing game-over cleanup path. Draft state, selection state, and discovery data are also cleared there.

## Testing and Verification

Automated contract and behavior tests will cover:

- the next-tick pause and the selector/editor/confirmation screen state transitions;
- civilization filtering and the explicit no-order choice;
- create, same-ID edit, rename, copy, collision rejection, cancellation, and automatic copy suffixes;
- whole-catalog storage and text-datastore persistence calls;
- recursive schema rendering contracts, nested step/check cards, ordering, add/delete, and Save/Cancel/Create copy commands;
- live option discovery, race and age filtering, missing-age fallback, missing-label fallback, and unit-family grouping;
- `id`/`oneof` conversion for both `built` and `age_up`;
- `vils`, `no_collect`, and `resources` presentation-to-runtime conversion;
- inferred age after adding, deleting, and reordering age-up steps; and
- fallback behavior when custom UI initialization fails.

Final verification consists of the full Python `unittest` suite, AoE4 MCP validation for every changed SCAR file, an AoE4 Content Editor package build, and an in-game checklist covering multiple civilizations, entity- and technology-based age-ups, selection, editing, persistence across sessions, and confirmed unpause without a selected order.
