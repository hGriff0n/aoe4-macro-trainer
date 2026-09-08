# Task 7 Report: API Audit, Package Build, and Final Regression Evidence

## Status

Completed the repository, automated, AoE4 MCP, XAML-support, localization-generation, and user-confirmed Content Editor package checks in the isolated `gri-109-110-build-order-ui` worktree.

- Steps 1-4: completed with fresh evidence below.
- Step 5: **not executed in game**. The nine-item manual acceptance checklist is preserved below with automated proxy evidence, but those checks still require an interactive match.
- Step 6: no verification defect was found, so no source/test fix and no empty commit were created.

Branch head remained `4b1e63e633b6837a09863bb746d923ac5faea150` (`fix: address paused startup review findings`). The package build changed no tracked files.

## Exact branch delta

`git merge-base origin/pr/19 HEAD` resolved to `082f4be321ba2e1bc5143a23bd0bc1e131d682f7`. `git diff --name-status origin/pr/19...HEAD` reported this complete 20-file branch delta:

```text
M  assets/locdb/Macro Trainer_en.csv
M  assets/scar/build_orders/datastore.scar
A  assets/scar/build_orders/editor.scar
A  assets/scar/build_orders/editor_discovery.scar
A  assets/scar/build_orders/editor_model.scar
A  assets/scar/build_orders/editor_schema.scar
A  assets/scar/build_orders/editor_ui.scar
M  assets/scar/build_orders/startup.scar
M  assets/scar/winconditions/Macro Trainer.scar
A  docs/superpowers/plans/2026-09-06-gri-109-110-build-order-ui.md
A  docs/superpowers/specs/2026-09-06-gri-109-110-build-order-ui-design.md
A  tests/scar_runtime.py
M  tests/test_build_order_datastore.py
A  tests/test_build_order_editor.py
A  tests/test_build_order_editor_discovery.py
A  tests/test_build_order_editor_model.py
A  tests/test_build_order_editor_ui.py
M  tests/test_build_order_import_graph.py
M  tests/test_build_order_startup.py
M  tests/test_simspeed_cycle.py
```

The production audit set is therefore exactly the eight SCAR files named in the Task 7 brief plus `assets/locdb/Macro Trainer_en.csv`. There are no branch-delta `.xaml` files; the feature XAML is the inline document in `editor_ui.scar`.

## Step 1: whitespace and repository state

Fresh checks before the final report:

```text
git diff --check origin/pr/19...HEAD
exit 0; no output

git status --short
no output
```

The same clean status was observed after the Content Editor build and after archive/localization inspection. Ignored `cache/`, `archives/`, and this SDD handoff report do not appear in tracked status.

## Step 2: complete automated suite

Fresh complete suite:

```text
python -m unittest discover -s tests -p "test_*.py" -v
Ran 363 tests in 1.451s
OK
```

A diagnostic rerun that wrapped this command inside a PowerShell output-capture expression produced 89 `PermissionError` cleanup errors under `C:\Users\ghoop\AppData\Local\Temp`. Root-cause isolation showed that the wrapper bypassed the approved direct `python -m unittest` command path and caused the restricted sandbox to deny access inside newly created temporary directories; a minimal `tempfile.TemporaryDirectory` probe reproduced the same boundary failure before any project code ran. Reissuing the unchanged command directly, exactly as shown above, restored the intended execution context and passed all 363 tests. No repository change was involved or needed.

Fresh packaged-import graph suite:

```text
python -m unittest tests.test_build_order_import_graph -v
Ran 5 tests in 0.008s
OK
```

The latter specifically confirms the editor modules are reachable exactly once from the packaged root and remain in dependency order before startup.

## Step 3: complete AoE4 MCP SCAR audit

Each changed production SCAR file was read in full from the isolated worktree and submitted to a fresh AoE4 MCP `check_code` call with its absolute target path.

| Complete SCAR file | Status | Calls | Raw unknown calls | Low-confidence APIs | Missing locdb IDs |
| --- | --- | ---: | --- | --- | --- |
| `assets/scar/build_orders/datastore.scar` | `ok` | 19 | `[]` | `Game_SaveTextDataStore` | `[]` |
| `assets/scar/build_orders/editor_discovery.scar` | `ok` | 33 | `[]` | `[]` | `[]` |
| `assets/scar/build_orders/editor_model.scar` | `ok` | 51 | `["and"]` | `[]` | `[]` |
| `assets/scar/build_orders/editor_schema.scar` | `ok` | 5 | `[]` | `[]` | `[]` |
| `assets/scar/build_orders/editor_ui.scar` | `ok` | 55 | `["and"]` | `[]` | `[]` |
| `assets/scar/build_orders/editor.scar` | `ok` | 43 | `[]` | `[]` | `[]` |
| `assets/scar/build_orders/startup.scar` | `ok` | 34 | `[]` | `[]` | `[]` |
| `assets/scar/winconditions/Macro Trainer.scar` | `ok` | 36 | `[]` | `[]` | `[]` |

The two raw `and` results are tokenizer false positives, not calls. Direct source inspection located ordinary Lua boolean expressions:

- `editor_model.scar:541`: `value ~= nil and (type(value) ... )`
- `editor_model.scar:645`: `type(step) == "table" and (type(step.checks) ... )`
- `editor_ui.scar:744`: `type(option) == "table" and (option.id or option.ids) ...`
- `editor_ui.scar:770`: a continued `and (...)` condition

There is no function invocation named `and`, and no production call is unresolved.

`Game_SaveTextDataStore` was independently resolved with `api_context` and `find_api` to the exact official declaration in `official_api/Essence_ScarFunctions.api:945`:

```text
Game_SaveTextDataStore(String id, String path)
Save text data store to disk
source_set=official_api; exact-name match; overall confidence=high (0.943)
```

The declaration's own documentation-quality field is low and the MCP has no usage sample, which is why `check_code` reports it in `low_confidence_apis`; it is nevertheless an exact documented official API, not an unknown call.

`check_code` reports `loc_ref_count=0` for this feature because its references live in inline XAML and localization constants. The CSV/generated-output cross-check below covers them independently.

## XAML-sensitive validation

Fresh focused executable checks:

```text
python -m unittest \
  tests.test_build_order_editor_ui.BuildOrderEditorUIContractTests.test_pointer_reorder_uses_all_three_routed_events_and_command_parameters \
  tests.test_build_order_editor_ui.BuildOrderEditorUIContractTests.test_static_xaml_labels_use_stable_fully_qualified_localization \
  tests.test_build_order_editor_ui.BuildOrderEditorUIProjectionTests.test_nested_objects_and_object_list_entries_project_and_render_recursively \
  tests.test_build_order_editor_ui.BuildOrderEditorUIProjectionTests.test_recursive_projection_uses_stable_paths_expansion_and_exact_errors \
  tests.test_build_order_editor_ui.BuildOrderEditorUIProjectionTests.test_projected_check_kind_options_use_stable_localized_labels \
  tests.test_build_order_editor_ui.BuildOrderEditorUIProjectionTests.test_projected_optional_field_uses_stable_localized_label -v
Ran 6 tests in 0.035s
OK
```

These tests parse the complete inline XAML as XML, verify the two drag handles and the three routed pointer phases, require each `CallCommandAction`/command parameter, require the recursive object/list projection and `DynamicResource BuildOrderFieldTemplate` references, and resolve all static/projected localization keys.

AoE4 MCP `find_ui` added engine-source evidence:

- It indexed the exact project `EventTrigger` + `CallCommandAction` composition for `UIElement.PreviewMouseLeftButtonDown` at inline-XAML lines 281 and 361, `UIElement.MouseEnter` at lines 264 and 344, `UIElement.MouseLeave` at lines 268 and 348, and `UIElement.PreviewMouseLeftButtonUp` at line 523. It found both the source document and cached project copy.
- Official UI results independently demonstrate `UIElement.PreviewMouseLeftButtonDown` and `UIElement.MouseLeave` routed events. Official inline XAML demonstrates `esActions:CallCommandAction`, and official UI includes `ItemTemplate="{DynamicResource ...}"` usage.
- It indexed the project `BuildOrderFieldTemplate`, `BuildOrderObjectCardTemplate`, and `BuildOrderListItemTemplate` resource definitions and their static consumers.
- No exact official result combined this particular pointer-event/`CallCommandAction` pairing, and an exact project search for `{DynamicResource BuildOrderFieldTemplate}` returned no match even though direct source/XML assertions find both recursive references. This is a `find_ui` search/index limitation, not proof of runtime template resolution.

The Content Editor package build below found no XAML diagnostic, but packaging inline XAML is not a substitute for instantiating it in the running HUD. The pointer and recursive-template items therefore remain explicit in the manual in-game checklist.

## Step 4: resolved user-confirmed Content Editor build

After explicit user confirmation, the controller invoked exactly one build from the `.aoe4mod` parent directory, following the worktree's `aoe4mod-build` skill:

```powershell
& 'F:\Program Files (x86)\Steam\steamapps\common\Age of Empires IV Content Editor\EssenceLauncher.exe' --build_mod 'E:\Docs\github\aoemod\aoe4-macro-trainer\.worktrees\gri-109-110-build-order-ui\Macro Trainer.aoe4mod' --auto_close_burn_window
```

The launcher returned exit code 0 in 0.131 seconds with no stdout/stderr. Because that quick return can represent delegation to the editor process, completion was checked from persistent output rather than inferred from launcher timing:

- `E:\Docs\My Games\Age of Empires IV\EssenceEditorLog.txt` was created at `2026-09-07T22:55:23.0801051Z` and finalized at `2026-09-07T22:55:31.9942339Z`.
- Log line 242 records `Building [...]Macro Trainer.aoe4mod...` for the exact isolated worktree.
- Log line 255 records `Loaded 2 data objects`.
- Log line 256 records the worktree archive copied into the local installed-mod directory.
- Targeted complete-log counts were `SCAR=0`, `XAML=0`, `locdb=0`, `missing loc=0`, `compile error=0`, `parse error=0`, and `syntax error=0`. The only `localization` matches are the normal subsystem load/unload steps.
- Lines 251-252 contain a nonfatal Content Editor bootstrap warning about missing `generic:editor\mecommand.lua`. It is not a project SCAR, XAML, or localization diagnostic, and the editor immediately proceeded to load the mod data, write/copy the archive, and shut down normally.

Fresh package artifact:

```text
path:     archives/Macro_Trainer.sga
size:     1,539,855 bytes
created:  2026-09-07T22:55:30.0679822Z
modified: 2026-09-07T22:55:31.6097473Z
SHA-256:  BE86533D8D6DD67E323C3C0620A30C2FC4407232AE890AF52E6E1F4DFD5EAD17
```

The installed copy at `E:\Docs\My Games\Age of Empires IV\mods\extension\local\Macro Trainer\Macro_Trainer.sga` has the same byte length, modification timestamp, and SHA-256 digest.

### Localization generation evidence

The build generated a fresh UTF-16 `cache/.../en/en.ucs` at `2026-09-07T22:55:30.1241659Z`. An exact read-only comparison of the source CSV and generated UCS found:

```text
CSV_COUNT=80
UCS_COUNT=80
REFERENCED_ID_COUNT=53
CSV_TO_UCS_MISSING=
CSV_TO_UCS_MISMATCH=
UCS_EXTRA=
SCAR_REFS_MISSING_CSV=
SCAR_REFS_MISSING_UCS=
```

Thus all 80 source rows, including new IDs 31-83, were emitted with exact English text; no generated row is missing, changed, or extra; and every fully-qualified localization ID referenced by the editor/schema/startup SCAR exists in both source and generated output. No tracked localization artifact changed during the build.

## Step 5: pending manual in-game acceptance

No interactive Age of Empires IV match was launched from this verification task. These checks are therefore **not claimed as manually passed**. The following is the prepared acceptance record with the strongest fresh automated proxy for each item:

- [ ] Startup pauses and shows the local civilization selector. Proxy: `test_start_collects_local_orders_schedules_pause_and_is_idempotent` passed.
- [ ] No-order unpause requires confirmation. Proxy: `test_no_order_requires_confirmation_and_starts_only_enabled_cycle` passed.
- [ ] Create, edit, rename, and copy persist across a new match. Proxies covering transitions, rename/copy, datastore mutation, and persistence dispatch passed; cross-match disk durability still requires the manual match restart.
- [ ] The editor is single-column with nested, expandable, draggable step/check cards. XAML structure, recursive projection, all routed events, shared reorder behavior, and drag-state regressions passed; runtime HUD interaction remains manual.
- [ ] English entity-landmark and Abbasid/Ayyubid-style technology age-ups discover and save correctly. Discovery-kind, canonical conversion, and valid-save tests passed; live engine PBG discovery remains manual.
- [ ] Later-step option lists advance only after preceding `age_up` checks. `test_inferred_age_is_entering_age_and_only_age_up_advances_next_step` and `test_age_up_mutation_recomputes_step_ages_and_live_option_filter` passed.
- [ ] Spearman is selected as one family and saves all compatible canonical variants. Family discovery/conversion tests and `test_owned_living_spearman_tiers_count_as_one_family_and_reverse_when_lost` passed.
- [ ] Missing display metadata falls back to the internal ID and missing age falls back to Age I. Discovery normalization and live-projection fallback tests passed.
- [ ] Save writes all existing build orders, not only the modified one. `test_apply_replaces_or_renames_the_catalog_entry_then_saves_once` and `test_save_catalog_stores_the_live_catalog_then_saves_the_datastore` passed.

The 16-test acceptance-proxy run completed in 0.131s with `OK`. It included the startup, create/copy/rename/save, age-up, family, fallback, and whole-catalog tests named above.

## Step 6: fixes and commits

Verification exposed no production defect. No test was weakened, no source file was modified, and no fix or empty commit was created. This ignored handoff report is the only authored Task 7 file.

## Remaining acceptance boundary

The feature branch is automated-suite verified, complete-SCAR audited, localization-generation verified, and successfully packaged/installed by the Content Editor. Task 7 as a whole should not be described as fully accepted until the nine unchecked behaviors above have been exercised in an actual match, especially runtime creation of the inline XAML's routed pointer actions and recursive dynamic-resource templates and persistence across a second match.

## Final review-fix wave (2026-09-08)

Review head `4b1e63e633b6837a09863bb746d923ac5faea150` received one final focused fix wave. Every finding was first reproduced with an executable or contract RED test, then corrected and rechecked:

- Race PBG identity is now separate from canonical draft/startup civ identity (`Player_GetRace` for race-extension filtering; `Player_GetRaceName` plus the shared canonical conversion for persisted civ IDs). A non-string race-handle create/save regression and an alias/startup compatibility test are green.
- Discovery now has dedicated local `buildings`, `technologies`, and `age_ups`; uses documented type predicates and player-scoped upgrade costs; and offers only the exact inferred next-age candidates.
- The advertised `buildings` schema kind has an imported, registered polling handler with owner, completion, PBG, conversion/loss, and deactivation coverage. Every advertised nonoptional kind has a handler contract.
- Editor runtime IDs use `order:step:check_index`, and controller Save output round-trips through the Python datastore parser.
- Unit-family selection preserves `{label, icon, ids}` through the actual UI/controller save path while runtime payloads retain canonical IDs, covering Produce and Units titles.
- Datastore Store/Save dispatch exceptions roll back original/destination catalog identity and permit retry.
- Stable loc IDs 84–141 cover dynamic schema labels, entering-age text, validation/save errors, and friendly error labels; raw dotted paths no longer render in validation messages.
- Live candidate count is tracked before saved fallback insertion, so a saved fallback cannot hide an empty discovery state.

Final AoE4 MCP project scan was `ok`. `check_code` returned `ok` with no missing locdb IDs for every changed SCAR file. The only reported low-confidence API remains the exact official `Game_SaveTextDataStore` declaration with no indexed usage sample; `and`, `or`, and the freshly declared startup helper are checker parser/index artifacts, not unresolved production calls. The Content Editor was deliberately **not** run during this fix wave, per controller instruction; rebuild and in-game confirmation remain the explicit acceptance boundary.

The final direct Python command, `python -m unittest discover -s tests -p "test_*.py" -v`, completed with **388 tests, OK**. `git diff --check` was rerun before commit.
