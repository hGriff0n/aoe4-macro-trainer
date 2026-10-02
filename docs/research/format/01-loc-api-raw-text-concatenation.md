# 01: LocString API, raw text, and concatenation in AoE4 SCAR

Sources: the aoe4-mcp index (`index.sanitized.sqlite3`). That covers the official API doc `official_api/Essence_ScarFunctions.api` (`.api` line numbers are shown as `api:N`), official SCAR source (`official_scar/...:line`), official XAML (`official_ui/...`), and the official locdb (`official_loc/cardinal.*.ucs`, 26 locales).

Evidence tags:
- **[DOC]**: the official API doc says so.
- **[USE]**: official SCAR or XAML code does it. The file:line is from `code_records`.
- **[INF]**: inferred or unverified. It needs an in-game test.

The index has no full source files, only line snippets. Some context below is pieced together from adjacent snippets.

---

## TL;DR

| Need | Do this | Evidence |
|---|---|---|
| Localized text by ID | `Loc_GetString(11161290)` or `Loc_GetString("$11161290")`. Most display APIs also accept the bare number or the `"$id"` string. | [USE] |
| Text with parameters | `Loc_FormatText(id, arg1, arg2, ...)`. The args can be numbers, LocStrings, or `"$id"` strings. | [USE] |
| Show a raw Lua string (player-typed or built in Lua) | `Loc_FormatText(<key whose text is "%1TEXT%">, luaString)`. The official key `11252841` is `%1TEXT%` in all 26 locales. The other option is `LOC(luaString)`, which the doc labels **DEV ONLY**. | [INF] for the Lua-string arg. `LOC` is [DOC]+[USE]. |
| Join two display strings | `Loc_FormatText(11252837, a, b)` (text is `%1TEXT%%2TEXT%`). There are 3-way and 4-way variants (`11252839`, `11252840`). | key: [USE] locdb. Joining with it: [INF] |
| LocString to Lua string (logging, XAML data context) | `Loc_ToAnsi(loc)` or `loc.LocString` | [USE] |
| `a .. b` where either side is a LocString | **Don't.** No official code does this. Convert with `Loc_ToAnsi` first (which drops localization), or use a join key. | [INF] |

---

## 1. Complete `Loc*` API surface

The only `.api` file in the index is `Essence_ScarFunctions.api`. It documents exactly eight `Loc`-family functions. Two more (`Loc_FormatText` and `Loc_ToAnsi`) exist only in Lua or in practice.

| Function | Signature (doc) | Returns | What it does | Official usage | Confidence |
|---|---|---|---|---|---|
| `LOC` | `LOC(String string)` | LocString | "**DEV ONLY**: Converts ansi text to localized text." [DOC api:1001] | `gamesetup.scar:317-320` (message box), `scarutil.scar:147` (`playerName = LOC(playerName)`, "accept raw strings for now... convert them to LocString"), `scarutil.scar:2600,2603` (→ `Game_TextTitleFade`), `scarutil.scar:3931` (→ `UI_SystemMessageShow`), `missionomatic_actionlist.scar:395` (→ `UI_CreateEventCue`), `event_cues.scar:301` (`_ReturnLocVersion`: ST_STRING → `LOC(item)`), `combat_mode.scar:799` (`LOC("")`) | High that it exists and works. **Shipping use is risky because of the DEV ONLY label.** It does appear in shipping game modes (combat_mode, missionomatic). |
| `Loc_Empty` | `Loc_Empty()` | LocString | "Returns an empty localized string." [DOC api:1002] | 150 calls, for example `ui.scar` event cue descriptions and `cardinal.scar:582,586` (fallback when an arg isn't ST_LOCSTRING) | High |
| `Loc_GetString` | `Loc_GetString(StackVar id)` | LocString | "Returns the localized string identified by the specified id." [DOC api:1008] | Accepts a number (`combat_mode.scar:1215` `Loc_GetString(11161290)`), a `"$id"` string (`campaignpanel.scar:51` `Loc_GetString("$11180928")`), **and an existing LocString** (`campaignpanel.scar:505,1416` `Loc_GetString(Player_GetDisplayName(player))`, `campaignpanel.scar:1446` normalizes ST_LOCSTRING or `"$..."`) | High |
| `Loc_FormatText` | Lua wrapper. `--? @args Integer FormatID[, argc parameters]`, `--? @result LocString`. `function Loc_FormatText(LocID, ...) local arg = {...} return Loc_FormatTextInternal(LocID, arg)` | LocString | Fills `%1...%`, `%2...%` and so on in the loc entry | `scarutil.scar:2382-2386` (definition). 108 calls (see §2.2). | High. **Not in the .api doc.** `Loc_FormatTextInternal` is the engine binding. |
| `Loc_FormatInteger` | `(Integer integer)` | LocString | "Returns a localized string containing the integer." [DOC api:1003] | `core_objectives.scar:2734`, `objectives.scar:2427` (as `Loc_FormatText` args), `rogue_objectives.scar:1260` (→ `UI_CreatePositionKickerMessage`) | High |
| `Loc_FormatNumber` | `(Real number, Integer numDecimalPlaces)` | LocString | Number to N decimals [DOC api:1004] | No official usage found | Medium (doc only) |
| `Loc_FormatTime_M_S` | `(Real secs, Boolean leading_zeroes)` | LocString | `M:SS` [DOC api:1006] | `combat_mode.scar:1221,1475` (into data context), `rogue_objectives.scar:950,1473` (as a format arg), `core_objectives.scar:264` | High |
| `Loc_FormatTime_H_M_S` | `(Real secs, Boolean leading_zeroes)` | LocString | `H:MM:SS` [DOC api:1005] | None found | Medium (doc only) |
| `Loc_FormatTime_M_S_MS` | `(Real secs, Boolean leading_zeroes)` | LocString | `M:SS.mmm` [DOC api:1007] | None found | Medium (doc only) |
| `Loc_ToAnsi` | not in the doc | Lua string | LocString to plain Lua string | 22 calls, all for `print`/debug, for example `core_objectives.scar:130,211,265`, `rogue_tech_tree.scar:390` (`Loc_ToAnsi(BP_GetUpgradeUIInfo(upgrade).screenName)`), `cardinal.scar:447` (`"Skip to objective \""..Loc_ToAnsi(objective.Title).."\""`) | High that it exists. It is **undocumented**. |

**Not found anywhere (the doc, official SCAR, or the FTS index):** `Loc_ConvertNumber`, `Loc_FromAnsi`, `Loc_Concat`, `Loc_Append`, `Loc_FormatString`. Do not use them.

### Other functions that produce or carry LocStrings

| Function | Notes | Evidence |
|---|---|---|
| `Player_GetDisplayName(player)` | Returns a LocString. Has a `.LocString` field. Passed straight into `Loc_FormatText` and `Loc_GetString`. | [DOC api:1283] "Returns the players UI name". [USE] `diplomacy.scar:309`, `campaignpanel.scar:505` |
| `Core_GetPlayerName(playerID)` / `PLAYERS[i].playerName` | Wraps `Player_GetDisplayName` | [USE] `core.scar:401,557-562`, `surrender.scar:186` |
| `BP_GetUpgradeUIInfo / BP_GetEntityUIInfo / BP_GetSquadUIInfo` | Return a table. `.screenName`, `.helpText` and `.briefText` are LocStrings. | [DOC api] "table containing the ui_ext info". [USE] `rogue_tech_tree.scar:390`, `current_dynasty_ui.scar:535`, `chart_a_course.scar:443` |
| `Player_GetRaceName(player)` | Plain string, "always in english". **Not** for display. | [DOC] |
| `Setup_SetPlayerName(player, String name)` | Sets the UI name. `Setup_Player` converts a raw string with `LOC()` first. | [DOC], [USE] `scarutil.scar:146-154` |
| `Entity_OverrideScreenName(entity, String overrideName)` | Doc: "Loc_GetString can be used to get the localized string to pass in." Official code passes `"$id"`. | [DOC api:765], [USE] `rogue.scar:482` |
| `Debug_ScartypeToString(v)` | Debugging type names (`missionomatic_leader.scar:21`) | [USE] |

### The LocString value itself

- `scartype(x) == ST_LOCSTRING` identifies a LocString. [DOC] `Essence_Constants.api:562`. [USE] `campaignpanel.scar:1444`, `cardinal.scar:581`, `missionomatic_actionlist.scar:392`
- `loc.LocString` returns a **plain Lua string**. It is used in `string.format("%s")` and in XAML data contexts. [USE] `core.scar:433`, `elimination.scar:61`, `diplomacy.scar:393,672`, `score.scar:494,517`, `combat_mode.scar:1070,1228`. Change detection compares `oldValue.LocString ~= newValue.LocString` (`campaignpanel.scar:1459-1460`).
- `loc[1]` is concatenated as a Lua string: `data.text.."("..(Loc_FormatTime_M_S(currTime, true)[1])..")"` [USE] `core_objectives.scar:2781`, `objectives.scar:2472`. What `[1]` holds is undocumented. [INF] It is probably the same text as `.LocString`.

---

## 2. Displaying raw (non-localized) text

### 2.1 What a "text" parameter accepts

Official code shows that LocString-taking display APIs accept all three of these forms. The `.api` doc types them all as `String`.

| Form | Example | Evidence |
|---|---|---|
| Integer loc ID | `Obj_SetTitle(obj, 11190384)`, `UI_CreateEventCueClickable(-1, 10, 0, 20, 11269722, Loc_Empty(), ...)`, `Obj_Create(player.id, 11159068, Loc_Empty(), ...)` | [USE] `religious.scar:901`, `king_of_the_hill_mode.scar:646`, `wonder.scar:916` |
| `"$id"` Lua string | `UI_CreateEventCue("$11166944", Loc_Empty(), "", "", sfx)`, `Entity_OverrideScreenName(eid, "$11271510")` | [USE] `missionomatic_artofwar.scar:549`, `rogue.scar:482` |
| LocString | any `Loc_*` result | [USE] everywhere |
| Arbitrary Lua string (not `$`) | Official code **wraps it in `LOC()` first**: `elseif scartype(action.message) == ST_STRING then UI_CreateEventCue(LOC(action.message), ...)` | [USE] `missionomatic_actionlist.scar:392-395`, `event_cues.scar:294-301`, `scarutil.scar:146-147` |

The repeated "if ST_STRING and not `$`, then `LOC()` it" pattern strongly suggests that a bare raw Lua string is **not** reliably accepted by those APIs. It would either be treated as a key or rejected. **[INF]**

There is one counter-example. `cardinal.scar:379` passes raw Lua strings to `UI_MessageBoxSetText("ALERT", msg)` and `UI_MessageBoxSetButton(DB_Button1, "CONTINUE", "Continue", ...)`, but that is campaign-debug-only code.

### 2.2 `Loc_FormatText` argument types (official evidence)

| Arg type | Example | Evidence |
|---|---|---|
| ID: integer | `Loc_FormatText(11161270, round)` | `combat_mode.scar:544` |
| ID: `"$id"` string | `Loc_FormatText("$11164967", Player_GetDisplayName(player))` | `campaignpanel.scar:511` |
| Lua number | `Loc_FormatText(11161258, tribute.food, ...)`, `Loc_FormatText(11195756, 3)` | `diplomacy.scar:1290`, `religious.scar:1027` |
| LocString (player name) | `Player_GetDisplayName(id)` / `player.playerName` | `diplomacy.scar:309`, `wonder.scar:269` |
| LocString (from `Loc_Format*`) | `Loc_FormatText(11120883, data.text, Loc_FormatInteger(a), Loc_FormatInteger(b))` | `core_objectives.scar:2734` |
| Nested `Loc_FormatText` result | No direct `Loc_FormatText(id, Loc_FormatText(...))` was found. LocString args do work (row above), so nesting should work. | [INF] |
| `"$id"` string arg, **resolved as a key** | `Loc_FormatText("$11252749", leaderData.stringName)` where `stringName = "$11230140"` ("Saladin"). The output is "Saladin has returned to the battle!" | `missionomatic_leadertent.scar:98,142` |
| Plain Lua string (non-`$`) | **No official example found.** `core_objectives.scar:2779-2784` avoids it: an ST_STRING title gets `..` concatenation, and only a loc title gets `Loc_FormatText`. | [INF] |

The placeholder syntax in loc text is `%1%` or `%1NAME%`. The digit is the argument index and the trailing name is only a label. [USE] locdb: `11189636 "%1% has been injured"`, `11164967 "Food for %1PLAYER_NAME%"`.

### 2.3 Recommended raw-text recipe

```lua
-- Official key 11252841 = "%1TEXT%" in all 26 locales (also 11252842, 11191492 "%1%", 556002 "%1Message%").
-- Prefer a mod-owned key with the same text so you aren't coupled to an engine ID.
local RAW_TEXT_ID = 11252841

function Text_FromLua(s)
    -- s is a plain Lua string (e.g. player-authored build-order text)
    return Loc_FormatText(RAW_TEXT_ID, s)          -- [INF] needs in-game confirmation
end

UI_CreateEventCue(Text_FromLua("Build 2 houses"), Loc_Empty(), "", "", "sfx_ui_event_queue_high_priority_play")
Obj_SetTitle(objId, Text_FromLua(step.title))
```

The fallback is the official pattern, but the doc labels `LOC` DEV ONLY:

```lua
local function ToLoc(v)                       -- mirrors event_cues.scar _ReturnLocVersion / actionlist
    local t = scartype(v)
    if t == ST_LOCSTRING or t == ST_NUMBER then return v end
    if t == ST_STRING then
        if string.sub(v, 1, 1) == "$" then return Loc_GetString(v) end
        return LOC(v)                           -- DEV ONLY per Essence_ScarFunctions.api:1001
    end
    return Loc_Empty()
end
```

This repo already uses the first approach. A mod key `143 = "%1TEXT%"` (`assets/locdb/Macro Trainer_en.csv:31`) is called as `Loc_FormatText(BO_LOC_StringId(143), step.title)` (`assets/scar/build_orders/objectives.scar:124`), and mod keys are built as `"$<modguid>:<id>"` (`localization.scar:11-12`). [INF] Unverified.

---

## 3. Concatenation

### 3.1 Join keys in the official locdb (`official_loc/cardinal.*.ucs`)

All of these are identical in all 26 locales unless noted.

| ID | Text | Use |
|---|---|---|
| `11252841`, `11252842` | `%1TEXT%` | Wrap one value |
| `11191492` | `%1%` | Wrap one value. [USE] XAML `objectivetemplates.xaml:748` `ConverterParameter=$11191492`. The XAML comment shows `' %1%'` (leading space?). |
| `11252837`, `11252838`, `11166338` | `%1TEXT%%2TEXT%` | Join 2 |
| `11252839` | `%1TEXT%%2TEXT%%3TEXT%` | Join 3 |
| `11252840` | `%1TEXT%%2TEXT%%3TEXT%%4TEXT%` | Join 4 |
| `11168874` | `%1%: %2%` | "label: value". Locale-specific punctuation: fr `%1% : %2%`, CJK uses `：`. |
| `11204790` | `%1%. %2%` | Sentence join |
| `11226734` | `%1ITEM%, %2ITEM%` | List join (localized: ja `、`, zh `，`) |
| `999426` | `%1NAME% (%2VALUE%)` | Name (value) |
| `11158557` | `(%1%)` | Parenthesize ([USE] XAML) |
| `11004775`, `11168857` | `%1%/%2%` | Ratio |
| `11161287` | `%1ROUNDS_WON%` | [USE] `combat_mode.scar:1073` `Loc_FormatText(11161287, team.roundsWon)`. This is official precedent for a single-placeholder key used only to turn a value into a LocString. |

None of the `%1TEXT%%2TEXT%` keys are referenced by indexed official SCAR. They are probably UI-side, so engine IDs could in theory change. **Prefer defining the same strings in your own locdb.**

```lua
local JOIN2 = 11252837   -- "%1TEXT%%2TEXT%"
local title = Loc_FormatText(JOIN2, Loc_GetString("$11161290"), Text_FromLua(" (custom)"))
-- or, with raw strings directly as args [INF]:
local line  = Loc_FormatText(JOIN2, BO_LOC_ResourceName(res), " x" .. tostring(n))
```

### 3.2 Idioms and pitfalls

| Idiom | Status |
|---|---|
| `locA .. locB` or `loc .. "text"` | **No official instance.** Every official `..` with loc data goes through `Loc_ToAnsi(...)`, `.LocString` or `[1]`. The one ambiguous case is dev-only `scarutil.scar:3931` `LOC(line1.."\n"..line2)`, where `line1` may be a `LOC()` result. **[INF]** Expect "attempt to concatenate" errors. |
| `Loc_ToAnsi(loc) .. "text"` then `LOC(...)` to rewrap | Works for debug (`cardinal.scar:447` builds a string this way). This **drops localization** because the text is frozen at call time, and it needs DEV-ONLY `LOC`. Officially it is used only for print and cheat UI. |
| `Loc_FormatText(id, locA, locB)` | The official way to combine. It handles word order per locale. [USE] |
| Lua `string.format` / `..` on numbers | Fine for plain Lua strings. To display the result, wrap it (see §2.3). `combat_mode.scar:1074` uses `tostring(n)` directly in a data context. |

---

## 4. Which display APIs take what

The `.api` doc writes LocString params as `String`, so the "accepts" column comes from official usage.

| API | Param doc | LocString | ID int / `"$id"` | Raw Lua string | Evidence |
|---|---|---|---|---|---|
| `Obj_Create(player, title, desc, icon, template, faction, type, parent, telemetryTitle)` | `String title, String desc` | yes | yes (`wonder.scar:916` int; `core_objectives.scar:167` `Description or 0`) | `telemetryTitle` is a plain string (`"wonderObj"`). Title is unknown, so wrap it. | [USE] |
| `Obj_SetTitle / Obj_SetDescription` | "Set title text localization ID" | yes (`combat_mode.scar:544`) | yes (`religious.scar:901,871`) | unknown, so wrap it | [DOC api:1234,1221] + [USE] |
| `UI_CreateEventCue(title, desc, template, icon, sfx, [visibility, lifetime])` | Lua wrapper: `--? @args LocString title, LocString description, String data_template, ...` (`ui.scar:513-517`). Calls `UI_CreateEventCueClickable(-1, ...)`. | yes | `"$id"` yes (`missionomatic_artofwar.scar:549`) | official code wraps it with `LOC()` (`missionomatic_actionlist.scar:395`) | [USE] |
| `UI_CreateEventCueClickable[CanQueue](...)` | `String title, String description` [DOC api:1781,1783] | yes | int yes (`king_of_the_hill_mode.scar:646`) | unknown | [USE] |
| `Game_TextTitleFade(text, in, dur, out)` | `String text` [DOC api:962] | yes (`scarutil.scar:2600` `LOC(...)`, `Util_MissionTitle` `@args LocString title` `scarutil.scar:1627`) | n/a | `scarutil.scar:1442` only calls it when `scartype(v[2]) == 20`, which suggests a raw string is not accepted | [USE] |
| `UI_SystemMessageShow / UI_SystemMessageHide` | `String message` [DOC api:1878,1877] | yes (`scarutil.scar:3931-3933` `LOC(...)`) | ? | ? | [USE] (single site) |
| `UI_MessageBoxSetText / UI_MessageBoxSetButton` | `String` [DOC api:1839,1838] | yes (`gamesetup.scar:317`) | ? | raw strings in debug code (`cardinal.scar:379-380`) | [USE] |
| `UI_CreatePositionKickerMessage` etc. | "localized message to display" [DOC api:1786-1790] | yes (`rogue_objectives.scar:1260` `Loc_FormatInteger`) | ? | ? | [USE] |
| `Subtitle_PlayCharacterSpeech(name, text, icon, sfx)` | `String` [DOC api:1718] | IDs passed through (`speech.scar:31`) | yes | ? | [USE] |
| `UI_SetPropertyValue(element, prop, StackVar)` | StackVar [DOC api:1870] | yes (`combat_mode.scar:1116` sets `"Text"` to `Loc_FormatText`) | ? | likely (StackVar) [INF] | [USE] |
| `UI_SetDataContext(element, StackVarTable)` (also Player/Entity/Squad variants) | StackVarTable [DOC api:1858] | **yes**: `roundsWon = Loc_FormatText(...)`, `roundTime = Loc_FormatTime_M_S(...)`, `help = Loc_FormatText(...)` | n/a | **yes**: `name = player.playerName.LocString`, `roundUnits = tostring(n)`, `roundsWon = "0"`, `color = UI_GetColourAsString(...)` | [USE] `combat_mode.scar:1070-1079,1215-1228`, `diplomacy.scar:672,713`, `score.scar:494` |

XAML side: bindings like `Text="{Binding Counter, Converter={StaticResource LocalizedStringConverter}, ConverterParameter=$11191492}"` (`objectivetemplates.xaml:748`) format a data-context value through a loc key inside XAML. That is an alternative to building composite strings in SCAR. [USE] official_ui

`campaignpanel.scar:1438-1446` (`_CampaignPanel_LocalizeAllStrings`) pre-converts every ST_LOCSTRING or `"$..."` value in a data table with `Loc_GetString` before pushing it. This implies a raw `"$id"` Lua string in a data context would show literally rather than be resolved. [INF]

---

## Gotchas

1. **`Loc_FormatText` and `Loc_ToAnsi` are not in the .api doc.** `Loc_FormatText` is a Lua wrapper in `scarutil.scar`, so it's only available where scarutil is imported. `Loc_ToAnsi` is used only for logging.
2. **`LOC()` is labelled DEV ONLY** [DOC]. It is still used in shipping game-mode code (combat_mode, missionomatic). Treat it as working but unsupported.
3. **A raw string starting with `$` is a loc key.** `Loc_FormatText` args and `Loc_GetString` resolve `"$11230140"` to "Saladin" (`missionomatic_leadertent.scar:98,142`). User-typed text that begins with `$` may be resolved or garbled. Escape it, for example by prefixing a zero-width or other character. [INF]
4. **`..` on a LocString:** no official instance exists. Use a join key, or `Loc_ToAnsi`/`.LocString` if you only need a Lua string (for logging or a data context).
5. **`Loc_ToAnsi`, `.LocString` and `[1]` freeze the text.** The result no longer re-localizes. For a player-name LocString that doesn't matter, but for a loc ID it would if the language changed.
6. **`Player_GetRaceName` is English only**, so don't display it.
7. **Locale punctuation:** join keys like `11168874` (`%1%: %2%`) and `11226734` (list) are translated per locale. Pure `%1TEXT%%2TEXT%` keys aren't, so any separator you put in a raw arg stays English.
8. **Event cue wrapper:** `UI_CreateEventCue` defaults `customEventType` to -1 and has no callback. Use `UI_CreateEventCueClickable` if you need the ID.
9. **Data-context change detection:** official code compares `.LocString` because two LocStrings with the same text are not `==` (`campaignpanel.scar:1459`). [INF] on identity semantics.

## Open questions (need an in-game test)

1. Does `Loc_FormatText(<"%1TEXT%" key>, "plain lua string")` display the literal string? This is the project's core assumption and has **no official precedent**.
2. Does `Obj_SetTitle(id, "plain string")` or `UI_CreateEventCue("plain string", ...)` without wrapping show the text, show blank, show `$0`, or error?
3. What do `locA .. locB` and `loc .. "x"` do: error, `tostring` garbage, or a working `__concat` metamethod?
4. Are `loc.LocString` and `loc[1]` identical? Is it the resolved display text, or the key for ID-based LocStrings?
5. Does `LOC()` behave the same in a non-`-dev` retail build? Is anything stripped?
6. Do the official engine IDs `11252837`–`11252842` stay stable across patches? (This is moot if you mirror them in the mod locdb.)
7. Does nesting `Loc_FormatText(JOIN2, Loc_FormatText(...), Loc_FormatText(...))` work to arbitrary depth?
8. What does `Loc_FormatText` do with a boolean, nil, or table arg? (Probably an error.)
9. In a data context, is a LocString bound to `TextBlock.Text` rendered as text without `LocalizedStringConverter`? (Official code mixes LocStrings and Lua strings in the same tables, so it's probably yes.)
