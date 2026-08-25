# Build-Order Objectives Framework Design

## Scope

Implement Linear issue GRI-71 and its five direct sub-issues:

- GRI-66: basic build-order objective framework;
- GRI-67: YAML-to-SCAR build and packaging script;
- GRI-68: bundled build-order lobby setting;
- GRI-69: invalid build-order startup handling; and
- GRI-72: setting to disable the slow/normal simulation-rate cycle.

GRI-55 through GRI-64 remain downstream work. They will provide production handlers for individual check types. This design defines the data and runtime interfaces those handlers consume, but does not implement their game-state predicates.

Build-order training is single-player for this milestone. Separating it from the simulation-rate mod and supporting multiplayer build-order selection are out of scope.

## Existing Systems

The existing GRI-23/GRI-38 settings implementation is the baseline for reading win-condition options. GRI-72 adds a setting to that system; it does not replace or complete GRI-23/GRI-38.

The simulation-rate loop and build-order engine remain independent runtime systems. Either may run without the other. The only coordination occurs during startup when an invalid build-order selection temporarily pauses the match before enabled systems begin.

## Authoritative Inputs and Generated Outputs

YAML is the authoritative build-order format and the normal user-facing editing surface. A configurable input directory may contain any number of `.yaml` or `.yml` files. Each file may contain one build-order mapping or a list of mappings.

The repository stores:

- the YAML schema and build-order YAML sources;
- the build script and compiler modules;
- baseline RDO and localization templates representing a mod with no bundled build orders;
- stable SCAR runtime modules; and
- tests and fixtures.

The repository does not store generated production outputs. The live RDO, localization CSV, and generated SCAR catalog are local build products and are ignored by Git.

Every build invocation follows this order:

1. Replace all generated outputs with pristine copies of the checked-in no-build-order baselines.
2. Discover input files in deterministic path order.
3. Parse and validate every YAML document in memory.
4. Construct one canonical build-order catalog.
5. Atomically emit the full SCAR catalog, RDO enumeration, and localization CSV.
6. Invoke the Essence CLI only after successful generation.
7. Leave the generated inputs in place for local inspection and use.

There is no incremental parse or emission shortcut. Resetting first guarantees that deleted or renamed YAML entries cannot survive from a previous build.

If parsing or validation fails, generation does not proceed and the live outputs remain in their no-build-order baseline state. If Essence fails, the script returns a nonzero result, does not report a successful or fresh mod package, and leaves the generated inputs available for diagnosis.

## YAML Schema

Each build order requires:

- `civ`: the game civilization identifier;
- `title`: the player-facing build-order title; and
- `steps`: an ordered list of step mappings.

Each step may contain an optional `title`. A supplied title is rendered exactly as written. An untitled step falls back to `Step N`, where `N` is its one-based position.

Build orders do not require an author-supplied ID. The compiler generates a deterministic internal slug from normalized `civ` and `title`, such as `english-2-tc`. A collision between generated IDs is a validation error. Renaming a title intentionally changes the generated identifier.

The compiler accepts the documented check fields, including fields marked experimental. It validates mapping/list shapes, scalar types, positive counts, supported resource names, and mutually exclusive alternatives such as `id` versus `oneof`. Unknown fields are errors rather than silently ignored.

The compiler preserves:

- YAML file order after deterministic path sorting;
- build-order order within list documents;
- step order;
- check-field order within each step; and
- list order within each check.

Each check becomes a canonical descriptor containing:

- a type-independent presentation descriptor for its child objective;
- the typed configuration payload consumed by a future handler; and
- required or optional metadata when supported by the source schema.

The compiler generates English localization rows for build-order titles, step titles, settings entries, errors, buttons, and check presentation text. Game identifiers remain intact in typed payloads so future handlers can resolve official localized names or icons.

All validation diagnostics identify the source file and the YAML path of the invalid value.

## Generated Lobby Settings

The build-order setting is a static RDO enumeration. Its default item is `none`, which represents no selected build order. Generated build-order items are ordered by normalized civilization and title. Because the native lobby UI cannot dynamically group or filter enumeration items by civilization, item labels use a prefix such as `[English] 2 TC`.

GRI-72 adds a separate Boolean setting named for enabling the slow/normal cycle. It defaults to enabled to preserve the existing mod behavior.

The startup code reads both settings through the existing GRI-23/GRI-38 settings path. The build-order selector is host-configured, but build-order behavior is explicitly single-player in this milestone.

## Startup State Matrix

The two settings are evaluated independently:

| Build-order selection | Civilization | Sim-rate cycle | Result |
| --- | --- | --- | --- |
| Valid build | Matches | Enabled | Start build-order objectives and the sim-rate cycle. |
| Valid build | Matches | Disabled | Start only build-order objectives at normal speed. |
| `none` | N/A | Enabled | Start only the sim-rate cycle without an alert. |
| `none` | N/A | Disabled | Pause, explain that no system is enabled, then continue at normal speed with neither system. |
| Valid build | Mismatch | Enabled | Pause, disable only build-order progression, then start the sim-rate cycle after dismissal. |
| Valid build | Mismatch | Disabled | Pause, disable build-order progression, then continue at normal speed with neither system. |

An invalid build order never ends the match. The player may quit through the normal game UI.

## Error Message and Pause Lifecycle

Configuration errors use the native message-box API rather than a custom XAML view or an objective popup. Startup resets/configures the message box and displays one enabled button labeled `Continue Without Build Order` while the simulation is still running. It then schedules a self-removing rule that sets the simulation rate to `0` on the next simulation tick if the alert remains open, allowing the UI time to create the modal.

The civilization mismatch message names the selected build order, its required civilization, and the player's actual civilization. The no-selection message explains that neither a build order nor the sim-rate cycle was enabled.

The message-box callback:

1. ignores duplicate invocation;
2. closes or resets the message box as required by the native API;
3. cancels any pending startup-pause callback;
4. restores the normal simulation rate; and
5. starts the sim-rate cycle only when that setting is enabled.

Build-order initialization is permanently disabled for that match after either configuration error. Error handling does not disable or mutate the sim-rate setting itself.

## Generated Runtime Catalog

The generated SCAR catalog is data-only. It maps each generated build-order ID to normalized metadata and ordered step/check descriptors. It does not parse YAML, inspect lobby state, create objectives, or evaluate game state.

The stable runtime catalog module exposes lookup and iteration operations without exposing generation details. Runtime consumers treat a missing selected ID as invalid generated/configuration state and route it through the same build-order-disabled error path.

## Objective Engine

The build-order engine renders only the active step:

- one normal primary objective for the step; and
- normal secondary child objectives for each compiled check descriptor.

It does not use warning objectives or warning icons. A titled step uses its title verbatim; an untitled step uses `Step N`.

The engine owns:

- selected build and active-step state;
- creation and cleanup of the active objective hierarchy;
- handler registration by check type;
- handler activation and deactivation;
- completion notifications;
- protection against duplicate advancement; and
- transition to the next ordered step when all required children complete.

Handlers receive the canonical check payload, its presentation descriptor, the relevant objective ID, and active-step context. They may subscribe to events, register polling rules, update presentation, and notify the engine when complete. The engine, not a handler, decides when the step advances.

No production check handlers are part of GRI-71. Descriptors without registered handlers remain visible and pending; they do not crash, complete, or advance the step. Tests register a fake handler to verify activation, completion, advancement, and cleanup.

Optional descriptors do not block advancement once production optional-check behavior is implemented. Until the corresponding handler issue lands, they remain visible and pending without affecting the fake-handler lifecycle tests.

## Component Boundaries

- **Build orchestrator:** resets outputs, calls the compiler and emitters, invokes Essence, and reports build success or failure.
- **Compiler:** parses YAML, validates it, normalizes values, generates IDs, and constructs canonical in-memory data.
- **SCAR emitter:** writes the data-only runtime catalog.
- **RDO emitter:** adds the complete static build-order enumeration to the baseline settings template.
- **Localization emitter:** appends deterministic generated English rows to the baseline localization template.
- **Runtime catalog:** provides stable lookup of generated data.
- **Objective engine:** renders active objectives and coordinates handler lifecycle and advancement.
- **Startup coordinator:** reads settings, validates the selected build and civilization, owns configuration-error pause/resume, and starts enabled systems.
- **Sim-rate controller:** owns only phase timing, objectives, speed changes, and its own cleanup.

These boundaries keep user-authored data and generation logic outside the gameplay runtime, and keep future check implementations independent from selection, rendering, and step progression.

## Failure Handling

The build script fails before invoking Essence for malformed YAML, duplicate generated IDs, invalid schema values, missing templates, or emission failures. File emission uses temporary sibling files followed by atomic replacement so consumers never observe partially written generated files.

An Essence nonzero exit, missing expected package, or package that is not fresh for the current invocation is a build failure. The script must not print a success message or treat a stale prior package as the result of the current build.

At runtime, unknown selected IDs, missing catalog data, no-selection with the cycle disabled, and civilization mismatches disable only the build-order engine and use the message-box flow. Objective or callback cleanup is idempotent so game-over handling is safe from every startup state.

## Testing and Validation

Compiler tests cover:

- single-object and list documents;
- deterministic file and in-document ordering;
- generated-ID normalization and collision detection;
- optional step titles and untitled fallbacks;
- every documented schema shape;
- strict unknown-field rejection;
- source-file and YAML-path diagnostics;
- reset-before-parse behavior; and
- baseline preservation after failed validation.

Emitter tests use temporary directories and verify complete deterministic SCAR, RDO, and localization output without committing production-generated files. They also verify that removed YAML input cannot survive a later invocation.

SCAR contract tests cover:

- reading both settings through the existing settings infrastructure;
- every row of the startup state matrix;
- rate-zero pause and one-button message-box setup;
- idempotent callback behavior and correct resume path;
- independent build-order and sim-rate startup;
- primary/secondary objective hierarchy;
- exact titled-step and fallback-title behavior;
- pending behavior for missing production handlers;
- fake-handler activation, completion, advancement, and cleanup; and
- game-over cleanup from normal, paused, and disabled states.

The complete SCAR source is checked against the AoE4 API references for unknown or low-confidence calls and missing localization keys. A successful end-to-end run must produce a fresh package through the Essence CLI.

Manual playtesting covers:

- valid matching selection with the cycle enabled and disabled;
- no selection with the cycle enabled and disabled;
- civilization mismatch with the cycle enabled and disabled;
- reading and dismissing the paused message box;
- active-step and child-objective layout in supported HUD modes; and
- normal game-over cleanup.

## Implementation and Integration Strategy

Implementation uses isolated Git worktrees and subagent-driven review cycles. Work proceeds in dependency order:

1. GRI-67 establishes templates, compiler, emitters, and the generated catalog contract.
2. GRI-66 implements the objective engine against that contract.
3. GRI-68 adds generated build-order enumeration entries and selection lookup.
4. GRI-72 adds the independent sim-rate enable/disable setting.
5. GRI-69 integrates the startup matrix, validation, native message box, pause, and resume behavior.

An issue receives its own worktree, implementation agent, requirements review, and code-quality review. Independent tasks may run concurrently only when their file ownership is disjoint. Each dependency is integrated and verified before dependent worktrees are created, avoiding parallel edits to the same RDO template, localization template, or startup SCAR code.

After all five issues are integrated, the parent branch runs the full compiler, SCAR, API-validation, Essence-build, and manual-playtest handoff checks before GRI-71 is considered complete.
