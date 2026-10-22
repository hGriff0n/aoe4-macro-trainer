# SCAR text formatting research

How to produce displayed text from SCAR in AoE4. Most of the evidence comes from the aoe4-mcp index: the official API doc, official SCAR/XAML snippets, and the official locdb (26 locales).

**Nothing here was tested in-game.** Every report tags each claim with its evidence level. Each report also ends with an "Open questions" section listing the in-game tests still needed.

| Report | Covers |
|---|---|
| [01-loc-api-raw-text-concatenation.md](01-loc-api-raw-text-concatenation.md) | Every `Loc_*` function, LocString vs Lua string, showing raw text, joining strings, which display APIs accept what |
| [02-format-string-syntax.md](02-format-string-syntax.md) | Placeholder grammar inside loc strings, format specs, escapes, markup survey, verified official arg-type ↔ placeholder pairs |
| [03-game-object-names.md](03-game-object-names.md) | Localized names for units, buildings, upgrades, players, civs, ages and resources |
| [04-icons.md](04-icons.md) | Icon arguments on native APIs, blueprint icons, XAML images, inline icons, verified icon paths |
| [05-pluralization-and-numbers.md](05-pluralization-and-numbers.md) | Plural handling (there is none), number, time and percent formatting |

## Quick answers

**Format string grammar.** A placeholder has this shape:

```
%<index 1-9>[NAME][:spec]%
```

- `NAME` is a free-text label for translators and the engine ignores it.
- `spec` is one of `.0`, `.1`, `.2`, `02`, `0`. Every spec seen so far comes from the XAML UI; whether specs work through `Loc_FormatText` is untested.
- `%%` produces a literal `%`.
- The locdb stores `\r\n` and `\n` as literal backslash sequences, and the engine turns them into line breaks.
- There is no `{0}`, colour, bold, BBCode, plural or gender syntax.

See [02](02-format-string-syntax.md).

**Arguments to `Loc_FormatText(key, ...)`.** Official code passes:
- Lua numbers (raw, or wrapped in `Loc_FormatInteger`)
- LocStrings: `Loc_GetString`, `Player_GetDisplayName`, UI-info `screenName`, `Loc_FormatTime_*`, or a nested `Loc_FormatText`
- `"$id"` strings, which the engine resolves as loc keys

Official code never passes a plain Lua string; it wraps text in `LOC()` first. See [01](01-loc-api-raw-text-concatenation.md).

**Raw text (e.g. player typing).** Use one of these:
- a key whose text is `%1%` / `%1TEXT%` (official `11191492` / `11252841`) or the mod's own equivalent, with the text passed via `LOC(str)`
- for XAML data contexts, a plain Lua string, which they accept directly

`LOC` is labelled "DEV ONLY" in the API doc but is used in shipped scripts. Any string that starts with `$` is interpreted as a loc key, so escape or prefix user text before displaying it. See [01](01-loc-api-raw-text-concatenation.md).

**Joining strings.** Use the official placeholder-only keys and nest calls as needed:
- `11252837` = `%1TEXT%%2TEXT%`
- `11252839` = three parts
- `11252840` = four parts

Do not use `..` on LocStrings. `Loc_ToAnsi` and `.LocString` freeze the text in the current language, so official code uses them only for logs and XAML. Copying these join keys into the mod's own locdb is recommended. See [01](01-loc-api-raw-text-concatenation.md).

**Game objects.**
- **Units, buildings, upgrades:** use `BP_GetSquadUIInfo(sbp, race)`, `BP_GetEntityUIInfo(ebp)` or `BP_GetUpgradeUIInfo(ubp)`, then `.screenName`, which is a LocString. Other fields: `helpText`, `extraText`, `briefText`, `iconName`.
- **Players:** `Player_GetDisplayName(p)`.
- **Ages and resources:** no getter exists; official code hard-codes loc ids (e.g. Age I–IV = `11149423`–`11149426`).
- **Civs:** no localized-name getter found. `Player_GetRaceName` returns an internal id.

See [03](03-game-object-names.md).

**Icons.**
- **Native APIs** (objectives, event cues, kickers, hint points, map icons) take an engine icon name with no extension, e.g. `icons/resources/resource_food_icon`.
- **XAML** needs `pack://application:,,,/WPFGUI;component/<path>.png`.
- **Inline icons in loc text** exist only as input-binding glyphs: `##ICON::<binding_group>::<command>##`.
- **Arbitrary inline icons** need custom XAML: a `TextBlock` with `Run` and `InlineUIContainer`.

See [04](04-icons.md).

**Pluralization.** No engine support exists. Official content does one of these:
- uses separate singular and plural keys and picks between them with `if n == 1` in SCAR
- writes one key per value
- avoids plural wording altogether

Slavic translations rewrite strings into plural-free forms ("Label: N", abbreviations). Recommended: wording without plurals, or a one/other helper used only where English quality matters. See [05](05-pluralization-and-numbers.md).

**Numbers and times.** The functions are:
- `Loc_FormatInteger(n)`
- `Loc_FormatNumber(x, decimals)`
- `Loc_FormatTime_M_S`, `Loc_FormatTime_H_M_S`, `Loc_FormatTime_M_S_MS`, each taking `(secs, leading_zeroes)`

`Loc_ConvertNumber` does not exist. See [05](05-pluralization-and-numbers.md).

## Cross-report notes

- **Correction applied to 04.** The icons agent first reported that loc text contains no icon markup. The format-syntax agent found `##ICON::…##` in 384 en rows, and I verified that against the DB. The `group::command` pairs match `UI_AddCommandBinding` names (`gameplay/xbox_diplomacy_menus.scar:267-269`), so these tokens are key/button prompts, not general images. Section 1 of 04 has been rewritten.
- **Disagreement:** 01 and 02 both found that official code wraps raw Lua strings in `LOC()` before passing them as format arguments. Whether a bare Lua string also works is an open in-game question. This repo's `%1TEXT%` + raw-string approach depends on the answer.

## Possible bugs in this repo found during research

None of these were tested; each needs confirmation before fixing.

1. `assets/locdb/Macro Trainer_en.csv`, ids 170–173: every slot uses `%1COUNT%` / `%1RESOURCE%`, so every slot will show argument 1. They should use `%1`…`%8`. Id 172 also has a stray `| %1COUNT% |`. **Verified by reading the file.**
2. `checks/utils/pbg.scar:7` (`local found, pbg = blueprint_getter(id)`), `pbg.scar:46` and `checks/upgrades.scar:32` (`local resolved, uiInfo = ui_accessor(pbg)`) unpack two return values. Every official `BP_Get*Blueprint` / `BP_Get*UIInfo` call returns one value. That makes the second variable always `nil`, so names fall back to the raw id. This looks like code meant for `pcall(getter, id)` that calls the getter directly. **Verified by reading the code**; the single return value is inferred from official usage. See [03](03-game-object-names.md).
3. `built.scar` key `buildMany` = "Build %1COUNT% %2TARGET%" renders "Build 3 House" because the unit name is always singular. See [05](05-pluralization-and-numbers.md).
4. In the worktrees, `gri-51-hints` uses the icon `"Icons_objectives_objective_secondary"`, which does not exist in official content. `gri-109-110-build-order-ui` binds a raw `iconName` to XAML `Image.Source` without converting it to a pack URI. See [04](04-icons.md).

## Tooling note

The aoe4-mcp server could not find its DB. It autodiscovers `data/index.sanitized.sqlite3` relative to its working directory, and that directory is this repo. `.mcp.json` now sets `AOE4_MCP_DB_PATH` to point at it, which takes effect after the MCP server restarts.
