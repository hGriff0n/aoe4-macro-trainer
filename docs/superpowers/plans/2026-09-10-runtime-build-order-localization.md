# Runtime Build-Order Localization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove generated English objective titles from the datastore and format every build-order objective at runtime from reusable localization templates and canonical game IDs.

**Architecture:** The Python compiler continues to validate YAML and normalize identities, but schema version 2 stores only check semantics. SCAR handlers own `formatTitle` functions that turn their existing payloads into `LocString` values using shared helpers, mod locdb templates, and base-game `screenName` values.

**Tech Stack:** Python 3 dataclasses and `unittest`, YAML compiler, Lua-like AoE IV SCAR, AoE IV locdb CSV, Essence Content Editor.

**Spec:** `docs/superpowers/specs/2026-09-10-runtime-build-order-localization-design.md`

## Global Constraints

- Datastore schema version is exactly `2`; do not add schema-version-1 compatibility or migration.
- Do not store generated check titles or generated step titles.
- Preserve authored build-order titles, custom step titles, and hint payload text exactly.
- Never call `LOC` on arbitrary datastore text.
- Never convert a resolved game `screenName` through `Loc_ToAnsi` for display.
- Do not restore any abandoned in-game editor code.
- Preserve current check completion semantics and current English title wording.
- Preserve the untracked `assets/scar/generated/` directory; it is user-owned output.

---

### Task 1: Remove Generated Titles from the Compiler Model

**Files:**
- Modify: `tools/build_orders/model.py`
- Modify: `tools/build_orders/compiler.py`
- Modify: `tests/test_build_order_compiler.py`
- Modify: `tests/test_build_order_resources.py`
- Modify: `tests/test_build_order_hints.py`
- Modify: `tests/test_build_order_produce.py`
- Modify: `tests/test_build_order_units.py`
- Modify: `tests/test_build_order_upgrades.py`
- Modify: `tests/test_build_order_compiler_cli.py`

**Interfaces:**
- Produces: `CheckDescriptor(kind: str, optional: bool, payload: dict[str, object])`.
- Preserves: `Step(title: str | None, checks: tuple[CheckDescriptor, ...])`; `None` continues to distinguish a generated step title from authored text.
- Preserves: canonical `id`, `oneof`, and `ids` payload values used by later SCAR formatters.

- [ ] **Step 1: Rewrite compiler tests to assert semantic descriptors only**

Replace title-bearing expectations with payload expectations. Representative exact assertions:

```python
self.assertEqual(
    checks,
    (
        CheckDescriptor("vils", False, {"food": 7, "gold": 3}),
        CheckDescriptor(
            "vils",
            False,
            {"resource": "wood", "no_collect": True},
        ),
    ),
)

self.assertEqual(
    hint,
    CheckDescriptor("hints", True, {"text": "Keep producing villagers"}),
)

self.assertEqual(
    built.payload,
    {"oneof": ["building_stable_eng", "building_archery_range_eng"], "count": 2},
)
self.assertFalse(hasattr(built, "title"))
```

Update every `check.title`, `(check.title, ...)`, and four-argument `CheckDescriptor(...)` assertion under `tests/` so tests describe kind, optionality, ordering, and payload only.

- [ ] **Step 2: Run the focused compiler tests and verify they fail**

Run:

```powershell
python -m unittest tests.test_build_order_compiler tests.test_build_order_resources tests.test_build_order_hints tests.test_build_order_produce tests.test_build_order_units tests.test_build_order_upgrades tests.test_build_order_compiler_cli -v
```

Expected: failures because `CheckDescriptor` still requires `title` and compiled checks still expose English titles.

- [ ] **Step 3: Remove presentation assembly from the Python model and compiler**

Change the dataclass to:

```python
@dataclass(frozen=True)
class CheckDescriptor:
    kind: str
    optional: bool
    payload: dict[str, object]
```

Construct checks only from semantic fields:

```python
checks.append(CheckDescriptor("resources", False, {"resource": resource, "count": number}))
checks.append(CheckDescriptor("vils", False, thresholds))
checks.append(CheckDescriptor("rallypoint", False, {"resource": resource}))
result.append(CheckDescriptor(kind, False, dict(payload)))
result.append(CheckDescriptor("upgrades", optional, payload))
result.append(CheckDescriptor("produce", optional, payload))
result.append(CheckDescriptor("buildings", False, payload))
result.append(CheckDescriptor("units", False, payload))
checks.append(CheckDescriptor("hints", True, {"text": text}))
```

Delete `_humanize_identity_id`, `_pluralize_unit`, title locals, and family-ID return values used only for presentation. Keep all validation, canonical-ID resolution, resource ordering, flags, and optionality unchanged.

- [ ] **Step 4: Run all Python compiler tests**

Run:

```powershell
python -m unittest tests.test_build_order_compiler tests.test_build_order_resources tests.test_build_order_hints tests.test_build_order_produce tests.test_build_order_units tests.test_build_order_upgrades tests.test_build_order_compiler_cli -v
```

Expected: compiler/model tests pass; datastore and objective tests may still fail until Tasks 2 and 4 update their contracts.

- [ ] **Step 5: Commit the compiler-only change**

```powershell
git add tools/build_orders/model.py tools/build_orders/compiler.py tests/test_build_order_compiler.py tests/test_build_order_resources.py tests/test_build_order_hints.py tests/test_build_order_produce.py tests/test_build_order_units.py tests/test_build_order_upgrades.py tests/test_build_order_compiler_cli.py
git commit -m "refactor: remove compiled objective titles"
```

---

### Task 2: Introduce Strict Datastore Schema Version 2

**Files:**
- Modify: `tools/build_orders/datastore.py`
- Modify: `assets/scar/build_orders/datastore.scar`
- Modify: `tests/test_build_order_datastore_codec.py`
- Modify: `tests/test_build_order_datastore.py`

**Interfaces:**
- Consumes: three-field `CheckDescriptor` from Task 1.
- Produces: schema-v2 records with check keys `id`, `kind`, `optional`, and `payload`.
- Produces: step records with required `checks` and optional authored `title`.

- [ ] **Step 1: Add failing schema-v2 serialization and validation tests**

Use fixtures with one authored and one generated step:

```python
ORDER = BuildOrder(
    "english-opening",
    "english",
    "Opening",
    (
        Step("Economy", (CheckDescriptor("vils", False, {"food": 7}),)),
        Step(None, (CheckDescriptor("hints", True, {"text": "Scout"}),)),
    ),
)

rendered = render_datastore(Catalog((ORDER,)))
self.assertIn("schema_version = 2", rendered)
self.assertIn('title = "Economy"', rendered)
self.assertEqual(rendered.count('title = "Economy"'), 1)
self.assertNotIn('title = "Step 2"', rendered)
self.assertNotRegex(rendered, r"kind = \"(?:vils|hints)\",\s*title =")
self.assertEqual(parse_datastore(rendered), Catalog((ORDER,)))
```

Add negative cases proving schema 1 is rejected, a check `title` is an unknown key, an empty custom step title is rejected, and an omitted step title parses to `None`. Update the SCAR behavior fixture to use `schema_version = 2`, omit check titles, and omit generated step titles.

- [ ] **Step 2: Run datastore tests and verify they fail**

Run:

```powershell
python -m unittest tests.test_build_order_datastore_codec tests.test_build_order_datastore -v
```

Expected: failures showing schema version 1, required step/check titles, and four-field descriptor construction.

- [ ] **Step 3: Implement schema-v2 Python serialization and parsing**

Set:

```python
SCHEMA_VERSION = 2
```

Serialize checks without `title` and steps conditionally:

```python
checks.append(
    {
        "id": f"{order.id}:{step_index}:{check_index}",
        "kind": check.kind,
        "optional": check.optional,
        "payload": check.payload,
    }
)
step_record: dict[str, object] = {"checks": checks}
if step.title is not None:
    step_record["title"] = step.title
steps.append(step_record)
```

Parse step keys with `{"checks"}` required and `{"title"}` optional. Parse absent title as `None`. Require check keys `{"id", "kind", "optional", "payload"}` and construct `CheckDescriptor(kind, optional, payload)`.

- [ ] **Step 4: Implement matching SCAR validation**

Set `BUILD_ORDER_DATASTORE_SCHEMA_VERSION = 2`. Remove the `check.title` requirement. Permit `step.title == nil`; if it is present, require a non-empty string:

```lua
if step.title ~= nil and (type(step.title) ~= "string" or step.title == "") then
    return false
end
```

Keep build-order `title` required and keep all persistence behavior unchanged.

- [ ] **Step 5: Run datastore tests and the complete compiler suite**

Run:

```powershell
python -m unittest tests.test_build_order_datastore_codec tests.test_build_order_datastore -v
python -m unittest discover -s tests -p "test_build_order_*.py" -v
```

Expected: all datastore and compiler tests pass except objective-title tests intentionally replaced in Task 4.

- [ ] **Step 6: Commit schema version 2**

```powershell
git add tools/build_orders/datastore.py assets/scar/build_orders/datastore.scar tests/test_build_order_datastore_codec.py tests/test_build_order_datastore.py
git commit -m "feat: store semantic build order checks"
```

---

### Task 3: Add Reusable Localization and Game-Name Helpers

**Files:**
- Create: `assets/scar/build_orders/localization.scar`
- Create: `tests/test_build_order_localization.py`
- Modify: `assets/locdb/Macro Trainer_en.csv`
- Modify: `assets/scar/winconditions/Macro Trainer.scar`
- Modify: `tests/test_build_order_import_graph.py`

**Interfaces:**
- Produces: `BUILD_ORDER_LOC_KEYS` and `BUILD_ORDER_RESOURCE_KEYS`.
- Produces: `BuildOrder_RawText(text) -> LocString`.
- Produces: `BuildOrder_JoinLocalized(values, separatorKey) -> LocString`.
- Produces: `BuildOrder_ResourceName(resource) -> LocString`.
- Produces: `BuildOrder_GameName(kind, id, context) -> LocString`.
- Produces: `BuildOrder_TargetNames(payload, kind, context) -> LocString`.
- Produces: `BuildOrder_FirstSquadName(payload, context) -> LocString`.

- [ ] **Step 1: Add failing helper, locdb, and import tests**

Create tests that execute the helper with `ScarRuntime` and stub `Loc_FormatText` as a structural tuple:

```python
runtime.globals["Loc_FormatText"] = lambda key, *args: (key, *args)
self.assertEqual(
    runtime.call("BuildOrder_RawText", "Авторский текст"),
    ("$dfb5645698a84afb91cf7a2dfb0f4a4e:143", "Авторский текст"),
)
```

Stub blueprint functions with identity-bearing dictionaries and assert:

```python
self.assertEqual(
    runtime.call("BuildOrder_GameName", "entity", "building_kremlin", context),
    "localized Kremlin",
)
self.assertEqual(entity_ui_calls, ["building_kremlin"])
self.assertEqual(loc_to_ansi_calls, [])
```

Test squad resolution calls `BP_GetSquadUIInfo` with `Player_GetRace(context.localPlayer)`, upgrade resolution uses `BP_GetUpgradeUIInfo`, `oneof` keeps order, missing IDs are logged and passed through the raw wrapper, and resource lookup covers food/gold/wood/stone. Assert the packaged root imports `build_orders/localization.scar` after the datastore and before the objective engine.

- [ ] **Step 2: Run the localization tests and verify they fail**

Run:

```powershell
python -m unittest tests.test_build_order_localization tests.test_build_order_import_graph -v
```

Expected: failure because the helper file, generic locdb templates, and import do not exist.

- [ ] **Step 3: Replace Abbasid strings with reusable locdb slots**

Reassign IDs 143–167 to these English texts and notes; remove obsolete exact-title rows 168–172:

```csv
143,,,Raw authored build-order text.,,,%1TEXT%
144,,,Generated build-order step title.,,,Step #%1COUNT%
145,,,Build-order hint title.,,,[HINT] %1TEXT%
146,,,Optional check title wrapper.,,,[Optional] %1TEXT%
147,,,Unavailable check title.,,,Build-order check unavailable
148,,,Build-order resource name.,,,food
149,,,Build-order resource name.,,,gold
150,,,Build-order resource name.,,,wood
151,,,Build-order resource name.,,,stone
152,,,Resource allocation fragment.,,,%1COUNT% %2RESOURCE%
153,,,Resource allocation separator.,,,%1TEXT% | %2TEXT%
154,,,Alternative target separator.,,,%1TEXT% or %2TEXT%
155,,,Resource collection check.,,,Collect at least %1COUNT% %2RESOURCE%
156,,,Villager assignment check.,,,Assign %1ALLOCATIONS%
157,,,No-collection villager check.,,,No %1RESOURCE% villagers
158,,,Rally-point check.,,,Rally to %1RESOURCE%
159,,,Single-building construction check.,,,Build %1TARGET%
160,,,Counted-building construction check.,,,Build %1COUNT% %2TARGET%
161,,,Age-up check.,,,Age Up: %1TARGET%
162,,,Research check.,,,Research %1UPGRADE%
163,,,Queued research check.,,,Queue %1UPGRADE% for research
164,,,Production check.,,,Produce %1COUNT% %2UNIT%
165,,,Queued production check.,,,Queue %1COUNT% %2UNIT%
166,,,Constant production check.,,,Constantly produce %1UNIT%
167,,,Active-unit count check.,,,Have %1COUNT% active %2UNIT%
```

- [ ] **Step 4: Implement the shared SCAR helper**

Define key tables and compositional helpers. Core behavior:

```lua
function BuildOrder_RawText(text)
    return Loc_FormatText(BUILD_ORDER_LOC_KEYS.rawText, text)
end

function BuildOrder_JoinLocalized(values, separatorKey)
    if #values == 0 then
        return Loc_Empty()
    end
    local result = values[1]
    for index = 2, #values do
        result = Loc_FormatText(separatorKey, result, values[index])
    end
    return result
end

function BuildOrder_GameName(kind, id, context)
    local uiInfo = nil
    if kind == "entity" then
        local found, pbg = pcall(BP_GetEntityBlueprint, id)
        if found and pbg ~= nil then
            local resolved, value = pcall(BP_GetEntityUIInfo, pbg)
            if resolved then uiInfo = value end
        end
    elseif kind == "squad" then
        local found, pbg = pcall(BP_GetSquadBlueprint, id)
        if found and pbg ~= nil then
            local resolved, value = pcall(
                BP_GetSquadUIInfo,
                pbg,
                Player_GetRace(context.localPlayer)
            )
            if resolved then uiInfo = value end
        end
    elseif kind == "upgrade" then
        local found, pbg = pcall(BP_GetUpgradeBlueprint, id)
        if found and pbg ~= nil then
            local resolved, value = pcall(BP_GetUpgradeUIInfo, pbg)
            if resolved then uiInfo = value end
        end
    end
    if uiInfo ~= nil and uiInfo.screenName ~= nil then
        return uiInfo.screenName
    end
    print("BuildOrder: missing localized " .. tostring(kind) .. " name for " .. tostring(id))
    return BuildOrder_RawText(tostring(id))
end
```

`BuildOrder_TargetNames` reads `payload.id` or every ordered value in `payload.oneof`, resolves each through `BuildOrder_GameName`, and joins alternatives with the `or` key. `BuildOrder_FirstSquadName` resolves `payload.ids[1]`.

- [ ] **Step 5: Import the helper before the objective engine and run tests**

Add:

```lua
import("build_orders/datastore.scar")
import("build_orders/localization.scar")
import("build_orders/objective_engine.scar")
```

Run:

```powershell
python -m unittest tests.test_build_order_localization tests.test_build_order_import_graph tests.test_build_order_settings -v
```

Expected: PASS, including exact locdb IDs, no `LOC(rawText)`, and no display-path `Loc_ToAnsi`.

- [ ] **Step 6: Commit reusable localization support**

```powershell
git add assets/scar/build_orders/localization.scar "assets/locdb/Macro Trainer_en.csv" "assets/scar/winconditions/Macro Trainer.scar" tests/test_build_order_localization.py tests/test_build_order_import_graph.py
git commit -m "feat: add runtime build order localization helpers"
```

---

### Task 4: Format Steps and Dispatch Check Titles in the Objective Engine

**Files:**
- Modify: `assets/scar/build_orders/objective_engine.scar`
- Create: `assets/scar/build_orders/checks/hints.scar`
- Modify: `assets/scar/winconditions/Macro Trainer.scar`
- Modify: `tests/test_build_order_objectives.py`
- Modify: `tests/test_build_order_hints.py`
- Modify: `tests/test_build_order_import_graph.py`

**Interfaces:**
- Consumes: `BuildOrder_RawText` and `BUILD_ORDER_LOC_KEYS` from Task 3.
- Consumes: optional `handler.formatTitle(check, BUILD_ORDER_STATE) -> LocString` supplied by Tasks 4–7.
- Produces: `BuildOrder_StepTitle(step, stepIndex) -> LocString`.
- Produces: `BuildOrder_CheckTitle(check, handler) -> LocString`.

- [ ] **Step 1: Replace exact-title tests with failing runtime-dispatch tests**

Delete tests for `BUILD_ORDER_OBJECTIVE_TITLE_KEYS`, Abbasid strings, and the `LOC:` fallback. Add executable tests using a fake formatter:

```python
FAKE_HANDLER_FIXTURE = '''local fakeHandler = {
    formatTitle = function(check, context)
        return Loc_FormatText("$fake:1", check.payload.count)
    end,
    activate = function(check, objectiveID, context)
        BuildOrder_NotifyComplete(check.id)
    end,
    deactivate = function(check, objectiveID, context)
    end,
}
BuildOrder_RegisterHandler("fake", fakeHandler)'''
```

Assert an absent step title produces the ID-144 formatted title, a custom title produces the ID-143 wrapper, the child objective receives the fake handler result, a missing formatter produces ID 147 and a diagnostic, and synthesized check IDs copy only `kind`, `optional`, and `payload`.

Add a hint formatter contract:

```lua
function Hints_FormatTitle(check, context)
    return Loc_FormatText(BUILD_ORDER_LOC_KEYS.hint, check.payload.text)
end

BuildOrder_RegisterHandler("hints", {
    formatTitle = Hints_FormatTitle,
})
```

Assert hint registration does not add `activate`, does not emit a missing-handler log, and formats only `[HINT] %1TEXT%` without the optional wrapper.

- [ ] **Step 2: Run objective and hint tests and verify they fail**

Run:

```powershell
python -m unittest tests.test_build_order_objectives tests.test_build_order_hints -v
```

Expected: failures because the engine still reads stored titles and hints have no registered formatter.

- [ ] **Step 3: Implement step and check formatting dispatch**

Remove `BUILD_ORDER_OBJECTIVE_TITLE_KEYS` and `BuildOrder_ObjectiveTitle`. Add:

```lua
function BuildOrder_StepTitle(step, stepIndex)
    if step.title ~= nil then
        return BuildOrder_RawText(step.title)
    end
    return Loc_FormatText(BUILD_ORDER_LOC_KEYS.step, stepIndex)
end

function BuildOrder_CheckTitle(check, handler)
    if handler == nil or handler.formatTitle == nil then
        print("BuildOrder: no title formatter for " .. tostring(check.kind) .. " (check " .. tostring(check.id) .. ")")
        return BUILD_ORDER_LOC_KEYS.unavailable
    end
    return handler.formatTitle(check, BUILD_ORDER_STATE)
end
```

Resolve `handler` before `Obj_Create`, pass `BuildOrder_StepTitle(step, stepIndex)` to the primary objective, and pass `BuildOrder_CheckTitle(check, handler)` to the child. Remove `title` from the synthesized check record.

Create `checks/hints.scar` with the presentation-only handler shown in Step 1. Import it with the other check handlers after `objective_engine.scar`, and update the import-graph test to require exactly one hints import before startup.

- [ ] **Step 4: Run objective, hint, and import tests**

Run:

```powershell
python -m unittest tests.test_build_order_objectives tests.test_build_order_hints tests.test_build_order_import_graph -v
```

Expected: PASS; no exact-title lookup, no arbitrary `LOC`, generated steps use their runtime index, and hints remain non-blocking.

- [ ] **Step 5: Commit objective dispatch**

```powershell
git add assets/scar/build_orders/objective_engine.scar assets/scar/build_orders/checks/hints.scar "assets/scar/winconditions/Macro Trainer.scar" tests/test_build_order_objectives.py tests/test_build_order_hints.py tests/test_build_order_import_graph.py
git commit -m "feat: format build order objectives at runtime"
```

---

### Task 5: Format Resource, Villager, and Rally Checks

**Files:**
- Modify: `assets/scar/build_orders/checks/resources.scar`
- Modify: `assets/scar/build_orders/checks/vils.scar`
- Modify: `assets/scar/build_orders/checks/rallypoint.scar`
- Modify: `tests/test_build_order_resources.py`
- Modify: `tests/test_build_order_vils.py`
- Modify: `tests/test_build_order_rallypoint.py`

**Interfaces:**
- Consumes: `BuildOrder_ResourceName` and `BuildOrder_JoinLocalized` from Task 3.
- Produces: `Resources_FormatTitle`, `Vils_FormatTitle`, and `Rallypoint_FormatTitle`.

- [ ] **Step 1: Add failing executable formatter tests**

For each module, concatenate `localization.scar` with the handler source, stub `Loc_FormatText`, and call the formatter directly. Assert these structures:

```python
self.assertEqual(
    runtime.call("Resources_FormatTitle", {"payload": {"resource": "gold", "count": 150}}, context),
    (LOC["collect"], 150, LOC["gold"]),
)
self.assertEqual(
    runtime.call("Rallypoint_FormatTitle", {"payload": {"resource": "stone"}}, context),
    (LOC["rally"], LOC["stone"]),
)
```

For vils, assert `{food=6, gold=3}` becomes an `assign` format containing two `countResource` fragments joined by the localized pipe key in food/gold/wood/stone order. Assert `{resource="wood", no_collect=true}` uses the no-villagers key.

- [ ] **Step 2: Run the three focused tests and verify they fail**

Run:

```powershell
python -m unittest tests.test_build_order_resources tests.test_build_order_vils tests.test_build_order_rallypoint -v
```

Expected: missing formatter functions and missing `formatTitle` registrations.

- [ ] **Step 3: Implement and register the formatters**

Use direct payload formatting:

```lua
function Resources_FormatTitle(check, context)
    return Loc_FormatText(
        BUILD_ORDER_LOC_KEYS.collect,
        check.payload.count,
        BuildOrder_ResourceName(check.payload.resource)
    )
end

function Rallypoint_FormatTitle(check, context)
    return Loc_FormatText(
        BUILD_ORDER_LOC_KEYS.rally,
        BuildOrder_ResourceName(check.payload.resource)
    )
end
```

`Vils_FormatTitle` handles `no_collect` first. Otherwise it walks the fixed order `food`, `gold`, `wood`, `stone`, creates localized count/resource fragments, joins them using `BUILD_ORDER_LOC_KEYS.allocationJoin`, and wraps them with `BUILD_ORDER_LOC_KEYS.assign`. Add `formatTitle = ...` to all three existing registrations without changing lifecycle functions.

- [ ] **Step 4: Run focused tests**

Run:

```powershell
python -m unittest tests.test_build_order_resources tests.test_build_order_vils tests.test_build_order_rallypoint -v
```

Expected: PASS, with unchanged check polling and completion behavior.

- [ ] **Step 5: Commit primitive check formatters**

```powershell
git add assets/scar/build_orders/checks/resources.scar assets/scar/build_orders/checks/vils.scar assets/scar/build_orders/checks/rallypoint.scar tests/test_build_order_resources.py tests/test_build_order_vils.py tests/test_build_order_rallypoint.py
git commit -m "feat: localize resource build order checks"
```

---

### Task 6: Format Entity, Age-Up, and Upgrade Checks

**Files:**
- Modify: `assets/scar/build_orders/checks/built.scar`
- Modify: `assets/scar/build_orders/checks/buildings.scar`
- Modify: `assets/scar/build_orders/checks/age_up.scar`
- Modify: `assets/scar/build_orders/checks/upgrades.scar`
- Modify: `tests/test_build_order_built.py`
- Modify: `tests/test_build_order_buildings.py`
- Modify: `tests/test_build_order_age_up.py`
- Modify: `tests/test_build_order_upgrades.py`

**Interfaces:**
- Consumes: `BuildOrder_GameName`, `BuildOrder_TargetNames`, and localized action keys from Task 3.
- Produces: `Built_FormatTitle`, `Buildings_FormatTitle`, `AgeUp_FormatTitle`, and `Upgrades_FormatTitle`.

- [ ] **Step 1: Add failing formatter tests for every branch**

Stub game-name helpers to return deterministic localized values. Assert:

```python
self.assertEqual(single_built, (LOC["buildOne"], "Barracks"))
self.assertEqual(counted_built, (LOC["buildMany"], 2, "Barracks"))
self.assertEqual(oneof_built, (LOC["buildOne"], (LOC["orJoin"], "Stable", "Archery Range")))
self.assertEqual(buildings, "Town Center")
self.assertEqual(construction_age, (LOC["ageUp"], "Council Hall"))
self.assertEqual(upgrade_age, (LOC["ageUp"], "Economic Wing"))
self.assertEqual(research, (LOC["research"], "Wheelbarrow"))
self.assertEqual(queued, (LOC["queueResearch"], "Wheelbarrow"))
self.assertEqual(optional, (LOC["optional"], (LOC["research"], "Wheelbarrow")))
```

Verify construction age-ups request entity names, upgrade age-ups request upgrade names, ordered `oneof` values are retained, and existing activation functions are unchanged.

- [ ] **Step 2: Run focused tests and verify they fail**

Run:

```powershell
python -m unittest tests.test_build_order_built tests.test_build_order_buildings tests.test_build_order_age_up tests.test_build_order_upgrades -v
```

Expected: missing formatter functions and registrations.

- [ ] **Step 3: Implement entity and age-up formatters**

Use `BuildOrder_TargetNames(check.payload, "entity", context)` for built checks. Choose the singular or counted build template from `payload.count`. Buildings return `BuildOrder_GameName("entity", check.payload.id, context)` directly.

For age-up checks:

```lua
function AgeUp_FormatTitle(check, context)
    local targetKind = "entity"
    if check.payload.trigger == "upgrade" then
        targetKind = "upgrade"
    end
    return Loc_FormatText(
        BUILD_ORDER_LOC_KEYS.ageUp,
        BuildOrder_TargetNames(check.payload, targetKind, context)
    )
end
```

Add each formatter to its existing handler registration.

- [ ] **Step 4: Implement upgrade formatting and handler-controlled optional copy**

```lua
function Upgrades_FormatTitle(check, context)
    local name = BuildOrder_GameName("upgrade", check.payload.id, context)
    local title = nil
    if check.payload.queued then
        title = Loc_FormatText(BUILD_ORDER_LOC_KEYS.queueResearch, name)
    else
        title = Loc_FormatText(BUILD_ORDER_LOC_KEYS.research, name)
    end
    if check.optional then
        return Loc_FormatText(BUILD_ORDER_LOC_KEYS.optional, title)
    end
    return title
end
```

Do not make the objective engine apply optional copy globally.

- [ ] **Step 5: Run focused tests**

Run:

```powershell
python -m unittest tests.test_build_order_built tests.test_build_order_buildings tests.test_build_order_age_up tests.test_build_order_upgrades -v
```

Expected: PASS with all existing execution-contract tests still green.

- [ ] **Step 6: Commit entity and upgrade formatters**

```powershell
git add assets/scar/build_orders/checks/built.scar assets/scar/build_orders/checks/buildings.scar assets/scar/build_orders/checks/age_up.scar assets/scar/build_orders/checks/upgrades.scar tests/test_build_order_built.py tests/test_build_order_buildings.py tests/test_build_order_age_up.py tests/test_build_order_upgrades.py
git commit -m "feat: localize entity and upgrade checks"
```

---

### Task 7: Format Squad Production and Unit Checks

**Files:**
- Modify: `assets/scar/build_orders/checks/produce.scar`
- Modify: `assets/scar/build_orders/checks/units.scar`
- Modify: `tests/test_build_order_produce.py`
- Modify: `tests/test_build_order_units.py`

**Interfaces:**
- Consumes: `BuildOrder_FirstSquadName(payload, context) -> LocString` from Task 3.
- Produces: `Produce_FormatTitle` and `Units_FormatTitle`.

- [ ] **Step 1: Add failing formatter tests for production precedence and units**

Assert the first canonical family ID supplies the localized name and that current precedence is preserved:

```python
self.assertEqual(normal, (LOC["produce"], 2, "Villager"))
self.assertEqual(queued, (LOC["queueProduce"], 2, "Villager"))
self.assertEqual(constant, (LOC["constantProduce"], "Villager"))
self.assertEqual(constant_and_queued, (LOC["constantProduce"], "Villager"))
self.assertEqual(active, (LOC["activeUnits"], 3, "Spearman"))
```

Assert constant production remains completion-optional without acquiring `[Optional]` display text.

- [ ] **Step 2: Run focused tests and verify they fail**

Run:

```powershell
python -m unittest tests.test_build_order_produce tests.test_build_order_units -v
```

Expected: missing formatter functions and registrations.

- [ ] **Step 3: Implement squad formatters**

```lua
function Produce_FormatTitle(check, context)
    local name = BuildOrder_FirstSquadName(check.payload, context)
    if check.payload.constant then
        return Loc_FormatText(BUILD_ORDER_LOC_KEYS.constantProduce, name)
    elseif check.payload.queued then
        return Loc_FormatText(BUILD_ORDER_LOC_KEYS.queueProduce, check.payload.count, name)
    end
    return Loc_FormatText(BUILD_ORDER_LOC_KEYS.produce, check.payload.count, name)
end

function Units_FormatTitle(check, context)
    return Loc_FormatText(
        BUILD_ORDER_LOC_KEYS.activeUnits,
        check.payload.count,
        BuildOrder_FirstSquadName(check.payload, context)
    )
end
```

Register both formatters without changing their event, polling, baseline, or completion logic.

- [ ] **Step 4: Run focused tests**

Run:

```powershell
python -m unittest tests.test_build_order_produce tests.test_build_order_units -v
```

Expected: PASS.

- [ ] **Step 5: Commit squad formatters**

```powershell
git add assets/scar/build_orders/checks/produce.scar assets/scar/build_orders/checks/units.scar tests/test_build_order_produce.py tests/test_build_order_units.py
git commit -m "feat: localize squad build order checks"
```

---

### Task 8: Verify the Complete Runtime Localization Path

**Files:**
- Modify: `tests/test_build_order_compiler_cli.py`
- Test: all `tests/test_*.py`
- External generated datastore: `E:/Docs/My Games/Age of Empires IV/Users/76561198050151767/datastore/macroTrainerBuildOrders.rlt`
- Built archive: `archives/Macro_Trainer.sga`

**Interfaces:**
- Consumes: schema-v2 compiler and every SCAR formatter from Tasks 1–7.
- Produces: a locally testable schema-v2 datastore and rebuilt mod package.

- [ ] **Step 1: Add an end-to-end datastore assertion**

In `tests/test_build_order_compiler_cli.py`, compile a fixture with generated and custom steps, then assert the written text has schema 2, contains the custom title and hint payload, and contains neither check titles nor `Step 1`:

```python
self.assertIn("schema_version = 2", text)
self.assertIn('title = "Opening"', text)
self.assertIn('text = "Keep producing"', text)
self.assertNotIn('title = "Step 1"', text)
self.assertNotIn("[HINT] Keep producing", text)
self.assertNotIn("Assign 7 food", text)
```

- [ ] **Step 2: Run the complete automated suite**

Run:

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
git diff --check
```

Expected: every test passes and `git diff --check` prints no errors.

- [ ] **Step 3: Compile the real build-order directory into the active profile**

Run:

```powershell
python -m tools.build_orders.compiler build "E:\Docs\github\aoemod\build orders" --profile 76561198050151767
```

Expected: 10 build orders are stored. Inspect the resulting datastore and verify `schema_version = 2`, check records have no `title`, custom step titles remain, and generated steps omit `title`.

- [ ] **Step 4: Build the mod through the Content Editor**

Use the `aoe4mod-build` skill and build:

```powershell
& 'F:\Program Files (x86)\Steam\steamapps\common\Age of Empires IV Content Editor\EssenceLauncher.exe' --build_mod 'E:\Docs\github\aoemod\aoe4-macro-trainer\Macro Trainer.aoe4mod' --auto_close_burn_window
```

Expected: exit code 0 and an updated `archives/Macro_Trainer.sga`.

- [ ] **Step 5: Perform the in-game smoke test**

Verify both `abba_3tc` and a Rus build order. Confirm generated steps show `Step #N`, standard checks use localized game object names, custom titles and hints preserve authored text, and no objective contains `LOC:`. Also verify completing checks still advances steps normally.

- [ ] **Step 6: Commit final integration coverage**

```powershell
git add tests/test_build_order_compiler_cli.py
git commit -m "test: verify runtime-localized datastore output"
```

Do not commit the external player datastore or generated SGA archive unless they are already intentionally tracked.
