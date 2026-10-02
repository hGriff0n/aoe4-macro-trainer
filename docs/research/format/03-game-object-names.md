# 03 - Localized names for game objects in SCAR

Topic: how SCAR gets *display* (localized) names/descriptions for units, buildings, upgrades,
abilities, ages, civs, players, resources and colours, and how those feed into `Loc_FormatText`.

Sources:
- **Official API doc** = `Essence_ScarFunctions.api` as indexed in `aoe4-mcp` (`api_functions`, line no. given as `api:NNN`). The index has no return types for these functions; return types below are derived from official usage unless stated.
- **Official usage** = official SCAR found on disk at `C:/Users/ghoop/AppData/Local/Temp/codex-crucible-review/cardinal-data/scar/` (paths below are relative to that `scar/` folder) and the `aoe4-mcp` `code_records` table (`official_scar/...`).
- **Inferred/unverified** = my reading; needs an in-game test.

See also `01-loc-api-raw-text-concatenation.md` (LocString vs Lua string) and `02-format-string-syntax.md` (placeholder syntax).

---

## 1. Summary table

| Object kind | API | Input | Returns | Use in `Loc_FormatText` |
|---|---|---|---|---|
| Squad (unit) | `BP_GetSquadUIInfo(sbp, rbp)` | squad PBG + **race PBG** | Lua table: `.screenName`, `.helpText`, `.extraText`, `.iconName` (LocStrings + icon string) | pass `info.screenName` directly as an arg |
| Entity (building, landmark, wonder) | `BP_GetEntityUIInfo(ebp)` | entity PBG | same table shape | pass `info.screenName` |
| Upgrade / technology / age-up upgrade | `BP_GetUpgradeUIInfo(ubp)` | upgrade PBG | same table, plus `.briefText` seen | pass `info.screenName` |
| Ability | **none**. Only `UI_GetAbilityIconName(abilityPBG)` (icon) | ability PBG | icon name string | no name API: use your own loc id |
| Player | `Player_GetDisplayName(player)` | PlayerID | LocString (has `.LocString` field) | pass directly; official ids use `%1PLAYER_NAME%` |
| Civ (race) | `Player_GetRaceName(player)` | PlayerID | **English internal id string**, e.g. `"abbasid"`, `"byzantine_ha_mac"`. Not a display name | do not show; map to your own loc id |
| Civ icon | `World_GetRaceIcon(Player_GetRace(p))` (undocumented, official usage) | race PBG | icon path string | n/a |
| Age | no API. Official code hard-codes loc ids | n/a | n/a | `Loc_GetString(11149423)` .. `11149426` ("Age I".."Age IV") |
| Resource (RT_*) | no API. Official code hard-codes one format id per resource | n/a | n/a | e.g. `11161258` "%1AMOUNT% food received from %2PLAYER_NAME%" |
| Player colour | `Player_GetUIColour(player)` + `UI_GetColourAsString(colour)` | PlayerID | table `.r .g .b .a` (0-255) / `"#AARRGGBB"` string | not via Loc. Goes into XAML data-context colour fields |
| Blueprint internal name | `BP_GetName(pbg)` | any PBG | plain Lua string (short attrib name) | debug or lookup keys only, never player-facing |
| Override entity name | `Entity_OverrideScreenName(eid, "$11271510")` | EntityID + `"$<locid>"` string | n/a | n/a |

None of these APIs return a loc **id** for a blueprint. The UI-info getters return the localized
LocString itself. The only place you handle raw ids is your own/hard-coded loc ids (`11149423`, `"$11271510"`).

---

## 2. Per-API details

### 2.1 `BP_GetSquadUIInfo(ScarSquadPBG sbp, ScarRacePBG rbp)`
- **Official API doc** (api:475): "Returns a table containing the ui_ext info for given squad and race".
- **Official usage**: `gameplay/chi/current_dynasty_ui.scar:514,541`, `gameplay/templar/templar_age_up_ui.scar:120,125,137,148`:
  ```lua
  race = Player_GetRace(Game_GetLocalPlayer())            -- race PBG, NOT Player_GetRaceName
  uiinfo = BP_GetSquadUIInfo(BP_GetSquadBlueprint(_dynasty.squads[i]), race)
  squad = {
      icon  = uiinfo.iconName,
      extra = uiinfo.extraText,
      name  = uiinfo.screenName,
      help  = uiinfo.helpText,
  }
  ```
- Returns a **single** table (assigned to one variable in every official call).
- The race argument exists because a squad's `ui_ext` can differ per race. **Inferred:** this is how one shared sbp can show a civ-specific name.

### 2.2 `BP_GetEntityUIInfo(ScarEntityPBG ebp)`
- **Official API doc** (api:450). **Official usage** `gameplay/chi/current_dynasty_ui.scar:528,558` (buildings and wonders/landmarks). Same fields: `iconName`, `extraText`, `screenName`, `helpText`.

### 2.3 `BP_GetUpgradeUIInfo(ScarUpgradePBG ubp)`
- **Official API doc** (api:479).
- **Official usage**:
  - `gameplay/chi/current_dynasty_ui.scar:517-523` reads `.extraText`, `.screenName`, `.helpText`.
  - `gamemodes/chaotic_climate_mode.scar:609,664` stores it, then `:422-423` passes `.screenName` and `.briefText` straight to `UI_CreateEventCue` as title and description (LocString args).
  - `rogue/rogue_tech_tree.scar:391`: `Loc_ToAnsi(BP_GetUpgradeUIInfo(upgrade).screenName)`. This shows `screenName` is a LocString (needs `Loc_ToAnsi` to become a Lua string).
- Related: `Game_ChartACourseGetPlayerUpgradeUIInfo(player, idx)` (mode-specific, undocumented) returns the same kind of table. It is used with `.briefText` and `.iconName` (`gamemodes/chart_a_course.scar:442-443`).

**Fields seen in official SCAR:** `screenName`, `helpText`, `extraText`, `iconName`, `briefText`. The XAML side has more properties (`UIInfo.Name/Help/Extra/Brief/Icon/NameShort/IconAlternate/IsUniqueToRace...`), but those belong to the C# model and were never seen as Lua fields. **Inferred:** a Lua `nameShort` might exist. Untested.

### 2.4 `BP_GetName(PropertyBagGroup pbg)`
- **Official API doc** (api:455): "Return the short name of the group".
- **Official usage**: debug and lookup only, e.g. `view.scar:302`, `gameplay/score.scar:192` (commented `print`), `rogue/rogue_tech_tree.scar:67` (`race.name = BP_GetName(rbp)` then `"race_"..race.name` as a type key).
- Returns a plain Lua string such as `unit_villager_1_abb`. It is not localized, so never show it to players.

### 2.5 `Player_GetDisplayName(Player& player)`
- **Official API doc** (api:1283): "Returns the players UI name."
- Returns a LocString. Official code uses it three ways:
  1. As a direct `Loc_FormatText` arg: `gameplay/diplomacy.scar:309` `Loc_FormatText(11161246, Player_GetDisplayName(observerPlayer.id))` → "%1PLAYER_NAME% is now neutral".
  2. Wrapped: `campaignpanel.scar:505,1416` `Loc_GetString(Player_GetDisplayName(player))`.
  3. Via `.LocString` member for data contexts: `gameplay/score.scar:494`, `gameplay/diplomacy.scar:394,672`, `gamemodes/combat_mode.scar:1071`.
- `core.scar:401` caches it as `PLAYERS[i].playerName`. That is why `player.playerName` is passed to `Loc_FormatText` in `gameplay/event_cues.scar:194-211` and `gamemodes/combat_mode.scar:1176`.

### 2.6 `Player_GetRaceName(Player& player)` / `Player_GetRace`
- **Official API doc** (api:1297): "Returns the name of the race for a given player **(always in english)**". Official usage compares it to ids like `'byzantine'`, `"abbasid_ha_01"`, `"templar"`, `"mongol_ha_gol"` (`gameplay/chatcheats.scar:169,552`, `gameplay/event_cues.scar:186-192`). It is an internal id, not a display name. `core.scar:403` caches it as `PLAYERS[i].raceName`.
- `Player_GetRace` (api:1296) returns the race PBG. This is what `BP_GetSquadUIInfo` and `World_GetRaceIcon` need.
- **No API returns a localized civ name.** The locdb has civ names (e.g. `11183528` "Abbasid Dynasty"; English has 5 ids: `11119080`, `11180347`, `11199897`, `11200751`, `11202269`), but no official SCAR references them. The only civ-name format strings found are UI ones (`11193311` "Open the codex for the %1civilization_name% civilization."). **Inferred:** to show a civ name, keep your own `raceName -> loc id` map (or your own locdb entries).

### 2.7 `Entity_OverrideScreenName(EntityID, String overrideName)`
- **Official API doc** (api:765) says `Loc_GetString` can produce the 2nd arg. **Official usage** (`rogue/rogue.scar:482,487,492`) passes a `"$<id>"` string instead: `Entity_OverrideScreenName(eid, "$11271510")` ("Invulnerable Stone Wall"). This is the clearest example of the blueprint-style loc id format `"$11xxxxxx"`.

### 2.8 Player colour
- `Player_GetUIColour(player)` (**Official API doc** api:1325): table with `.r .g .b .a` 0-255, "with respect to the local machine".
- `UI_GetColourAsString(colour)` is an official SCAR helper (`ui.scar:812`, code_records). It converts that table to `"#AARRGGBB"`. Used in `campaignpanel.scar:506` and `gameplay/score.scar:495` to set XAML `color_name` fields.
- Colour is not a Loc placeholder. For coloured text you bind the colour in XAML. Whether inline colour markup works inside LocStrings is out of scope here (see 02).

### 2.9 Abilities
- No `BP_GetAbilityUIInfo` in the API index. The only ability UI getter is `UI_GetAbilityIconName(ScarAbilityPBG)` (**Official API doc**). Use your own loc ids for ability names.

### 2.10 Ages
- No API. Official hard-coded ids:
  - `gameplay/score.scar:38-43`: `Loc_GetString(11149423..11149426)` → "Age I" .. "Age IV" (table indexed by age).
  - `gameplay/event_cues.scar:36-39`: `11161396/7/8` = "%1PLAYER_NAME% reached the Feudal/Castle/Imperial Age".
- The locdb also has `11181806..11181809` = "Dark Age", "Feudal Age", "Castle Age", "Imperial Age", but no official SCAR uses them (**Inferred** usable, untested).
- An age-up **landmark's** name comes from `BP_GetEntityUIInfo(landmarkEbp).screenName`. An age-up **upgrade's** name comes from `BP_GetUpgradeUIInfo(ubp).screenName`. This repo's `age_up.scar` already uses both.

### 2.11 Resources
- No `RT_* -> name` API. Official code bakes the resource word into a separate format id per resource:
  - `gameplay/diplomacy.scar:85-88`: `{ resource_type = RT_Food, ..., help = 11164967 }` ("Food for %1PLAYER_NAME%"), then `:713` calls `Loc_FormatText(resource.help, Player_GetDisplayName(player.id))`.
  - `gameplay/diplomacy.scar:1290-1302` / `campaignpanel.scar:769-778`: `11161258` food, `11161259` wood, `11161260` stone, `11161261` gold = "%1AMOUNT% <res> received from %2PLAYER_NAME%".
- Standalone words exist in the locdb with many duplicate ids, and none are referenced by official SCAR. Examples: Food `11085951`, `11204463`, `62`; Wood `11085952`, `11204466`, `63`; Gold `11105784`, `11204464`, `64`; Stone `11144802`, `11204465`, `65`; Olive Oil `11244678`, `11251699`, `11256513`, `11256689`. The `11204463-66` run is one consecutive Food/Gold/Stone/Wood block (**Inferred** to come from one UI set).
- Engine format strings that take a resource arg also exist (`11121049` "Insufficient %1RESOURCE%", `11164354` "Sell %1AMOUNT:.0% %2RESOURCE_TYPE% to get ..."). This suggests the engine can substitute a resource name, but no SCAR path to do it was found.
- Recommendation: either (a) one format string per resource, like official code, which also handles grammar per language, or (b) your own `RT_* -> loc id` table passed as a LocString arg. (b) is fine for English. Some languages need different case/gender forms, which is a reason to prefer (a) in sentences.

---

## 3. Base data (`base_data_entries`) and blueprint loc ids

- Categories: `units`, `buildings`, `technologies`, `upgrades`, `abilities` (source `official_base_data/<cat>/all.json`, aoe4world-style data).
- JSON keys (units): `id, baseId, name, cnName, description, cnDescription, attribName, pbgid, civs, age, costs, classes, displayClasses, producedBy, ...`.
- **There are no loc ids in base data.** I searched `details_json` for `$11`: 0 rows. `name` is plain English. Use it only for author tooling.
- What it does give you is `attribName` (e.g. `unit_villager_1_abb`), which is the short name for `BP_GetSquadBlueprint` / `BP_GetEntityBlueprint` / `BP_GetUpgradeBlueprint`. It also gives `baseId` (e.g. `villager`), which groups the civ variants.
- Generic vs civ names: every civ has its own villager blueprint (`unit_villager_1_abb`, `unit_villager_1_abb_ha_01`, `unit_villager_1_byz`, ...), all with `name` "Villager" and `baseId` "villager". The way to get the name the *player* sees is to resolve the civ's blueprint and read `screenName`. **Inferred:** unique units and renamed variants then show correctly.
- Blueprint `ui_ext.screen_name` ids follow the `"$11xxxxxx"` form (as in `Entity_OverrideScreenName`). The attrib files are not on disk here, so I could not read a blueprint's actual screen_name id. **Inferred:** `11119068` "Villager" and `11119069` "Town Center" are the shipped ids for those, but this is unconfirmed. Do not hard-code them. Use `screenName` from UI info.
- So "find a blueprint's loc id and call `Loc_GetString`" is **not** the supported path: no API returns the id. Use the UI-info table instead.

---

## 4. Feeding names into `Loc_FormatText`

`Loc_FormatText` is an official SCAR helper (`scarutil.scar:2382`, `--? @args Integer FormatID[, argc parameters]`, `@result LocString`). Officially used argument kinds:
- **LocString**: `Player_GetDisplayName(...)` (diplomacy.scar:309), `player.playerName` (event_cues.scar:194), `Loc_FormatInteger(...)` / `Loc_FormatTime_M_S(...)` (objectives.scar:2427, rogue/rogue_objectives.scar:950).
- **Raw Lua number**: `tribute.food` (diplomacy.scar:1290), `_combat_mode.victoryThreshold` (gamemodes/combat_mode.scar:797).
- Format id given as an integer (`11161246`) or a `"$11161246"` string (campaignpanel.scar:511). Both are used.
- Placeholders are `%N%` or `%NNAME%` (e.g. `%1PLAYER_NAME%`, `%2UNIT NAME%`). The name part is a label for translators. Details are in 02.

**Count + name.** No official SCAR call was found that combines a count with a blueprint `screenName`. The closest official patterns are count + player name (`11161258` "%1AMOUNT% food received from %2PLAYER_NAME%") and an engine string `11046953` "%1UPGRADE% - %2UNIT NAME%". Passing `screenName` as a `Loc_FormatText` arg is **Inferred**: it is a LocString like `Player_GetDisplayName`, which is officially passed this way. `UI_CreateEventCue(info.screenName, info.briefText, ...)` (chaotic_climate_mode.scar:422) shows `screenName` is accepted wherever a LocString is.

---

## 5. Copy-paste examples

```lua
-- Unit name (civ-aware), e.g. own loc "$<mod>:Train %1COUNT% %2UNIT%"
local function UnitName(player, sbpName)          -- sbpName = base_data attribName
    local sbp  = BP_GetSquadBlueprint(sbpName)
    local info = BP_GetSquadUIInfo(sbp, Player_GetRace(player))   -- race PBG
    return info.screenName                         -- LocString
end
local text = Loc_FormatText(TRAIN_FMT_ID, 3, UnitName(player, "unit_villager_1_eng"))

-- Building / landmark
local info = BP_GetEntityUIInfo(BP_GetEntityBlueprint("building_house_eng"))  -- name illustrative
local text = Loc_FormatText(BUILD_FMT_ID, 2, info.screenName)

-- Upgrade / technology
local info = BP_GetUpgradeUIInfo(BP_GetUpgradeBlueprint(ubpName))
local text = Loc_FormatText(RESEARCH_FMT_ID, info.screenName)
UI_CreateEventCue(info.screenName, info.briefText, template, info.iconName, sfx, vis, lifetime) -- official pattern

-- Player
local text = Loc_FormatText(11161246, Player_GetDisplayName(p))   -- "%1PLAYER_NAME% is now neutral"
local plain = Player_GetDisplayName(p).LocString                    -- for XAML data context

-- Age (official table)
local AGE = { 11149423, 11149424, 11149425, 11149426 }              -- "Age I".."Age IV"
local text = Loc_GetString(AGE[age])

-- Resource (official per-resource format ids)
local FOOD_RECEIVED = 11161258   -- "%1AMOUNT% food received from %2PLAYER_NAME%"
local text = Loc_FormatText(FOOD_RECEIVED, 200, Player_GetDisplayName(sender))

-- Player colour for XAML
local colour = UI_GetColourAsString(Player_GetUIColour(p))          -- "#AARRGGBB"

-- Debug only
print(BP_GetName(sbp) .. " = " .. Loc_ToAnsi(info.screenName))
```

---

## 6. Gotchas

1. **UI-info getters return ONE value.** Every official call does `uiinfo = BP_Get*UIInfo(...)`. This repo's `assets/scar/build_orders/checks/utils/pbg.scar` `Mod_Pbg_ScreenName` does `local resolved, uiInfo = ui_accessor(pbg)`, and `checks/upgrades.scar:32` does the same. If the getter returns one table, `uiInfo` is always `nil` and the code always falls back to raw-id text. Fix: `local uiInfo = ui_accessor(pbg)`. (**Inferred** from official usage; confirm in-game.)
2. **Same issue for blueprint lookups.** `Mod_Pbg_Resolve` does `local found, pbg = blueprint_getter(id)` with `BP_GetEntityBlueprint` / `BP_GetSquadBlueprint`. Official code always takes one return (`sbp = BP_GetSquadBlueprint("...")`, `rogue/rogue_poi.scar:83`), so the first return is the PBG. With two-value assignment, `found` gets the PBG and `pbg` is `nil`, so nothing is cached. (**Inferred**; it would also mean every name falls back.) Separately, official code never tests an invalid name, so whether it errors or returns nil is unknown. `pcall` it if names come from data.
3. `BP_GetSquadUIInfo` takes the race **PBG** (`Player_GetRace`), not the string from `Player_GetRaceName`. `checks/produce.scar` does this correctly. Note that `produce.scar` `BuildOrder_Check_Produce_GetText` references `unit` and `id` before defining them (a bug in that function, unrelated to the API).
4. `screenName`, `helpText` and `Player_GetDisplayName()` are LocStrings. Don't `..`-concatenate them. Use `Loc_FormatText`, or `Loc_ToAnsi` for debug prints only.
5. `Player_GetRaceName` is always an English internal id (`"abbasid_ha_01"`). It is never a display name. Variant civs (`_ha_01`, `_ha_mac`, ...) have their own ids.
6. `BP_GetName` returns the internal short name, never the player-facing name.
7. No API exists for ability, civ, age or resource names. Use hard-coded official loc ids (ages, resource format strings) or your own locdb entries.
8. Duplicate loc ids: "Food", "English", "Villager" etc. each have several ids. Only reuse ids that official SCAR references (listed above), or ship your own.
9. `Entity_OverrideScreenName` is officially called with a `"$id"` string, despite the doc mentioning `Loc_GetString`.
10. `Player_GetUIColour` is relative to the local machine (doc), so colours differ per viewer. Never use it in synced logic.

## 7. Open questions (need in-game test)

- Do `BP_Get*UIInfo` and `BP_Get*Blueprint` return exactly one value? (Gotchas 1-2.) Test: `print(select('#', BP_GetSquadUIInfo(sbp, race)))`.
- Full field list of the UI-info table: iterate it with `pairs` and print keys. Does `nameShort` or `briefText` exist on squad/entity tables?
- Is `screenName` an empty LocString or `nil` for blueprints without `ui_ext`?
- Does `BP_GetSquadUIInfo(sbp, otherRace)` give a different name than the owning race for shared blueprints?
- Do `Loc_FormatText` args accept a raw integer **loc id** as a nested string? (`objectives.scar:2427` comments "name is (likely) a locID".) Or is it always formatted as a number?
- What does `BP_GetEntityBlueprint("bad_name")` do: error, nil, or an invalid PBG?
- Do `11181806..09` (Dark/Feudal/Castle/Imperial Age) and `11204463..66` (resource words) render in every locale? Are they the in-HUD strings?
- Is there an undocumented civ display-name getter (like the undocumented `World_GetRaceIcon`)? Try `World_GetRaceName`, `BP_GetRaceUIInfo`, etc. under `pcall` and log the results.
