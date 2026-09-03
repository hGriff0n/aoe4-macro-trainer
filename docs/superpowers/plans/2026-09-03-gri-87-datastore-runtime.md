# GRI-87 Datastore Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Load and merge compiled build orders from the AoE4 datastore, then let the player choose any compatible merged order from the startup modal.

**Architecture:** A focused SCAR datastore module owns asynchronous engine loading, schema checks, and overlay semantics. The existing startup coordinator waits for that module, then either starts the lobby-selected order or drives a guarded message-box carousel over compatible merged-catalog entries.

**Tech Stack:** AoE4 SCAR/Lua, Python 3 `unittest`, AoE4 official API checker.

**Spec:** `docs/superpowers/specs/2026-09-03-build-order-datastore-design.md`

## Global Constraints

- Datastore ID and default filename stem are exactly `macroTrainerBuildOrders`.
- Supported datastore schema version is exactly `1`.
- Datastore records overlay bundled records by exact build-order ID.
- Missing or invalid datastore content preserves the complete bundled catalog.
- Runtime datastore titles are literal strings and do not require generated locdb entries.
- The modal chooser contains only orders matching `string.lower(Player_GetRaceName(Game_GetLocalPlayer()))`.
- No branch step edits or removes the user's existing main-checkout changes.

---

### Task 1: Asynchronous datastore catalog overlay

**Files:**
- Create: `assets/scar/build_orders/datastore.scar`
- Create: `tests/test_build_order_datastore.py`
- Modify: `assets/scar/winconditions/Macro Trainer.scar`
- Modify: `tests/test_simspeed_cycle.py`

**Interfaces:**
- Consumes: bundled global `BUILD_ORDER_CATALOG` populated by `generated/build_orders.scar`.
- Produces: `BuildOrderDatastore_Load(onComplete)`, `BuildOrderDatastore_FinishLoad()`, `BuildOrderDatastore_Stop()`, and the merged `BUILD_ORDER_CATALOG`.

- [ ] **Step 1: Add failing load-sequencing and import tests**

Create `tests/test_build_order_datastore.py` with the repository's existing `function_body` helper pattern and assertions equivalent to:

```python
def test_load_waits_one_rule_tick_then_retrieves_named_global(self):
    load = function_body(self.datastore, "BuildOrderDatastore_Load")
    finish = function_body(self.datastore, "BuildOrderDatastore_FinishLoad")
    self.assertIn('Game_LoadTextDataStore(BUILD_ORDER_DATASTORE_ID, "")', load)
    self.assertIn("Rule_Add(BuildOrderDatastore_FinishLoad)", load)
    self.assertNotIn("Game_RetrieveTableData", load)
    self.assertIn("Rule_RemoveMe()", finish)
    self.assertIn("Game_RetrieveTableData(BUILD_ORDER_DATASTORE_ID, false)", finish)
    self.assertIn("local loaded = _G[BUILD_ORDER_DATASTORE_ID]", finish)

def test_main_imports_datastore_after_bundled_catalog_before_startup(self):
    bundled = 'import("generated/build_orders.scar")'
    datastore = 'import("build_orders/datastore.scar")'
    startup = 'import("build_orders/startup.scar")'
    self.assertLess(self.main.index(bundled), self.main.index(datastore))
    self.assertLess(self.main.index(datastore), self.main.index(startup))
```

Also update the source-order expectation in `tests/test_simspeed_cycle.py` so the new datastore import is required between the generated catalog and objective/startup consumers.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
python -m unittest tests.test_build_order_datastore tests.test_simspeed_cycle -v
```

Expected: failures because `datastore.scar` and its import do not exist.

- [ ] **Step 3: Implement the minimal asynchronous loader**

Create constants and guarded module state:

```lua
BUILD_ORDER_DATASTORE_ID = "macroTrainerBuildOrders"
BUILD_ORDER_DATASTORE_SCHEMA_VERSION = 1
BUILD_ORDER_DATASTORE_ON_COMPLETE = nil
BUILD_ORDER_DATASTORE_LOADING = false
```

`BuildOrderDatastore_Load(onComplete)` stores the callback, sets the loading guard, calls `Game_LoadTextDataStore(BUILD_ORDER_DATASTORE_ID, "")`, removes any stale finish rule, and schedules `BuildOrderDatastore_FinishLoad`. The finish rule removes itself, calls `Game_RetrieveTableData(BUILD_ORDER_DATASTORE_ID, false)`, reads `_G[BUILD_ORDER_DATASTORE_ID]`, conditionally merges it, clears the guard/callback, and invokes the captured callback exactly once. `BuildOrderDatastore_Stop()` removes the rule and clears both state variables.

Import the module immediately after the generated catalog. Change `Mod_Start()` to call `BuildOrderDatastore_Load(BuildOrderStartup_Start)`. Call `BuildOrderDatastore_Stop()` from `Mod_OnGameOver()` before stopping the startup coordinator.

- [ ] **Step 4: Add failing schema, fallback, and precedence tests**

Add assertions that name the mutations they catch:

```python
def test_only_supported_catalog_records_overlay_bundled_ids(self):
    merge = function_body(self.datastore, "BuildOrderDatastore_Merge")
    self.assertIn("loaded.schema_version ~= BUILD_ORDER_DATASTORE_SCHEMA_VERSION", merge)
    self.assertIn('type(loaded.build_orders) ~= "table"', merge)
    self.assertIn("for id, buildOrder in pairs(loaded.build_orders) do", merge)
    self.assertIn("BUILD_ORDER_CATALOG[id] = buildOrder", merge)

def test_invalid_store_reaches_callback_without_clearing_bundled_catalog(self):
    finish = function_body(self.datastore, "BuildOrderDatastore_FinishLoad")
    self.assertNotIn("BUILD_ORDER_CATALOG = {}", finish)
    self.assertIn("BuildOrderDatastore_Complete()", finish)
```

Require record validation for exact key/record ID agreement, nonempty `civ`/`title`, and table-shaped `steps`; invalid records are skipped and logged while valid records still overlay.

- [ ] **Step 5: Run RED, implement validation/merge, and run GREEN**

Run the focused suite, confirm the new merge assertions fail, then implement `BuildOrderDatastore_IsValidOrder` and `BuildOrderDatastore_Merge`. Re-run:

```powershell
python -m unittest tests.test_build_order_datastore tests.test_simspeed_cycle tests.test_build_order_startup -v
```

Expected: all focused tests pass.

- [ ] **Step 6: Validate the SCAR API surface and commit**

Run the AoE4 checker against the full contents of `datastore.scar` and the modified main wincondition. Treat unknown calls as failures; the datastore calls must resolve to their official signatures. Then run `git diff --check` and commit:

```powershell
git add -- assets/scar/build_orders/datastore.scar assets/scar/winconditions/'Macro Trainer.scar' tests/test_build_order_datastore.py tests/test_simspeed_cycle.py
git commit -m "feat: load build orders from datastore"
```

### Task 2: Dynamic compatible-order modal chooser

**Files:**
- Modify: `assets/scar/build_orders/startup.scar`
- Modify: `assets/scar/winconditions/Macro Trainer.scar`
- Modify: `tests/test_build_order_startup.py`
- Modify: `build/templates/assets/locdb/Macro Trainer_en.csv`

**Interfaces:**
- Consumes: merged global `BUILD_ORDER_CATALOG`, `_mod.selectedBuildOrderID`, `NORMAL_SIM_RATE`, and `_mod.simspeedEnabled`.
- Produces: `BuildOrderStartup_CollectCompatible`, `BuildOrderStartup_ShowError`, `BuildOrderStartup_ShowChooser`, `BuildOrderStartup_HandleErrorChoice`, and `BuildOrderStartup_HandleChooserChoice`.

- [ ] **Step 1: Add failing no-selection and two-button error tests**

Replace the old assertion that a missing selection silently starts the sim-speed cycle. Assert that no selection opens the error modal and that the error modal configures all four slots to prevent stale chooser buttons:

```python
def test_no_selection_opens_error_with_dynamic_choice(self):
    start = function_body(self.startup, "BuildOrderStartup_Start")
    self.assertIn("BuildOrderStartup_ShowNoSelectionError()", start)
    self.assertNotIn("Mod_StartSimspeedCycle()", start)

def test_error_modal_offers_continue_and_compatible_catalog_choice(self):
    show = function_body(self.startup, "BuildOrderStartup_ShowError")
    self.assertRegex(show, r'UI_MessageBoxSetButton\(\s*DB_Button1,\s*"Continue Without Build Order"')
    self.assertRegex(show, r'UI_MessageBoxSetButton\(\s*DB_Button2,\s*"Choose Build Order"')
    self.assertRegex(show, r'UI_MessageBoxSetButton\(\s*DB_Button3,\s*"",\s*"",\s*"",\s*false')
    self.assertRegex(show, r'UI_MessageBoxSetButton\(\s*DB_Button4,\s*"",\s*"",\s*"",\s*false')
```

Add stable English locdb rows for the no-selection title/message and chooser labels only where the existing runtime requires loc keys; dynamically selected order content remains literal.

- [ ] **Step 2: Run startup tests and verify RED**

Run:

```powershell
python -m unittest tests.test_build_order_startup -v
```

Expected: failures because no selection still bypasses the modal and only one button is configured.

- [ ] **Step 3: Implement the guarded error transition**

Initialize chooser state in `_mod`:

```lua
compatibleBuildOrderIDs = {},
buildOrderChoiceIndex = 1,
buildOrderStarted = false,
```

Add `BuildOrderStartup_ResetButtons()` that calls `UI_MessageBoxSetButton` for buttons 1 through 4 with empty text/tooltips/icons and `false`. Call it before configuring every error or chooser modal. The error handler accepts only an open alert: button 1 closes the alert and continues without objectives; button 2 opens the chooser only when compatible IDs exist.

- [ ] **Step 4: Add failing deterministic catalog/carousel tests**

Add contract assertions for:

```python
def test_compatible_choices_filter_local_civ_and_sort_title_then_id(self):
    collect = function_body(self.startup, "BuildOrderStartup_CollectCompatible")
    self.assertIn("Player_GetRaceName(Game_GetLocalPlayer())", collect)
    self.assertIn("string.lower(buildOrder.civ) == actualCiv", collect)
    self.assertIn("BuildOrderStartup_ChoiceComesBefore", collect)

def test_chooser_configures_use_next_previous_and_cancel(self):
    chooser = function_body(self.startup, "BuildOrderStartup_ShowChooser")
    for button, label in (("DB_Button1", "Use This Build Order"), ("DB_Button2", "Next"), ("DB_Button3", "Previous"), ("DB_Button4", "Cancel")):
        self.assertRegex(chooser, rf'UI_MessageBoxSetButton\(\s*{button},\s*"{label}"')

def test_navigation_wraps_and_selection_starts_once(self):
    handler = function_body(self.startup, "BuildOrderStartup_HandleChooserChoice")
    self.assertIn("BuildOrderStartup_WrapChoiceIndex", handler)
    self.assertIn("_mod.selectedBuildOrderID = selectedID", handler)
    self.assertIn("BuildOrderStartup_StartSelected(buildOrder)", handler)
    self.assertIn("if _mod.buildOrderStarted then", handler)
```

Require the chooser message to include one-based position/count, title, civilization, and source only when nonempty.

- [ ] **Step 5: Run RED, implement the carousel, and run GREEN**

Confirm the new tests fail. Implement an insertion-sort helper so behavior does not depend on `pairs` order. Next/previous wrap, cancel returns to the error modal, and `Use This Build Order` revalidates civilization before starting. Centralize successful start in `BuildOrderStartup_StartSelected` and latch `_mod.buildOrderStarted` before invoking `BuildOrder_Start` or the cycle.

Run:

```powershell
python -m unittest tests.test_build_order_startup tests.test_build_order_datastore tests.test_simspeed_cycle tests.test_build_order_objectives -v
```

Expected: all focused runtime tests pass.

- [ ] **Step 6: Run API checks and commit**

Run the AoE4 checker on the complete startup and main SCAR sources. `UI_MessageBoxSetButton` must match the official five-argument signature; do not introduce the low-confidence unused `UI_MessageBoxReset` call. Run `git diff --check`, then commit:

```powershell
git add -- assets/scar/build_orders/startup.scar assets/scar/winconditions/'Macro Trainer.scar' tests/test_build_order_startup.py build/templates/assets/locdb/'Macro Trainer_en.csv'
git commit -m "feat: choose datastore build orders at startup"
```

### Task 3: GRI-87 verification and requested mod build

**Files:**
- Verify only; generated ignored assets may change during the build.

**Interfaces:**
- Consumes: completed GRI-87 runtime branch and `E:\Docs\github\aoemod\build orders`.
- Produces: passing verification evidence and a fresh `archives/Macro_Trainer.sga` from the wrapper.

- [ ] **Step 1: Run the complete automated verification**

Run:

```powershell
python -m unittest discover -s tests -v
git diff --check
git status --short
```

Expected: zero test failures, no whitespace errors, and no uncommitted source/test changes.

- [ ] **Step 2: Show the exact build command and obtain confirmation**

Per the repository build skill, display exactly:

```powershell
python 'E:\Docs\github\aoemod\aoe4-macro-trainer\.worktrees\gri-87-datastore-loading\tools\build_mod.py' --build-orders 'E:\Docs\github\aoemod\build orders'
```

Wait for explicit confirmation before launching the external Content Editor build.

- [ ] **Step 3: Run the wrapper to completion and record evidence**

Execute the confirmed command from the GRI-87 project directory. Wait for `tools/build_mod.py` itself to exit after its final archive polling. A nonzero exit means the build failed. On exit zero, verify the final archive exists and report its fresh timestamp/size.

- [ ] **Step 4: Push the GRI-87 prerequisite branch**

Verify the remote name and branch head, then push:

```powershell
git push -u origin codex/gri-87-datastore-loading
```

The compiler pull request cannot target this branch until it exists on the remote.

