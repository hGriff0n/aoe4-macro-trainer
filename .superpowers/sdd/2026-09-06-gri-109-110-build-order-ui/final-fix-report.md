# GRI-109/110 Final Review-Fix Report

## Scope and result

This is the single final review-fix wave from review head `4b1e63e633b6837a09863bb746d923ac5faea150`. It addresses all eight reported findings without running the Content Editor, opening a PR, pushing, or changing unrelated work.

## Finding evidence

| Finding | Focused RED | GREEN correction and coverage |
| --- | --- | --- |
| 1. Race identity | An executable create/save flow with a non-string `Player_GetRace` handle produced no canonical `civ`. | Discovery preserves the race handle only for blueprint race filtering and derives the draft civ from `Player_GetRaceName`, normalized through `BuildOrderDiscovery_CanonicalCivID`. The full controller create/save test now saves `english`; startup reuses the same canonical conversion, with a RED/GREEN alias compatibility test. |
| 2. Candidate classification | Mixed entities/upgrades initially exposed no dedicated valid building/technology/age-up categories. | Discovery exposes `buildings`, `technologies`, and `age_ups`; it rejects non-buildings and foreign/unavailable upgrades, recognizes local landmark or local-civ upgrade age-ups, and the UI applies an exact `current age + 1` filter for age-up choices. Executable mixed-civ/non-building/ordinary-upgrade/exact-age tests pass. |
| 3. Advertised `buildings` kind | Contract coverage found the nonoptional schema kind had no handler/import. | Added `checks/buildings.scar`, imported it from the root, and registered it. Its polling behavior handles ownership, PBG identity, construction completion, loss/conversion, and final deactivation. The executable handler and every-advertised-kind contract pass. |
| 4. Check identifiers | Editor-generated IDs did not match the Python datastore parser's canonical `order:step:check_index` format. | Conversion assigns a single monotonically increasing check index per runtime step. A controller Save output is embedded in a Lua datastore and parsed by the Python parser successfully. |
| 5. Family presentation | Selecting a family reduced it to IDs, so UI/controller save paths lost the chosen label and icon for produce/units titles. | Normalized options retain deep-copied `{label, icon, ids}` values through field change; conversion still serializes canonical IDs. Actual UI-command-save tests cover both Produce and Units titles. |
| 6. Save exception rollback | Exceptions from Store/Save left the catalog mutated. | `BuildOrderDatastore_Apply` snapshots original and destination entries, wraps persistence dispatch, restores object identity on either persistence exception, and permits a subsequent retry. |
| 7. Dynamic localization | Schema/age/error projection tests saw raw English strings and internal dotted error paths. | Added stable English IDs 84–141, schema/error maps, an age label plus separate number binding, localized validation/save messages, and friendly field labels. Projection/error tests resolve every new token and no longer render raw paths. |
| 8. Empty discovery state | Saved fallback options made the live list nonempty and hid the empty state. | The UI now records the live candidate count before adding a saved fallback and bases empty-state visibility on that count. The saved-fallback/zero-live-candidate test passes. |

## API decisions

- `Player_GetRace` is retained as the opaque race/PBG handle for entity and squad race-extension comparisons. `Player_GetRaceName` is officially documented as the English race name, and official core code records both separately; it is the canonical draft/startup civ source.
- `Entity_IsEBPOfType` is the official entity type predicate used for building, landmark, and age filtering. `BP_IsUpgradeOfType` is the official upgrade type predicate used for age-up upgrade classes.
- `Player_GetUpgradeBPCost(player, upgradePBG)` is a documented player-scoped official API. A non-`nil` cost is the available tech-tree inference used to exclude foreign/nonlocal upgrades; no unsupported `Player_CanResearch` predicate was introduced. This inference should still be checked in a live match after the next authorized package rebuild.
- The `buildings` handler uses documented `Entity_IsBuilding` and `Entity_GetBuildingProgress >= 1.0`, matching official usage for completed buildings.
- `Game_SaveTextDataStore` remains an exact official API declaration. MCP marks its documentation low-confidence because it has no indexed usage sample, not because it is unknown.

## Verification

- Focused RED→GREEN tests were run for each finding and for the startup canonical-conversion alignment.
- `python -m unittest tests.test_build_order_startup -v`: 15 tests, OK after the final startup alignment.
- `python -m unittest discover -s tests -p "test_*.py" -v`: 388 tests, OK.
- `git diff --check` is rerun before commit.
- AoE4 MCP `scan_project`: status `ok` for the isolated worktree.
- AoE4 MCP `check_code`: status `ok` and no missing locdb IDs for every changed SCAR file: datastore, discovery, model, schema, UI, editor, startup, the new buildings handler, and the root wincondition importer. The checker reports ordinary Lua `and`/`or` tokens and the newly declared startup helper as unknown-call parser artifacts; direct source inspection confirms they are not unresolved calls.

## Files changed

- Discovery, model/schema/UI/controller, datastore, startup, root importer, new buildings handler, and English locdb.
- Focused runtime/contract tests for discovery, editor/controller/model/UI, datastore, startup, the new buildings handler, and SCAR runtime support.

## Remaining concern / acceptance boundary

The code and SCAR audits are automated-green, but this fix wave intentionally did not run the Content Editor or an in-game match. After a user-authorized rebuild, live-engine confirmation should exercise actual local civ aliases, local tech-tree availability, dynamic inline-XAML localization, and the buildings handler in a match.
