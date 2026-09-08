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

## Re-review round 2 (2026-09-08)

### RED/GREEN evidence

| Re-review finding | Focused RED | GREEN correction and coverage |
| --- | --- | --- |
| Canonical civ aliases | `test_canonical_civ_aliases_cover_every_supported_civilization` initially exposed the incomplete three-alias table: 13 official/current-race aliases did not resolve to repository canonical IDs. | `BUILD_ORDER_DISCOVERY_CIV_ALIASES` now covers every supported `SOURCE_CIVILIZATIONS` target and current official race-name variants. The table-driven executable test covers all supported civs, including `byzantine -> byzantines`, `mongol -> mongols`, and `ottoman -> ottomans`; the existing startup test confirms it calls the same discovery canonical helper. |
| Technology availability and landmarks | The mixed discovery behavior test failed because landmarks were routed out of `buildings`; it expected each local landmark as both `building` and `age_up`. | `Collect` now creates two independent option records for a local landmark, preserving its building entry while adding its age-up entry. The focused test also proves a `nil` player upgrade cost is excluded. |
| Friendly error paths | `steps.1.checks.1.payload` rendered the ancestor `Checks` token (`:89`) instead of a semantic field label. | Added the stable `Check details` localization entry (`:142`), a `payload -> check_details` mapping, and an expanded table-driven projection test for every schema/path semantic key. No dotted internal path is rendered. |

### Live upgrade API decision and residual limitation

AoE4 MCP was checked for documented `upgrade`, `research`, `technology`, `tech tree`, `availability`, `race`, and player-query APIs. The high-confidence non-mutating upgrade APIs are `BP_GetUpgradeBlueprint`, `BP_GetUpgradeUIInfo`, `BP_IsUpgradeOfType`, `Player_GetUpgradeBPCost`, and `Player_HasUpgrade`; the last reports already-purchased state. There is no documented `Player_CanResearch`, `Player_CanUpgrade`, available-upgrades/tech-tree enumeration, or upgrade `type_ext` race query. `Entity_QueueProductionItemByPBG` is documented to push an item onto a queue, so it is not a safe discovery probe.

The implementation therefore keeps `Player_GetUpgradeBPCost(player, pbg) ~= nil` as the only player-specific, non-mutating live best-effort availability filter. Its helper and comment explicitly state that it is **not** a guaranteed civilization/tech-tree membership predicate. No static/generated civ-to-upgrade catalog or naming heuristic was added. A user-authorized rebuild must include manual cross-civilization technology selection verification, especially a foreign upgrade with a non-`nil` cost.

### Round-2 files and verification

- Changed: `editor_discovery.scar`, `editor_schema.scar`, `editor_ui.scar`, English locdb entry `142`, and focused discovery/UI tests.
- Focused RED→GREEN: landmark dual-list behavior, best-effort availability contract, canonical-alias table, and semantic path labels.
- Focused suites: discovery (21), UI (32), and startup (15) tests passed.
- Full direct suite: `python -m unittest discover -s tests -p "test_*.py" -v` — **390 tests, OK**.
- AoE4 MCP `scan_project` returned `ok`. Complete-file `check_code` checks returned `ok`, with no missing locdb IDs for discovery, schema, and UI. The UI checker still classifies Lua `and`/`or` as parser artifacts; they are not calls.
- No Content Editor, package build, push, or PR was run in this round.
