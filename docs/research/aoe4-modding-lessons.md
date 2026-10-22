# AoE4 Modding Lessons

Extracted from Codex session logs (Aug–Sep 2026) and corrected by hand. Items marked *unverified* came from mid-debug hypotheses and were not confirmed in-game.

## Callbacks and rules

- `Rule_Add`, `Rule_AddGlobalEvent`, etc. require **named global functions**. Anonymous closures are rejected ("Adding unnamed function as rule; this is not allowed"). Generate one named global per callback if needed.
- `UI_CreateCommand(callbackName)` takes a **string** naming a global function, not a function value.
- Don't mutate a table while a callback is iterating it with `pairs` (e.g. completing a check inside `Vils_PollAll` mutated `VILS_STATE`, which was fatal). Batch updates instead.
- `Rule_RemoveGlobalEvent` exists; remove subscriptions when the last consumer deactivates.

## Imports

- Every handler file must be reachable from the root wincondition (`winconditions/Macro Trainer.scar`). GRI-55–62 handlers silently never registered because their files were never imported at all.
- Nothing established that imports must live directly in the root file. Transitive reachability was the tested contract. *In-game behavior of nested imports is unverified.*

## Lobby settings

- `Mod_SetupSettings` is not an engine hook. Call `Setup_GetWinConditionOptions(options)` in `Mod_OnInit`, then pass the table on yourself.
- `enum_value` is opaque. Recover the key by reverse lookup over `enum_items`, which maps `enum_key -> opaque_value` directly (not `{key, value}` records).

## Game APIs

- Sim speed: `Misc_SetSimRate(rate)`. `setsimrate` does not exist.
- Pausing via sim rate 0 before showing a dialog can prevent the dialog's callback from dispatching. Show first, then pause.
- `Obj_CreatePopup(objectiveID, title, templateOverride)` takes three args; `""` keeps the default template. The "New Objective!" heading is hardcoded in the `TA_xbox_NewObjective` XAML style.
- An arity error like "expected 3, got 2" once came from the game loading a stale archive, not the source. Confirm the loaded build is fresh.
- PBG wrappers are opaque; two wrappers for the same blueprint can compare unequal. Compare fields structurally.

## Datastore

- Path argument is always `""`.
- `Game_LoadTextDataStore` is synchronous.
- `Game_RetrieveTableData(id, clear)` returns the table directly.
- Files live under `<Documents>/My Games/Age of Empires IV/Users/<profile-id>/datastore/<id>.rlt`.

## Events

- Construction: only `GE_ConstructionComplete` is a reliable terminal signal. Earlier construction events can mean start, worker attach, cancel, or death.
- Production: `GE_EntityCommandIssued` (command type 3) fires on queue insertion, not production start. `GE_BuildItemComplete` gives player, full PBG, and spawned squad ID.

## UI (XAML)

- Custom UI is SCAR-injected XAML: `UI_AddChild("ScarDefault", "XamlPresenter", name, { DataContext = UI_CreateDataContext(view), ... })`, commands via `UI_CreateCommand`, refresh via `UI_SetDataContext`. The Content Editor does not package standalone XAML.
- The engine supports rich UI (scrolling item lists with icons, tabs, full-screen hover grids; see the unreleased UUT 2.0 mod). Our problems were missing knowledge, not engine limits.
- Calling `UI_SetDataContext` inside a command callback that rebuilds the collection whose selection fired it re-enters the UI update and crashed the game. Bind dependent views to the control's `SelectedItem` / pass it as `CommandParameter` instead.
- Dropdown selection never reached SCAR with either `CallCommandTrigger` or `EventTrigger` + `CallCommandAction` on `SelectionChanged`. Root cause unknown.
- References: shipped game XAML (aoe4-mcp `find_ui` / `trace_ui_binding`), [AoE4_ObserverUI](https://github.com/kuschAoe/AoE4_ObserverUI), BoonUI in [AOE4_Mods_ComradPing](https://github.com/GPK-GIT5/AOE4_Mods_ComradPing), [aoemods wiki: Custom UI elements](https://github.com/aoemods/wiki/wiki/Custom-UI-elements).

## Debugging

- The SCAR log and `warnings.log` live under `E:\Docs\My Games\Age of Empires IV\` (Documents is redirected to `E:\Docs`). Read them before guessing at UI or callback failures.
