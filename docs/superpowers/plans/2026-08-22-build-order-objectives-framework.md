# Build-Order Objectives Framework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compile user-authored YAML build orders into local AoE4 mod assets, expose them through lobby settings, and render their pending checks in the native objectives UI without implementing production check predicates.

**Architecture:** A Python build pipeline resets ignored live outputs from tracked no-build-order templates, validates YAML into immutable canonical models, emits SCAR/RDO/localization data, and then invokes Essence. Stable SCAR modules independently own build-order objective state, sim-rate state, and startup validation so later predicate issues can register handlers without knowing how YAML or settings are generated.

**Tech Stack:** Python 3.13, PyYAML 6.x, `unittest`, AoE4 SCAR/Lua, WinCondition RDO XML, locdb CSV, AoE4 Content Editor CLI

**Spec:** `docs/superpowers/specs/2026-08-22-build-order-objectives-framework-design.md`

## Global Constraints

- YAML is the sole authoritative build-order source; generated production SCAR, RDO, and CSV files are never committed.
- Every generator run resets outputs to a checked-in no-build-order baseline before reading YAML; there is no incremental-generation shortcut.
- The build-order ID is the normalized `civ + title` slug; duplicate generated IDs fail validation.
- A supplied step title is rendered verbatim; only an untitled step renders `Step N`.
- GRI-55 through GRI-64 own production check predicates. This plan creates presentation descriptors and handler interfaces only.
- Build-order training is single-player. Multiplayer selection and separation from the sim-rate mod are out of scope.
- `none` is the default build-order selection. It is silent when the sim-rate cycle is enabled and an alert when the cycle is disabled.
- Configuration alerts pause at simulation rate `0`, disable only build-order progression, and resume through one native message-box button.
- The existing GRI-23/GRI-38 duration and slow-rate settings remain intact.
- Do not modify or commit the user's `.codex/config.toml` working-tree change.
- Each Linear issue is implemented in its own `codex/gri-<number>-...` worktree branch and receives requirements and code-quality review before integration.

## Execution Bootstrap

Use `superpowers:using-git-worktrees` before implementation. Create a clean integration worktree and branch from fetched `origin/main`, then cherry-pick the approved spec and this plan. Create each issue worktree from the current integration branch after all dependencies listed below are integrated. Never base issue worktrees on the stale local `main` checkout.

Dependency order:

1. GRI-67
2. GRI-66
3. GRI-68
4. GRI-72
5. GRI-69
6. Parent integration verification

The ordering is intentional: GRI-67 defines canonical data; GRI-66 consumes it; GRI-68 extends its emitters; GRI-72 separates timer startup; and GRI-69 coordinates every resulting interface.

---

### Task 1: GRI-67 — YAML Compiler and Build Orchestrator

**Files:**
- Create: `requirements-build.txt`
- Create: `build_orders/.gitkeep`
- Create: `build/templates/assets/scar/winconditions/Macro Trainer.rdo`
- Create: `build/templates/assets/locdb/Macro Trainer_en.csv`
- Create: `tools/build_orders/__init__.py`
- Create: `tools/build_orders/model.py`
- Create: `tools/build_orders/compiler.py`
- Create: `tools/build_orders/emitters.py`
- Create: `tools/build_mod.py`
- Create: `tests/fixtures/build_orders/valid/english_opening.yaml`
- Create: `tests/test_build_order_compiler.py`
- Create: `tests/test_build_order_build.py`
- Modify: `.gitignore`
- Modify: `docs/build_order_schema.yaml`
- Modify: `README.md`
- Modify: `tests/test_simspeed_cycle.py`
- Move: `assets/scar/winconditions/Macro Trainer.rdo` → `build/templates/assets/scar/winconditions/Macro Trainer.rdo`
- Move: `assets/locdb/Macro Trainer_en.csv` → `build/templates/assets/locdb/Macro Trainer_en.csv`

**Interfaces:**
- Consumes: `.yaml`/`.yml` files containing one mapping or a list of mappings; `Macro Trainer.aoe4mod`; fixed Essence launcher path `F:\Program Files (x86)\Steam\steamapps\common\Age of Empires IV Content Editor\EssenceLauncher.exe`.
- Produces: `compile_directory(input_dir: Path) -> Catalog`, `reset_outputs(paths: BuildPaths) -> None`, `emit_outputs(catalog: Catalog, paths: BuildPaths) -> None`, `generate_assets(config: BuildConfig) -> Catalog`, and `build_mod(config: BuildConfig, runner: Callable[..., CompletedProcess]) -> int`.
- Produces ignored live files: `assets/scar/winconditions/Macro Trainer.rdo`, `assets/locdb/Macro Trainer_en.csv`, and `assets/scar/generated/build_orders.scar`.
- Produces SCAR global: `BUILD_ORDER_CATALOG`, keyed by generated build-order ID.

- [ ] **Step 1: Add the build dependency and ignored-output contract**

Add the exact dependency:

```text
PyYAML>=6.0,<7
```

Add root-anchored ignore entries:

```gitignore
/assets/scar/winconditions/Macro Trainer.rdo
/assets/locdb/Macro Trainer_en.csv
/assets/scar/generated/build_orders.scar
```

Move the currently tracked RDO and English CSV to the matching `build/templates` paths. Update `tests/test_simspeed_cycle.py` so its RDO and localization constants point at the tracked templates. Add `title: string # optional player-facing step title` to each step in `docs/build_order_schema.yaml`.

- [ ] **Step 2: Write failing canonical-model and compiler tests**

Define tests with temporary input directories that require these immutable models:

```python
@dataclass(frozen=True)
class CheckDescriptor:
    kind: str
    title: str
    optional: bool
    payload: dict[str, object]

@dataclass(frozen=True)
class Step:
    title: str | None
    checks: tuple[CheckDescriptor, ...]

@dataclass(frozen=True)
class BuildOrder:
    id: str
    civ: str
    title: str
    steps: tuple[Step, ...]

@dataclass(frozen=True)
class Catalog:
    build_orders: tuple[BuildOrder, ...]
```

Tests must cover: one mapping; a list document; `.yaml` and `.yml`; deterministic file sorting; preserved step/check/list ordering; slug `english-2-tc`; titled and untitled steps; all documented check keys; at least one check per step; `id`/`oneof` exclusivity; positive counts; resource validation; unknown-field rejection; duplicate slug rejection; and diagnostics containing `relative/file.yaml: steps[0].built[1].id`-style paths.

- [ ] **Step 3: Run the compiler tests and verify the red state**

Run:

```powershell
python -m unittest tests.test_build_order_compiler -v
```

Expected: FAIL because `tools.build_orders.model` and `compile_directory` do not exist.

- [ ] **Step 4: Implement canonical models, normalization, and strict validation**

Implement `normalize_id` with Unicode NFKD normalization, lowercase ASCII, non-alphanumeric runs collapsed to `-`, and leading/trailing separators removed:

```python
def normalize_id(civ: str, title: str) -> str:
    normalized = unicodedata.normalize("NFKD", f"{civ}-{title}")
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")
```

Use `yaml.safe_load`, accept only a root mapping or list of mappings, and build fresh payload dictionaries so YAML aliases cannot create mutable shared runtime state. Expand mapping checks such as `vils` and `resources` into one descriptor per ordered resource entry; expand list checks into one descriptor per ordered item. Store presentation text separately from the typed payload. Reject title-only/empty steps because they would auto-advance without presenting a check. Raise one `BuildOrderValidationError` containing file and YAML path on the first invalid value.

- [ ] **Step 5: Run the compiler suite to green**

Run:

```powershell
python -m unittest tests.test_build_order_compiler -v
```

Expected: PASS.

- [ ] **Step 6: Write failing reset, emission, and subprocess tests**

Create temporary template/output trees. Tests must place stale sentinel build orders in all three live outputs, call `reset_outputs`, and assert the RDO/CSV exactly equal their templates while the SCAR contains exactly:

```lua
BUILD_ORDER_CATALOG = {}
```

Then require `emit_outputs` to write a catalog with localized titles and ordered checks, without leaving `.tmp` siblings. Add a malformed-YAML test that calls `build_mod` and verifies stale data is gone, outputs remain at baseline, and the fake Essence runner was never called. Add a successful-build test whose runner receives exactly:

```python
[
    essence_launcher,
    "--build_mod",
    str(mod_file.resolve()),
    "--auto_close_burn_window",
]
```

Add a nonzero-runner test that returns the same nonzero code and never prints the success message.

- [ ] **Step 7: Run build-pipeline tests and verify the red state**

Run:

```powershell
python -m unittest tests.test_build_order_build -v
```

Expected: FAIL because reset, emission, and orchestration functions do not exist.

- [ ] **Step 8: Implement baseline-first atomic emission**

Define exact path/config objects:

```python
@dataclass(frozen=True)
class BuildPaths:
    project_root: Path
    rdo_template: Path
    locdb_template: Path
    rdo_output: Path
    locdb_output: Path
    scar_output: Path

@dataclass(frozen=True)
class BuildConfig:
    paths: BuildPaths
    build_order_dir: Path
    mod_file: Path
    essence_launcher: Path
```

`reset_outputs` creates parent directories, copies the two templates, and atomically writes the empty catalog. `emit_outputs` renders every complete file in memory, writes a sibling `<name>.tmp`, and uses `Path.replace` only after all rendering succeeds. `generate_assets` performs exactly `reset_outputs` → `compile_directory` → `emit_outputs` and returns the catalog. Escape SCAR backslashes, quotes, CR/LF, and tabs explicitly. Allocate generated localization IDs deterministically from `1000` in catalog traversal order and use fully qualified `$dfb5645698a84afb91cf7a2dfb0f4a4e:<id>` keys in SCAR.

- [ ] **Step 9: Implement the build CLI**

Support:

```powershell
python tools/build_mod.py --build-orders build_orders
python tools/build_mod.py --build-orders tests/fixtures/build_orders/valid --generate-only
```

Defaults are the repository root, `Macro Trainer.aoe4mod`, and the fixed launcher path. The top-level order is `reset_outputs` → `compile_directory` → `emit_outputs` → optional Essence subprocess. Print validation errors to stderr and return `2`; return the Essence exit code for launcher failures; return `0` only after successful generation and, unless `--generate-only` was used, a successful launcher exit.

Use this committed fixture so emission and later objective tests share one deterministic catalog:

```yaml
civ: english
title: Framework Test
steps:
  - title: Opening Economy
    vils:
      food: 7
    hints:
      - Keep producing villagers
  - resources:
      wood: 400
```

- [ ] **Step 10: Run focused and complete Python tests**

Run:

```powershell
python -m unittest tests.test_build_order_compiler tests.test_build_order_build tests.test_simspeed_cycle -v
python -m unittest discover -s tests -v
```

Expected: all tests PASS.

- [ ] **Step 11: Document the authoritative workflow and commit GRI-67**

Document that YAML is authoritative, generated outputs are ignored/local, every run resets before parsing, `--generate-only` is for validation/tests, and normal builds require the exact Content Editor launcher. Commit only GRI-67 files:

```powershell
git add -- .gitignore requirements-build.txt build build_orders tools tests docs/build_order_schema.yaml README.md
git commit -m "feat: compile YAML build orders for GRI-67"
```

---

### Task 2: GRI-66 — Native Objective Engine and Handler Contract

**Files:**
- Create: `assets/scar/build_orders/objective_engine.scar`
- Create: `tests/test_build_order_objectives.py`
- Modify: `assets/scar/winconditions/Macro Trainer.scar`
- Modify: `tests/test_simspeed_cycle.py`

**Interfaces:**
- Consumes: generated `BUILD_ORDER_CATALOG[id]` records with `id`, `civ`, `title`, and ordered `steps`; each step has `title` and `checks`; each check has `id`, `kind`, `title`, `optional`, and `payload`.
- Produces: `BuildOrder_RegisterHandler(kind, handler)`, `BuildOrder_Start(buildOrder, player)`, `BuildOrder_ActivateStep(stepIndex)`, `BuildOrder_NotifyComplete(checkID)`, `BuildOrder_TryAdvance()`, and `BuildOrder_Stop()`.
- Handler contract: `handler.activate(check, objectiveID, context)` and optional `handler.deactivate(check, objectiveID, context)`.

- [ ] **Step 1: Write failing source-contract tests**

Require the main win-condition file to import generated data before the engine:

```lua
import("generated/build_orders.scar")
import("build_orders/objective_engine.scar")
```

Require engine state for the local player, selected build, active step, primary objective ID, ordered child records, handler map, and an `advancing` guard. Require primary creation with `DT_PRIMARY_DEFAULT`, `OT_Primary`, and parent `0`; require child creation with `DT_SECONDARY_DEFAULT`, `OT_Secondary`, and the primary ID. Reject warning templates/types.

Require missing handlers to leave `OS_Incomplete`, required completion to call `BuildOrder_TryAdvance`, optional checks not to block, cleanup to deactivate handlers then delete child objectives before the primary, and the last completed step to stop cleanly rather than indexing past the catalog.

- [ ] **Step 2: Run the objective tests and verify the red state**

Run:

```powershell
python -m unittest tests.test_build_order_objectives -v
```

Expected: FAIL because the engine file and imports do not exist.

- [ ] **Step 3: Implement objective creation and handler activation**

Use the documented low-level objective API:

```lua
local primaryID = Obj_Create(
    player.id, step.title, Loc_Empty(), "", DT_PRIMARY_DEFAULT,
    player.raceName, OT_Primary, 0, "buildOrderStep")
Obj_SetState(primaryID, OS_Incomplete)

local childID = Obj_Create(
    player.id, check.title, Loc_Empty(), "", DT_SECONDARY_DEFAULT,
    player.raceName, OT_Secondary, primaryID, "buildOrderCheck")
Obj_SetState(childID, OS_Incomplete)
```

Store child records by stable generated check ID and preserve an ordered array for cleanup. If a handler exists, call `activate`; otherwise leave the child pending. Never invoke handler logic while creating a sibling objective.

- [ ] **Step 4: Implement completion, advancement, and idempotent cleanup**

`BuildOrder_NotifyComplete` ignores unknown/already-complete check IDs, sets the matching child to `OS_Complete`, latches it, and calls `BuildOrder_TryAdvance`. `BuildOrder_TryAdvance` returns while `advancing` is true or any incomplete required child remains. Otherwise it marks the primary complete, clears the hierarchy, increments the step, and activates the next step. `BuildOrder_Stop` may be called repeatedly and always clears handlers/objectives/state safely.

- [ ] **Step 5: Add a fake-handler contract fixture inside the Python test**

The test embeds this expected consumer shape and asserts every referenced engine entry point exists and is called in the right lifecycle order:

```lua
local fakeHandler = {
    activate = function(check, objectiveID, context)
        BuildOrder_NotifyComplete(check.id)
    end,
    deactivate = function(check, objectiveID, context)
    end,
}
BuildOrder_RegisterHandler("fake", fakeHandler)
```

This is a contract fixture only; do not add a production `fake` handler to shipped SCAR.

- [ ] **Step 6: Run focused and complete tests**

Run:

```powershell
python -m unittest tests.test_build_order_objectives tests.test_simspeed_cycle -v
python -m unittest discover -s tests -v
```

Expected: all tests PASS.

- [ ] **Step 7: Validate the SCAR APIs and commit GRI-66**

Pass the complete engine and main SCAR source to the AoE4 code checker. `Obj_Create`, `Obj_SetState`, `Obj_Delete`, `DT_PRIMARY_DEFAULT`, `DT_SECONDARY_DEFAULT`, `OT_Primary`, and `OT_Secondary` must resolve to documented APIs/constants or high-confidence official usage. Commit:

```powershell
git add -- assets/scar/build_orders/objective_engine.scar assets/scar/winconditions/'Macro Trainer.scar' tests/test_build_order_objectives.py tests/test_simspeed_cycle.py
git commit -m "feat: add build-order objective framework for GRI-66"
```

---

### Task 3: GRI-68 — Generated Build-Order Lobby Enumeration

**Files:**
- Modify: `build/templates/assets/scar/winconditions/Macro Trainer.rdo`
- Modify: `build/templates/assets/locdb/Macro Trainer_en.csv`
- Modify: `tools/build_orders/emitters.py`
- Modify: `assets/scar/winconditions/Macro Trainer.scar`
- Create: `tests/test_build_order_settings.py`
- Modify: `tests/test_build_order_build.py`

**Interfaces:**
- Consumes: `Catalog.build_orders` and the GRI-67 template/output paths.
- Produces RDO option key: `option_build_order`.
- Produces enum item keys: `build_order_none` and `build_order_<generated-id>`.
- Produces SCAR state: `_mod.selectedBuildOrderID`, default `nil`.
- Produces helper: `Mod_ReadSelectedBuildOrder(settings) -> string|nil`.

- [ ] **Step 1: Write failing RDO/localization generation tests**

Require one `WinCondition::EnumerationOptionUIDescriptor` under `section_macro_trainer_settings` with key `option_build_order`. The baseline template contains exactly one default enum item with key `build_order_none` and player-facing text `None`. The template contains one exact XML marker:

```xml
<!-- GENERATED_BUILD_ORDER_ENUM_ITEMS -->
```

Generate two unsorted builds and assert emitted items sort by normalized civilization then title, use keys `build_order_english-2-tc`, use labels `[English] 2 TC`, allocate unique 64-bit RDO object IDs from `9100000000000000000`, and add matching localization rows without changing existing IDs 1–19.

- [ ] **Step 2: Run settings tests and verify the red state**

Run:

```powershell
python -m unittest tests.test_build_order_settings -v
```

Expected: FAIL because the build-order option and RDO emission marker do not exist.

- [ ] **Step 3: Add the baseline enumeration and RDO emitter**

Add static localization rows for the option name, tooltip, and `None` item before the generated-ID range. Extend `emit_outputs` so the RDO emitter replaces the one marker with generated `DataValue` and `DataObject` fragments. Every generated item has `m_isDefaultValue=false` and `m_devOnly=false`; only `build_order_none` is default.

- [ ] **Step 4: Read the selected value defensively in SCAR**

Add:

```lua
function Mod_ReadSelectedBuildOrder(settings)
    local option = settings.option_build_order
    local enumKey = option
    if type(option) == "table" then
        enumKey = option.enum_value
    end
    if enumKey == nil or enumKey == "build_order_none" then
        return nil
    end
    return string.gsub(enumKey, "^build_order_", "")
end
```

Call it from `Mod_SetupSettings` after the existing duration/rate values. Do not start objectives from the settings callback; startup remains a later responsibility.

- [ ] **Step 5: Run generation and regression tests**

Run:

```powershell
python -m unittest tests.test_build_order_settings tests.test_build_order_build tests.test_simspeed_cycle -v
python tools/build_mod.py --build-orders tests/fixtures/build_orders/valid --generate-only
python -m unittest discover -s tests -v
```

Expected: all tests PASS; generated live RDO contains `None` plus the English fixture.

- [ ] **Step 6: Commit GRI-68 without generated outputs**

```powershell
git status --short
git add -- build/templates tools/build_orders/emitters.py assets/scar/winconditions/'Macro Trainer.scar' tests/test_build_order_settings.py tests/test_build_order_build.py
git commit -m "feat: generate build-order setting for GRI-68"
```

Confirm ignored live RDO/CSV/SCAR outputs are absent from the staged set.

---

### Task 4: GRI-72 — Independent Sim-Rate Enable Setting

**Files:**
- Modify: `build/templates/assets/scar/winconditions/Macro Trainer.rdo`
- Modify: `build/templates/assets/locdb/Macro Trainer_en.csv`
- Modify: `assets/scar/winconditions/Macro Trainer.scar`
- Modify: `tests/test_simspeed_cycle.py`
- Modify: `tests/test_build_order_settings.py`

**Interfaces:**
- Consumes: existing `section_macro_trainer_settings` and timer functions.
- Produces option key: `option_enable_simspeed_cycle`, Boolean default `true`.
- Produces state: `_mod.simspeedEnabled = true`, `_mod.simspeedStarted = false`.
- Produces: `Mod_StartSimspeedCycle()` and `Mod_StopSimspeedCycle()`.

- [ ] **Step 1: Write failing Boolean-setting and lifecycle tests**

Require a `WinCondition::BooleanOptionUIDescriptor` with key `option_enable_simspeed_cycle`, `m_defaultValue=true`, and localized name/tooltip. Require `Mod_SetupSettings` to read a Boolean without conflating it with duration/rate values. Require `Mod_StartSimspeedCycle` to guard duplicate starts, compute durations, and enter the normal phase. Require `Mod_StopSimspeedCycle` to clear both transition rules, clear the phase objective, restore normal rate, and reset its started flag.

- [ ] **Step 2: Run focused tests and verify the red state**

Run:

```powershell
python -m unittest tests.test_simspeed_cycle tests.test_build_order_settings -v
```

Expected: FAIL because the option and separated lifecycle functions do not exist.

- [ ] **Step 3: Add the Boolean RDO option and localization**

Add the option after the existing slow-rate option. Use static localization text:

```text
Enable Slow/Normal Cycle
Alternate between configured normal-speed and slowed planning phases.
```

Preserve all existing option keys, object IDs, defaults, and localization rows.

- [ ] **Step 4: Separate timer startup and cleanup**

Refactor without changing phase math:

```lua
function Mod_StartSimspeedCycle()
    if _mod.simspeedStarted then
        return
    end
    _mod.simspeedStarted = true
    _mod.normalPhaseDuration = math.ceil(_mod.normalDurationSeconds)
    _mod.slowPhaseDuration = math.ceil(_mod.slowDurationSeconds * _mod.slowSimRate / NORMAL_SIM_RATE)
    Mod_StartPhase(NORMAL_PHASE_OBJECTIVE_TITLE, _mod.normalPhaseDuration, NORMAL_SIM_RATE, Mod_EnterSlowSpeed)
end
```

`Mod_Start` calls this function only when `_mod.simspeedEnabled`. `Mod_OnGameOver` calls `Mod_StopSimspeedCycle`. Transition callbacks return immediately when the cycle is not started.

- [ ] **Step 5: Run complete tests and generate baseline assets**

Run:

```powershell
python -m unittest discover -s tests -v
python tools/build_mod.py --build-orders build_orders --generate-only
```

Expected: all tests PASS; baseline generated RDO contains the enabled-by-default Boolean option.

- [ ] **Step 6: Commit GRI-72**

```powershell
git add -- build/templates assets/scar/winconditions/'Macro Trainer.scar' tests/test_simspeed_cycle.py tests/test_build_order_settings.py
git commit -m "feat: make simspeed cycle optional for GRI-72"
```

---

### Task 5: GRI-69 — Startup Validation, Paused Alert, and Resume

**Files:**
- Create: `assets/scar/build_orders/startup.scar`
- Create: `tests/test_build_order_startup.py`
- Modify: `build/templates/assets/locdb/Macro Trainer_en.csv`
- Modify: `assets/scar/winconditions/Macro Trainer.scar`
- Modify: `tests/test_simspeed_cycle.py`

**Interfaces:**
- Consumes: `_mod.selectedBuildOrderID`, `_mod.simspeedEnabled`, `BUILD_ORDER_CATALOG`, `BuildOrder_Start`, `BuildOrder_Stop`, `Mod_StartSimspeedCycle`, and `Mod_StopSimspeedCycle`.
- Produces: `BuildOrderStartup_Start()`, `BuildOrderStartup_ShowNoSystemsError()`, `BuildOrderStartup_ShowInvalidBuildError(buildOrder, actualCiv)`, `BuildOrderStartup_ShowError(title, message)`, `BuildOrderStartup_Continue(button)`, and `BuildOrderStartup_Stop()`.
- Uses official/high-confidence calls: `Game_GetLocalPlayer`, `Player_GetRaceName`, `Misc_SetSimRate`, `UI_MessageBoxSetText`, `UI_MessageBoxSetButton`, and official-SCAR-used `UI_MessageBoxShow`.

- [ ] **Step 1: Write the failing startup matrix tests**

Use source-contract helpers to require these exact branches:

| Selected build | Civ match | Cycle enabled | Required calls |
| --- | --- | --- | --- |
| valid | yes | yes | `BuildOrder_Start`, `Mod_StartSimspeedCycle` |
| valid | yes | no | `BuildOrder_Start` only |
| none | N/A | yes | `Mod_StartSimspeedCycle` only, no message |
| none | N/A | no | rate `0`, message, neither system |
| valid | no | yes | rate `0`, message; timer only from Continue |
| valid | no | no | rate `0`, message; neither system after Continue |

Require missing catalog IDs to use the invalid-build message path. Require the mismatch body to include build title, required civ, and actual `Player_GetRaceName(Game_GetLocalPlayer())`. Require only `DB_Button1`, label `Continue Without Build Order`, `DC_Default`, and callback `BuildOrderStartup_Continue`.

- [ ] **Step 2: Run startup tests and verify the red state**

Run:

```powershell
python -m unittest tests.test_build_order_startup -v
```

Expected: FAIL because the startup coordinator does not exist.

- [ ] **Step 3: Implement selection and civilization validation**

Implement this decision order:

```lua
if selectedID == nil then
    if _mod.simspeedEnabled then
        Mod_StartSimspeedCycle()
    else
        BuildOrderStartup_ShowNoSystemsError()
    end
    return
end

local buildOrder = BUILD_ORDER_CATALOG[selectedID]
local localPlayer = Game_GetLocalPlayer()
local actualCiv = string.lower(Player_GetRaceName(localPlayer))
if buildOrder == nil or actualCiv ~= buildOrder.civ then
    BuildOrderStartup_ShowInvalidBuildError(buildOrder, actualCiv)
    return
end

BuildOrder_Start(buildOrder, localPlayer)
if _mod.simspeedEnabled then
    Mod_StartSimspeedCycle()
end
```

Do not mutate the selected setting or sim-rate enabled setting.

- [ ] **Step 4: Implement the native message box with a deferred pause**

Set `_mod.buildOrderDisabled=true` and `_mod.startupAlertOpen=true`, then configure and show the message box while the simulation is still running:

```lua
UI_MessageBoxSetText(title, message)
UI_MessageBoxSetButton(
    DB_Button1,
    "Continue Without Build Order",
    "Resume the match without build-order objectives.",
    "",
    true)
UI_MessageBoxShow(DC_Default, BuildOrderStartup_Continue)
```

After `UI_MessageBoxShow`, replace any pending startup-pause rule with a `Rule_Add` callback. On the next simulation tick, that callback removes itself and sets the simulation rate to `0` only if the alert remains open. `BuildOrderStartup_Continue` returns unless the alert is open and `button == DB_Button1`; then it closes the guard, cancels any pending pause callback, restores `NORMAL_SIM_RATE`, and starts the timer only if enabled. It never starts the build-order engine. Shutdown also cancels the pending pause callback.

- [ ] **Step 5: Integrate startup and cleanup with the win-condition lifecycle**

Import `build_orders/startup.scar` after the generated catalog, engine, and timer functions are available. Replace direct timer startup in `Mod_Start` with `BuildOrderStartup_Start()`. In `Mod_OnGameOver`, call startup cleanup, build-order cleanup, and sim-rate cleanup exactly once each. Cleanup must be safe before or after message dismissal.

- [ ] **Step 6: Run focused and complete automated tests**

Run:

```powershell
python -m unittest tests.test_build_order_startup tests.test_build_order_objectives tests.test_simspeed_cycle -v
python -m unittest discover -s tests -v
```

Expected: all tests PASS.

- [ ] **Step 7: Validate APIs and commit GRI-69**

Run the AoE4 code checker over the complete main, engine, and startup SCAR sources. Accept `UI_MessageBoxShow` only with its exact high-confidence official usage signature `UI_MessageBoxShow(DC_Default, callback)`. Commit:

```powershell
git add -- assets/scar/build_orders/startup.scar assets/scar/winconditions/'Macro Trainer.scar' build/templates/assets/locdb/'Macro Trainer_en.csv' tests/test_build_order_startup.py tests/test_simspeed_cycle.py
git commit -m "feat: handle invalid build selections for GRI-69"
```

---

### Task 6: GRI-71 — Integration, Package Verification, and Issue Completion

**Files:**
- Modify if required by integration only: `README.md`
- Verify: every file changed by Tasks 1–5
- Do not commit: ignored generated RDO, CSV, or SCAR outputs

**Interfaces:**
- Consumes: all five issue commits and `tests/fixtures/build_orders/valid/english_opening.yaml`.
- Produces: one integrated GRI-71 branch with passing generation, SCAR validation, and a fresh `.aoe4mod` package.

- [ ] **Step 1: Integrate issue commits in dependency order**

Cherry-pick the reviewed GRI-67, GRI-66, GRI-68, GRI-72, and GRI-69 commits into the integration worktree. After each cherry-pick run:

```powershell
python -m unittest discover -s tests -v
```

Expected: all currently available tests PASS after every issue boundary.

- [ ] **Step 2: Verify clean authoritative/generated boundaries**

Run generation twice, deleting the fixture YAML from a temporary copied input directory between runs. Assert the second SCAR/RDO/CSV outputs contain no deleted build ID. Run:

```powershell
git status --short
git ls-files --error-unmatch 'assets/scar/winconditions/Macro Trainer.rdo'
git ls-files --error-unmatch 'assets/locdb/Macro Trainer_en.csv'
git ls-files --error-unmatch 'assets/scar/generated/build_orders.scar'
```

Expected: each `git ls-files --error-unmatch` exits nonzero because outputs are ignored, while tracked templates and YAML sources remain clean.

- [ ] **Step 3: Run the complete automated suite**

```powershell
python -m unittest discover -s tests -v
```

Expected: all tests PASS with no skipped compiler, settings, objective, timer, or startup tests.

- [ ] **Step 4: Validate complete SCAR source**

Pass `assets/scar/winconditions/Macro Trainer.scar`, `assets/scar/build_orders/objective_engine.scar`, `assets/scar/build_orders/startup.scar`, and the generated catalog to the AoE4 code checker. Unknown calls are failures. The documented-low `UI_MessageBoxReset` is not required; the official-use `UI_MessageBoxShow(DC_Default, callback)` pattern is allowed with a recorded note.

- [ ] **Step 5: Run a real Essence build with fixture data**

First display the exact external command implied by the wrapper and obtain the required build confirmation. Then run:

```powershell
python tools/build_mod.py --build-orders tests/fixtures/build_orders/valid
```

Expected: exit `0`, a newly written package for `Macro Trainer.aoe4mod`, and generated local inputs containing the English fixture. A nonzero launcher exit, missing package, or stale package timestamp fails this step.

- [ ] **Step 6: Complete the manual playtest matrix**

Verify in-game:

1. Valid matching build with cycle enabled: build objectives and timer both start.
2. Valid matching build with cycle disabled: only build objectives start at normal speed.
3. No build with cycle enabled: timer starts without an alert.
4. No build with cycle disabled: game pauses, message is readable, Continue resumes normal speed with neither system.
5. Mismatched build with cycle enabled: game pauses, message names build/required/actual civs, Continue starts only the timer.
6. Mismatched build with cycle disabled: Continue resumes normal speed with neither system.
7. Titled steps render only the supplied title; untitled steps render `Step N`.
8. Child checks appear as normal secondary objectives and remain pending without production handlers.
9. Ending the match from normal and paused states leaves no active build-order objective or timer callback.

- [ ] **Step 7: Review final diff and commit integration-only corrections**

```powershell
git diff --check origin/main...HEAD
git status --short
git log --oneline --decorate origin/main..HEAD
```

If integration required a correction, stage only that correction and commit:

```powershell
git commit -m "fix: integrate build-order objectives framework"
```

Do not create an empty integration commit.

- [ ] **Step 8: Update Linear only after verification**

Move GRI-66, GRI-67, GRI-68, GRI-69, and GRI-72 to Done only after their issue commit is integrated and the full automated suite passes. Move GRI-71 to Done only after the SCAR validation and real Essence build pass; record any manual playtest items that require the user's local confirmation rather than representing them as completed.
