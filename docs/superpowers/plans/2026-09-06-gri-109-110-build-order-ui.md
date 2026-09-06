# GRI-109 and GRI-110 In-Game Build Order UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the startup message-box chooser with a paused, local-player build-order selector and a single-column schema-driven editor backed by live AoE4 discovery and whole-catalog datastore persistence.

**Architecture:** Keep `BUILD_ORDER_CATALOG` as the only persisted representation. Add focused SCAR modules for live discovery, draft/runtime conversion and validation, schema-to-view projection, and XAML UI; keep `startup.scar` as the screen-state coordinator and `datastore.scar` as the sole persistence boundary.

**Tech Stack:** AoE4 SCAR/Lua, inline WPFG/XAML through `XamlPresenter`, official `UI_CreateDataContext`/`UI_CreateCommand` bindings, Python 3 `unittest` source-contract tests, AoE4 MCP validation, AoE4 Content Editor CLI.

**Spec:** `docs/superpowers/specs/2026-09-06-gri-109-110-build-order-ui-design.md`

## Global Constraints

- Base all work on PR #19 head `082f4be321ba2e1bc5143a23bd0bc1e131d682f7`.
- Keep the UI and its draft state local to `Game_GetLocalPlayer()`; add no network events.
- Keep `BUILD_ORDER_CATALOG` as the only persisted build-order representation.
- Enumerate live game data every time the editor opens; retain no discovery cache after editor close.
- Treat missing age metadata as Age I and missing display text as the internal PBG/path ID.
- Derive civilization from the local player and display it read-only with its flag.
- Represent unit choices as semantic families containing canonical age-variant squad IDs.
- Apply `id` for one alternative and ordered `oneof` for two or more alternatives.
- Render `food`, `wood`, `gold`, and `stone` together for `vils` and `resources`; each numeric value is either a positive integer or unselected.
- Start inferred age at I and increment only for steps following an `age_up` check.
- Persist the complete modified catalog with `Game_StoreTableData` followed by `Game_SaveTextDataStore`.
- Do not push or open a pull request; keep the branch local.

---

### Task 1: Whole-Catalog Datastore Mutation and Persistence

**Files:**
- Modify: `assets/scar/build_orders/datastore.scar`
- Modify: `tests/test_build_order_datastore.py`

**Interfaces:**
- Consumes: global `BUILD_ORDER_CATALOG`, `BUILD_ORDER_DATASTORE_ID`, and `BUILD_ORDER_DATASTORE_SCHEMA_VERSION`.
- Produces: `BuildOrderDatastore_Apply(originalID, newID, buildOrder) -> Boolean, String`; `BuildOrderDatastore_SaveCatalog() -> nil`.

- [ ] **Step 1: Write failing datastore mutation tests**

Add contract tests asserting that `BuildOrderDatastore_Apply` rejects invalid orders and collisions owned by another record, allows `newID == originalID`, removes a renamed `originalID`, inserts `newID`, and invokes one whole-catalog save. Assert that `BuildOrderDatastore_SaveCatalog` stores this exact root shape before saving it:

```lua
{
    schema_version = BUILD_ORDER_DATASTORE_SCHEMA_VERSION,
    build_orders = BUILD_ORDER_CATALOG,
}
```

Also assert the ordered calls:

```lua
Game_StoreTableData(BUILD_ORDER_DATASTORE_ID, stored)
Game_SaveTextDataStore(BUILD_ORDER_DATASTORE_ID, "")
```

- [ ] **Step 2: Run the focused test and confirm red**

Run: `python -m unittest tests.test_build_order_datastore -v`

Expected: FAIL because `BuildOrderDatastore_Apply` and `BuildOrderDatastore_SaveCatalog` do not exist.

- [ ] **Step 3: Implement the minimal persistence boundary**

Implement validation before mutation and identity-aware collision handling:

```lua
function BuildOrderDatastore_Apply(originalID, newID, buildOrder)
    if not BuildOrderDatastore_IsValidOrder(newID, buildOrder) then
        return false, "invalid_build_order"
    end
    if BUILD_ORDER_CATALOG[newID] ~= nil and newID ~= originalID then
        return false, "id_collision"
    end
    if originalID ~= nil and originalID ~= newID then
        BUILD_ORDER_CATALOG[originalID] = nil
    end
    BUILD_ORDER_CATALOG[newID] = buildOrder
    BuildOrderDatastore_SaveCatalog()
    return true, ""
end
```

`BuildOrderDatastore_SaveCatalog` must pass the complete live catalog to both official datastore APIs; it must not build a delta containing only the edited record.

- [ ] **Step 4: Run focused and full tests**

Run: `python -m unittest tests.test_build_order_datastore -v`

Run: `python -m unittest discover -s tests -p "test_*.py" -v`

Expected: PASS, 275 existing tests plus the new datastore tests.

- [ ] **Step 5: Commit**

```bash
git add assets/scar/build_orders/datastore.scar tests/test_build_order_datastore.py
git commit -m "feat: persist build order catalog edits"
```

---

### Task 2: Live Civilization-Aware Game Data Discovery

**Files:**
- Create: `assets/scar/build_orders/editor_discovery.scar`
- Create: `tests/test_build_order_editor_discovery.py`

**Interfaces:**
- Consumes: a `Player` from `Game_GetLocalPlayer()` and official PBG/race/UI-info APIs.
- Produces: `BuildOrderDiscovery_Collect(player) -> DiscoverySnapshot`; `BuildOrderDiscovery_Filter(snapshot, kind, maximumAge) -> Option[]`; `BuildOrderDiscovery_Clear() -> nil`.
- `DiscoverySnapshot` contains `civ`, `civ_name`, `entities`, `squads`, `upgrades`, and `families`.
- Each option contains `id`, `ids`, `kind`, `age`, `label`, and `icon`; scalar records use `id`, unit-family records use ordered `ids`.

- [ ] **Step 1: Write failing discovery contract tests**

Assert that collection enumerates `PBG_EntityProperties`, `PBG_SquadProperties`, and `PBG_UpgradeProperties` with `BP_GetPropertyBagGroupCount` and `BP_GetPropertyBagGroupPathName`; filters entity and squad records through their race-extension APIs; reads labels/icons through the three `BP_Get*UIInfo` functions; groups squads with `AI_CombatFitnessGetSquadArchetypeNames` and `AI_CombatFitnessGetSquadArchetypePBGs`; and sorts every option list by case-insensitive label then ID.

Assert explicit fallbacks:

```lua
age = discoveredAge or 1
label = discoveredLabel or pathName
icon = discoveredIcon or BUILD_ORDER_DISCOVERY_DEFAULT_ICONS[kind]
```

Assert `BuildOrderDiscovery_Filter` retains records with `option.age <= maximumAge` and that `BuildOrderDiscovery_Clear` releases the transient snapshot.

- [ ] **Step 2: Run the focused test and confirm red**

Run: `python -m unittest tests.test_build_order_editor_discovery -v`

Expected: FAIL because `editor_discovery.scar` does not exist.

- [ ] **Step 3: Implement enumeration, metadata normalization, and filtering**

Use small helpers with these signatures:

```lua
BuildOrderDiscovery_GetAge(kind, pathName, pbg) -> Integer
BuildOrderDiscovery_GetPresentation(kind, pathName, pbg, race) -> String, String
BuildOrderDiscovery_BelongsToRace(kind, pathName, race) -> Boolean
BuildOrderDiscovery_CollectFamilies(snapshot, player, race) -> Option[]
BuildOrderDiscovery_Sort(options) -> nil
```

Age detection must use official type/category predicates confirmed by the AoE4 MCP. `Player_CanConstruct` may supplement actual-current-age filtering but must not be the basis for future inferred ages. Family options must contain every compatible canonical squad PBG path for the archetype and expose one semantic family label.

- [ ] **Step 4: Validate APIs and run tests**

Run: `python -m unittest tests.test_build_order_editor_discovery -v`

Run the AoE4 MCP `check_code` tool on the complete contents of `assets/scar/build_orders/editor_discovery.scar`; resolve every unknown call or document an official-wrapper result in the test module.

Expected: focused tests PASS and MCP returns no unknown production API calls.

- [ ] **Step 5: Commit**

```bash
git add assets/scar/build_orders/editor_discovery.scar tests/test_build_order_editor_discovery.py
git commit -m "feat: discover live build order options"
```

---

### Task 3: Runtime Draft Model, Schema Adapters, and Age Inference

**Files:**
- Create: `assets/scar/build_orders/editor_model.scar`
- Create: `assets/scar/build_orders/editor_schema.scar`
- Create: `tests/test_build_order_editor_model.py`

**Interfaces:**
- Consumes: runtime build-order records and a `DiscoverySnapshot` from Task 2.
- Produces: `BuildOrderEditor_NewDraft(civ)`, `BuildOrderEditor_EditDraft(order)`, `BuildOrderEditor_CopyDraft(order, catalog)`, `BuildOrderEditor_InferAges(draft)`, `BuildOrderEditor_Validate(draft, discovery)`, and `BuildOrderEditor_ToRuntime(draft)`.
- Produces reusable helpers `BuildOrderEditor_Move(list, fromIndex, toIndex)` and `BuildOrderEditor_SetAlternatives(field, ids)`.
- `BuildOrderEditor_Validate` returns an ordered error table; `BuildOrderEditor_ToRuntime` returns `newID, buildOrder` only after validation succeeds.

- [ ] **Step 1: Write failing draft and conversion tests**

Cover blank drafts, deep-copy edits, unique `(copy)` suffixes, deterministic title/civilization IDs, same-order preservation, list moves, positive-or-unselected resource values, and validation paths.

Assert alternatives conversion:

```lua
{ "building_barracks_eng" }
-- becomes { id = "building_barracks_eng" }

{ "building_barracks_eng", "building_archery_range_eng" }
-- becomes { oneof = { "building_barracks_eng", "building_archery_range_eng" } }
```

Cover both `built` and `age_up`. Assert semantic unit-family selections emit `payload.ids`, not an age-specific alias. Assert a `vils` card emits one aggregate threshold descriptor plus separate `no_collect` descriptors, while a resources card emits one descriptor per populated resource.

Test inferred ages for add/delete/reorder: each step uses its entering age, and only an `age_up` increments the following step by one.

- [ ] **Step 2: Run the focused test and confirm red**

Run: `python -m unittest tests.test_build_order_editor_model -v`

Expected: FAIL because both editor modules are absent.

- [ ] **Step 3: Define the declarative schema**

In `editor_schema.scar`, define schema nodes for primitive, enum, object, optional, and list fields. Give every check kind an explicit field list. Register adapters by semantic shape rather than by rendering code:

```lua
BUILD_ORDER_EDITOR_ADAPTERS = {
    alternatives = { min_items = 1 },
    resources = { keys = { "food", "wood", "gold", "stone" } },
    no_collect = { values = { "food", "wood", "gold", "stone" } },
    live_entity = { discovery_kind = "entity" },
    live_upgrade = { discovery_kind = "upgrade" },
    live_family = { discovery_kind = "family" },
}
```

- [ ] **Step 4: Implement draft operations and runtime conversion**

Use stable path-addressed fields such as `steps.2.checks.1.payload.count` for errors and UI commands. Recompute inferred ages after every structural change. Generate deterministic check IDs from order ID, step index, kind, and same-kind occurrence; generate player-facing titles from current field values without persisting author aliases.

- [ ] **Step 5: Run focused and regression tests**

Run: `python -m unittest tests.test_build_order_editor_model tests.test_build_order_datastore -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add assets/scar/build_orders/editor_model.scar assets/scar/build_orders/editor_schema.scar tests/test_build_order_editor_model.py
git commit -m "feat: add schema driven build order drafts"
```

---

### Task 4: Single-Column XAML Editor and Recursive View Projection

**Files:**
- Create: `assets/scar/build_orders/editor_ui.scar`
- Create: `tests/test_build_order_editor_ui.py`

**Interfaces:**
- Consumes: editor drafts, schema definitions, errors, inferred ages, and discovery options from Tasks 2-3.
- Produces: `BuildOrderEditorUI_EnsureCreated() -> Boolean`, `BuildOrderEditorUI_ShowSelector(model)`, `BuildOrderEditorUI_ShowEditor(model)`, `BuildOrderEditorUI_ShowNoSelectionConfirmation(model)`, `BuildOrderEditorUI_Hide()`, `BuildOrderEditorUI_Stop()`, and `BuildOrderEditorUI_SetCallbacks(callbacks)`.
- `callbacks` exposes global command names for selection, create, edit, copy, save, cancel, unpause, confirm-unpause, field changes, add/delete, expand/collapse, and reorder.

- [ ] **Step 1: Write failing XAML and binding contract tests**

Assert one `XamlPresenter` is created under `ScarDefault` with `IsHitTestVisible = true`, an `UI_CreateDataContext` model, and `UI_CreateCommand` callbacks. Assert the root view is one scrollable column, not a sidebar/grid split. Assert step item templates contain nested check item templates, expansion state, validation text, drag handles, add/delete controls, and the sticky Save/Cancel/Create copy header.

Assert the editor binds current-civilization text read-only and displays the official current-player flag through `DataContext.LocalPlayer.RaceIconSecondary` on the containing `CardinalHUDPage`. Assert all four resource fields bind simultaneously and live selector options render label/icon plus internal-ID fallbacks.

- [ ] **Step 2: Run the focused test and confirm red**

Run: `python -m unittest tests.test_build_order_editor_ui -v`

Expected: FAIL because `editor_ui.scar` does not exist.

- [ ] **Step 3: Implement the recursive schema-to-view projection**

Create view nodes shaped consistently for XAML:

```lua
{
    path = "steps.2.checks.1",
    node_type = "object",
    label = "Age up",
    expanded = true,
    fields = {},
    errors = {},
}
```

Primitive and enum nodes render inline. Object nodes and list entries render as expandable cards. Empty optional nodes render an Add action. Refresh mutations by rebuilding the view model and calling `UI_SetDataContext`.

- [ ] **Step 4: Implement selector, editor, confirmation, and reorder UI**

`BuildOrderEditorUI_EnsureCreated` wraps the one-time `UI_AddChild` call in `pcall`, returning `false` when the presenter cannot be created so startup can use its minimal fallback. Create the presenter once and switch its bound `screen` value among `selector`, `editor`, `confirmation`, and `hidden`. Use `ListView`/`ItemsControl` vertical item templates. Implement reorder without undocumented native collection mutation: the drag handle's `PreviewMouseLeftButtonDown` command records the source path, each card's `MouseEnter` command records the current target while a drag is active, and `PreviewMouseLeftButtonUp` commits the source/target indices through `BuildOrderEditor_Move`. Bind each event through the official `CallCommandAction`/`CommandParameter` pattern and rebuild the data context after commit. Cancel the drag when the source disappears or mouse-up has no compatible target. Retain explicit keyboard-accessible move-up/move-down commands as an additional path.

- [ ] **Step 5: Run focused tests and validate SCAR/XAML APIs**

Run: `python -m unittest tests.test_build_order_editor_ui tests.test_build_order_editor_model -v`

Run AoE4 MCP `check_code` on `editor_ui.scar` and `find_ui` for every nonstandard XAML property introduced by the implementation.

Expected: tests PASS; all SCAR calls are documented APIs or official wrappers; every XAML interaction has an official-source precedent or passes the Content Editor build in Task 7.

- [ ] **Step 6: Commit**

```bash
git add assets/scar/build_orders/editor_ui.scar tests/test_build_order_editor_ui.py
git commit -m "feat: render the in game build order editor"
```

---

### Task 5: Editor Controller and Save Workflow

**Files:**
- Create: `assets/scar/build_orders/editor.scar`
- Create: `tests/test_build_order_editor.py`

**Interfaces:**
- Consumes: discovery, schema/model, UI, and datastore interfaces from Tasks 1-4.
- Produces: `BuildOrderEditor_OpenCreate(onComplete)`, `BuildOrderEditor_OpenEdit(originalID, onComplete)`, `BuildOrderEditor_CreateCopy()`, `BuildOrderEditor_Save()`, `BuildOrderEditor_Cancel()`, `BuildOrderEditor_HandleCommand(action, path, value)`, and `BuildOrderEditor_Stop()`.
- `onComplete(savedID)` receives the saved ID, or `nil` when canceled.

- [ ] **Step 1: Write failing controller tests**

Assert create and edit perform fresh discovery; edit retains `original_id`; copy clears it and chooses a collision-free title; all mutations validate and refresh the view; invalid Save retains the draft; valid Save calls `BuildOrderDatastore_Apply(originalID, newID, order)`; and cancel/stop clear draft, errors, discovery, and callbacks.

Assert reorder and `age_up` mutations immediately recompute all step ages and live option filters.

- [ ] **Step 2: Run the focused test and confirm red**

Run: `python -m unittest tests.test_build_order_editor -v`

Expected: FAIL because `editor.scar` does not exist.

- [ ] **Step 3: Implement controller state and command routing**

Keep state in one table:

```lua
BUILD_ORDER_EDITOR_STATE = {
    draft = nil,
    original_id = nil,
    discovery = nil,
    errors = {},
    on_complete = nil,
}
```

Route commands by stable schema path, then validate, infer ages, rebuild the view, and update the data context. Save must mutate the catalog only after conversion succeeds.

- [ ] **Step 4: Run focused tests**

Run: `python -m unittest tests.test_build_order_editor tests.test_build_order_editor_model tests.test_build_order_datastore -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add assets/scar/build_orders/editor.scar tests/test_build_order_editor.py
git commit -m "feat: coordinate build order editing"
```

---

### Task 6: Replace Startup Chooser and Integrate Module Lifecycle

**Files:**
- Modify: `assets/scar/build_orders/startup.scar`
- Modify: `assets/scar/winconditions/Macro Trainer.scar`
- Modify: `assets/locdb/Macro Trainer_en.csv`
- Modify: `tests/test_build_order_startup.py`
- Modify: `tests/test_build_order_import_graph.py`
- Modify: `tests/test_simspeed_cycle.py`

**Interfaces:**
- Consumes: `BuildOrderEditorUI_*`, `BuildOrderEditor_*`, `BuildOrderDatastore_*`, and existing objective/simspeed entry points.
- Produces: final GRI-109 startup behavior and cleanup through `BuildOrderStartup_Start()` and `BuildOrderStartup_Stop()`.

- [ ] **Step 1: Rewrite startup tests for the two focused screens**

Replace carousel/message-box expectations with assertions that startup collects compatible orders, schedules `BuildOrderStartup_PauseNextTick`, and shows the selector containing the explicit no-order choice. Cover select/edit/create, saved-order reselection, cancel restoration, selected-order unpause, no-order confirmation, idempotent start, and missing-selection fallback.

Assert custom UI failure uses the minimal message-box escape path and never resumes before explicit confirmation.

- [ ] **Step 2: Add failing import and cleanup tests**

Require this import order before `startup.scar`:

```lua
import("build_orders/editor_discovery.scar")
import("build_orders/editor_model.scar")
import("build_orders/editor_schema.scar")
import("build_orders/editor_ui.scar")
import("build_orders/editor.scar")
```

Require `Mod_OnGameOver()` to call `BuildOrderEditor_Stop()` and `BuildOrderEditorUI_Stop()` exactly once while preserving existing datastore, startup, objective, and simspeed cleanup.

- [ ] **Step 3: Run focused tests and confirm red**

Run: `python -m unittest tests.test_build_order_startup tests.test_build_order_import_graph tests.test_simspeed_cycle -v`

Expected: FAIL because startup still uses the message-box carousel and the new modules are not imported.

- [ ] **Step 4: Implement selector coordination and lifecycle integration**

Keep `_mod.selectedBuildOrderID` unchanged until the player selects or saves an order. `BuildOrderStartup_StartSelected` remains the only path that starts objectives. Confirmed no-order unpause starts only the enabled simspeed cycle. Save completion returns to the selector and selects the saved ID; editor cancel restores the prior selection.

Add stable localization rows for all visible labels and fallback messages, and reference their fully qualified `$dfb5645698a84afb91cf7a2dfb0f4a4e:<id>` keys from SCAR/XAML.

- [ ] **Step 5: Run focused and full tests**

Run: `python -m unittest tests.test_build_order_startup tests.test_build_order_import_graph tests.test_simspeed_cycle -v`

Run: `python -m unittest discover -s tests -p "test_*.py" -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add assets/scar/build_orders/startup.scar assets/scar/winconditions/'Macro Trainer.scar' assets/locdb/'Macro Trainer_en.csv' tests/test_build_order_startup.py tests/test_build_order_import_graph.py tests/test_simspeed_cycle.py
git commit -m "feat: add the paused build order startup UI"
```

---

### Task 7: API Audit, Package Build, and Final Regression Evidence

**Files:**
- Modify only if verification exposes a defect: files introduced or changed in Tasks 1-6 and their focused tests.

**Interfaces:**
- Consumes: the complete feature branch.
- Produces: verified SCAR, XAML, localization, and packaged-mod evidence.

- [ ] **Step 1: Run whitespace and repository checks**

Run: `git diff --check origin/pr/19...HEAD`

Run: `git status --short`

Expected: no whitespace errors and no unintended files.

- [ ] **Step 2: Run the complete automated suite**

Run: `python -m unittest discover -s tests -p "test_*.py" -v`

Expected: PASS with zero failures or errors.

- [ ] **Step 3: Audit every changed SCAR file with the AoE4 MCP**

Use `check_code` on the complete contents of:

```text
assets/scar/build_orders/datastore.scar
assets/scar/build_orders/editor_discovery.scar
assets/scar/build_orders/editor_model.scar
assets/scar/build_orders/editor_schema.scar
assets/scar/build_orders/editor_ui.scar
assets/scar/build_orders/editor.scar
assets/scar/build_orders/startup.scar
assets/scar/winconditions/Macro Trainer.scar
```

Expected: no unknown production calls, missing localization keys, or unresolved imports.

- [ ] **Step 4: Build the `.aoe4mod` package**

Use the repository's `aoe4mod-build` skill and the AoE4 Content Editor CLI to build `Macro Trainer.aoe4mod` from this worktree.

Expected: Content Editor exits successfully and the burn log contains no SCAR compile, XAML parse, or missing-localization error.

- [ ] **Step 5: Run the in-game acceptance checklist**

Verify manually in the built mod:

1. Startup pauses and shows the local civilization selector.
2. No-order unpause requires confirmation.
3. Create, edit, rename, and copy persist across a new match.
4. The editor is single-column with nested, expandable, draggable step/check cards.
5. English entity-landmark and Abbasid/Ayyubid-style technology age-ups discover and save correctly.
6. Later-step option lists advance only after preceding `age_up` checks.
7. Spearman is selected as one family and saves all compatible canonical variants.
8. Missing display metadata falls back to the internal ID and missing age falls back to Age I.
9. Save writes all existing build orders, not only the modified one.

- [ ] **Step 6: Commit verification fixes, if any**

For each defect, add or tighten a reproducing test first, implement the smallest correction, rerun the focused test and Steps 1-4, then commit only the affected files with a specific `fix:` message. If verification requires no correction, create no empty commit.
