# 05 — Pluralization, Numbers, Times, Percentages

Scope: how official AoE4 SCAR/loc content handles singular vs plural, and how numbers, times and percentages get formatted into `LocString`s.

Evidence tags:
- **Official API doc**: `official_api/Essence_ScarFunctions.api`, the `api_functions` table.
- **Official usage**: official SCAR (`official_scar/...:line`). Line numbers come from the MCP index and can be off by ±1.
- **Observed in locdb**: official `.ucs` loc entries (`loc_entries`). There are 26 locales: `en`, `zh-hans`, `zh-hant`, and `cardinal.{cs,da,de,el,es,es-419,fi,fr,hi,hu,it,ja,ko,ms,nl,no,pl,pt,pt-br,ru,sv,tr,vi}`.
- **Inferred/unverified**: my reasoning, or outside knowledge such as CLDR. Not tested in game.

---

## TL;DR

1. **There is no plural support in the engine or in loc strings.** No ICU `{n, plural, …}`, no `%1:plural%`, no pipe forms, and no `Loc_*Plural*` API. **Official API doc + Observed in locdb**: I scanned all 31,088 `en` entries and every `api_functions` name and description for plural syntax and found none.
2. Official content uses three workarounds:
   - **(a)** A separate hard-coded "1 …" string, picked in SCAR.
   - **(b)** One string per value, for small fixed sets.
   - **(c)** Only calling the plural string with values where it reads correctly.

   In `ru`/`pl`/`cs` the translators neutralize the plural with a label form ("Секунд осталось: %1%") or an abbreviation ("%1% мин.", "%1% s").
3. **SCAR has no API that tells you the current language** (no `*Lang*`/`*Locale*` functions). SCAR can only branch on English-style "count == 1". Languages with 3+ forms (ru, pl, cs) must be handled in the wording of the translation itself.
4. Number APIs: `Loc_FormatInteger(int)`, `Loc_FormatNumber(real, decimals)`, `Loc_FormatTime_M_S(secs, leading_zeroes)`, `Loc_FormatTime_H_M_S(...)`, `Loc_FormatTime_M_S_MS(...)`. **`Loc_ConvertNumber` does not exist.**
5. Raw Lua integers passed straight into `Loc_FormatText` are common in official code. Placeholders accept format specs `:.0`, `:.1`, `:.2`, `:02`, `:0`, and `%%` is a literal percent sign.

---

## 1. Pluralization

### 1.1 No plural syntax or API exists

| Searched for | Result |
|---|---|
| `api_functions` names/descriptions matching `plural`, `FormatText`, `Loc_Convert` | Nothing. The full `Loc*` set is `LOC`, `Loc_Empty`, `Loc_FormatInteger`, `Loc_FormatNumber`, `Loc_FormatTime_H_M_S`, `Loc_FormatTime_M_S`, `Loc_FormatTime_M_S_MS`, `Loc_GetString` (**Official API doc**) |
| `Loc_FormatText` | Not in the API doc. It is a Lua wrapper in `official_scar/scarutil.scar:2382` that calls `Loc_FormatTextInternal(LocID, {...})` (**Official usage**) |
| `Loc_ToAnsi`, `Loc_FormatTextInternal` | Used in official SCAR but undocumented. `Loc_ToAnsi` appears only in `print`/debug paths, e.g. `core_objectives.scar:211`, `rogue_tech_tree.scar:390` |
| en loc: `\{…plural`, `{0}`, `%1:plural%`, `%n%…\|` | 0 plural hits. The 5 pipe hits are literal separators such as `'%1DATE% \| %2TIME%'` (**Observed in locdb**) |
| en loc: `(s)` | 39 hits, all static UI text such as "Focus on Selected Unit(s)" (11144991) with no number placeholder. This is the official "plural-agnostic" style |
| `official_ui` XAML: plural converters | None. Only a `TimeFormatConverter` and `NumberToVisibilityConverter` exist (`official_ui/resources/layoutresources.xaml:92-99`) |
| Unit blueprints: plural name fields | None. Official SCAR reads only `screenName`, `helpText`, `briefText`, `iconName` from `BP_Get*UIInfo` (e.g. `rogue_tech_tree.scar:390`, `current_dynasty_ui.scar:535`). `base_data_entries` has no field matching `plural` |

### 1.2 Pattern A: separate singular entry, chosen in SCAR (**Observed in locdb + Official usage**)

| ID | en | ru | pl |
|---|---|---|---|
| 11197864 | `%1MINUTES_REMAINING% minutes until Wonder Victory` | `До победы с чудом света осталось %1MINUTES_REMAINING% мин.` | `%1MINUTES_REMAINING% min do zwycięstwa dzięki cudowi` |
| 11197866 | `1 minute until Wonder Victory` | `До победы с чудом света осталась 1 минута` | `1 min do zwycięstwa dzięki cudowi` |
| 11195756 / 11195758 | `%1…% minutes until Sacred Victory` / `1 minute until Sacred Victory` | same pattern | same pattern |

SCAR picks the entry, and the numbers are hard-coded at each call site:
- `winconditions/wonder.scar:683` → `Loc_FormatText(11197864, 12)`, then 9, 6, 3, 2 at :709/:735/:764/:793
- `winconditions/wonder.scar:825` → `Loc_FormatText(11197866, 2)` ("1 minute …"). The extra arg `2` has no placeholder and is silently ignored.
- `winconditions/religious.scar:1027/1050` → `Loc_FormatText(11195756, 3)` / `(…, 2)`; `religious.scar:1073` → raw ID `11195758` passed to `UI_CreateEventCueClickable`

In practice no code computes "if n == 1". Each step of the countdown is hard-coded. I found no official `if count == 1 then Loc_FormatText(...)` pattern. The only `count == 1` text branch is a debug pretty-printer (`view.scar:480`, `"Array (1 item)"`).

### 1.3 Pattern B: one string per value (**Observed in locdb**)

- 11183018…11183022: `1 Minute`, `2 Minutes`, … `5 Minutes`. ru: `1 минута` / `2 минуты` / `5 минут`. pl: `1 minuta` / `2 minuty` / `5 minut`. All three Russian/Polish forms appear because each value has its own string.
- 42800/42801/42805: `1 minute remaining` / `2 minutes remaining` / `15 minutes remaining`. ru: `Осталась 1 минута` / `Осталось 2 минуты` / `Осталось 15 минут`. Here the verb agrees with the number too.

### 1.4 Pattern C: only call the string with values where the plural reads correctly (**Official usage**)

- `gamemodes/combat_mode.scar:816-820`: `"%1REMAINING_TIME% seconds remaining"` (11161279) is only shown when `timeToWinRound == 20 or == 10`.
- 11161281 `%1PLAYER_NAME% Needs 1 more win` hard-codes the 1 (`combat_mode.scar:905`, commented out).

### 1.5 How translators neutralize plurals (**Observed in locdb**)

282 `en` strings have the form `%N…% <plural noun>` ("seconds", "units", "rounds", …). In ru/pl/cs they are rewritten so the noun does not have to agree with the number:

| ID | en | ru | pl / cs |
|---|---|---|---|
| 11161279 | `%1REMAINING_TIME% seconds remaining` | `Секунд осталось: %1REMAINING_TIME%` (label form) | pl `Pozostało %1REMAINING_TIME% s`, cs `Zbývá %1REMAINING_TIME% s` (abbreviation) |
| 11161274 | `Win %1ROUND_NUMBER% rounds` | `Выиграть раундов: %1ROUND_NUMBER%` | pl `Wygraj następującą liczbę rund: %1ROUND_NUMBER%` ("win the following number of rounds: N") |
| 11155329 | `%1NUM_KILLED% Units Killed` | `Юнитов убито: %1NUM_KILLED%` | pl `Zabite jednostki: %1NUM_KILLED%` |
| 11161258 | `%1AMOUNT% food received from %2PLAYER_NAME%` | `…получено %1AMOUNT% ед. пищи` ("units of", invariant) | pl `Otrzymano żywność (%1AMOUNT%) od: …` |
| 11144187 | `… by %1% seconds.` | `… на %1% сек.` | pl `… o %1% s.` |

Japanese/Chinese/Korean have no plural, e.g. `残り %1REMAINING_TIME% 秒`. de/fr just use the plural, because the values are almost never 1.

Translations are not always correct. 11159029 ru `на %1% секунд быстрее` uses the genitive plural, which is only right for 5+. Expect the same kind of slip in a mod.

### 1.6 Locales with more than two plural forms (**Inferred/unverified**, CLDR knowledge, not from the DB)

| CLDR categories for integers | Shipped locales |
|---|---|
| one / other | en, de, nl, sv, da, no, fi, it, es, es-419, pt, el, hu, tr*, hi** |
| one (0 and 1) / other | fr, pt-br |
| one / few / many | **ru, pl, cs** (cs: one/few/other) |
| other only | ja, ko, zh-hans, zh-hant, vi, ms |

\* Turkish usually uses the singular noun after a number. \*\* Hindi treats 0 and 1 as "one".

A SCAR-side "1 vs other" branch is correct for about 15 of the 26 locales. It is never correct in every case for ru/pl/cs, and it is pointless for CJK, vi and ms.

### 1.7 Current repo state (**Inferred/unverified**)

- `.worktrees/runtime-build-order-localization/assets/scar/build_orders/checks/built.scar:4-14` follows Pattern A: `count == 1` → `buildOne` ("Build %1TARGET%"), otherwise `buildMany` ("Build %1COUNT% %2TARGET%") with `Loc_FormatInteger(count)`.
- **Problem:** `%2TARGET%` is a blueprint `screenName`, which is always singular ("House"). In English the output is "Build 3 House". There is no plural blueprint name to swap in, as §1.1 shows. The same applies to `produce` (164 "Produce %1COUNT% %2UNIT%"), `queueProduce` (165), `activeUnits` (167), `collect` (155) and `allocation` (152).
- Main-branch `assets/scar/build_orders/checks/built.scar:112` passes `building` where `building_name` looks intended: `Loc_FormatText(..., payload.count, building)`. `building_name` is computed and never used. Possibly a bug; worth checking.

### 1.8 Recommended strategy

1. **Default to plural-free wording.** The noun should never need to agree with the number. This is what the official translators did:
   - en: `Build %2TARGET% ×%1COUNT%` or `%2TARGET%: %1COUNT%`
   - en: `Villagers on food: %1COUNT%`, not `%1COUNT% villagers on food`
   - Units: `%1COUNT% s` / `%1COUNT% min` abbreviations, or `Loc_FormatTime_M_S`.

   Translators can then copy the shape directly (ru `Дома: %1COUNT%`).
2. **If natural English matters, keep the one/other split in SCAR** (helper below). Write the "other" string so translators can neutralize it: the noun comes from a label slot or the string uses a label form. Add a translator note in your term sheet: "ru/pl/cs: use label form `Noun: N`; do not inflect by number".
3. For **small fixed values** (countdowns, 1–5 option lists), use Pattern B: one loc entry per value. This is the only way to get correct ru/pl/cs grammar.
4. Never derive simulation state from localized text. Display only.
5. Optional experiment, **Inferred/unverified**: ship a loc entry such as `PLURAL_RULE` whose translation is `one_other` / `slavic` / `none`, read it with `Loc_ToAnsi(Loc_GetString(key))`, and choose few/many keys in Lua. This depends on `Loc_ToAnsi` returning the *translated* text in release builds, which is unverified (official code only uses it for `print`). Any difference between players would only affect local UI. I would not build on this without an in-game test.

### 1.9 Plural helper (copy-paste)

```lua
-- Pick a loc key by count (English-style one/other) and format it.
-- keys = { one = "$<locdb-guid>:159", other = "$<locdb-guid>:160" }
-- The "one" string may omit %1COUNT% (official 11197866 does the same; extra args are ignored).
-- The count is always passed as %1COUNT%; extra args follow as %2..%N.
function Mod_FormatCount(keys, count, ...)
    local n = math.floor(count or 0)
    local key = (n == 1 and keys.one ~= nil) and keys.one or keys.other
    return Loc_FormatText(key, Loc_FormatInteger(n), ...)
end

-- Usage (built check):
-- en 159: "Build %2TARGET%"        en 160: "Build %2TARGET% ×%1COUNT%"
-- ru 160 (translator):            "Построить: %2TARGET% ×%1COUNT%"
local BUILD_KEYS = { one = BUILD_ORDER_LOC_KEYS.buildOne, other = BUILD_ORDER_LOC_KEYS.buildMany }
return Mod_FormatCount(BUILD_KEYS, check.payload.count, names)
```

Note the argument order. `count` is always `%1`, so both strings share one placeholder layout. This differs from the worktree's current `buildOne` (where `%1TARGET%` is the name), so renumber the `buildOne` placeholder to `%2TARGET%` if you adopt the helper.

---

## 2. Numbers, times, percentages

### 2.1 API signatures (**Official API doc**, `Essence_ScarFunctions.api`)

| Function | Params | Doc |
|---|---|---|
| `Loc_FormatInteger` | `Integer integer` | "Returns a localized string containing the integer." |
| `Loc_FormatNumber` | `Real number, Integer numDecimalPlaces` | "…containing the number to the specified number of decimal places." |
| `Loc_FormatTime_M_S` | `Real secs, Boolean leading_zeroes` | "…time string in minutes and seconds. can omit leading zeroes." |
| `Loc_FormatTime_H_M_S` | `Real secs, Boolean leading_zeroes` | hours, minutes, seconds |
| `Loc_FormatTime_M_S_MS` | `Real secs, Boolean leading_zeroes` | minutes, seconds, milliseconds |
| `Loc_FormatText` (scarutil.scar:2382) | `LocID, ...` | `--? @args Integer FormatID[, argc parameters]` / `@result LocString` |

**`Loc_ConvertNumber`, `Loc_FormatPercent` and `Loc_GetPluralString` do not exist.** None of them is in the API doc or in official code.

### 2.2 Official usage

- `Loc_FormatInteger`:
  - `objectives.scar:2427` / `core_objectives.scar:2733`: `Loc_FormatText(11120883, data._name, Loc_FormatInteger(currHealth), Loc_FormatInteger(data._storedTotal))`
  - `rogue/rogue_objectives.scar:1260`: `UI_CreatePositionKickerMessage(position, Loc_FormatInteger(thisRaidReward), …)` (standalone LocString)
- `Loc_FormatTime_M_S`:
  - `objectives.scar:2475` / `core_objectives.scar:2784`: `Loc_FormatText(11129961, data._text, Loc_FormatTime_M_S(currTime, true))`
  - `rogue/rogue_objectives.scar:950` and `:1473`: `Loc_FormatText("$11268922", Loc_FormatTime_M_S(math.ceil(remaining_time), true))` (en `Waves Starting in %1%`). Note the `math.ceil` before formatting.
  - `gamemodes/combat_mode.scar:1221/1255/1475`: `roundTime = Loc_FormatTime_M_S(team.timeToWinRound, true)` (assigned into a UI data context)
  - `core_objectives.scar:263`: `Loc_ToAnsi(Loc_FormatTime_M_S(World_GetGameTime(), true))` for a debug print
- Every official call passes `leading_zeroes = true`.
- `Loc_FormatNumber`, `Loc_FormatTime_H_M_S` and `Loc_FormatTime_M_S_MS` have **no official SCAR usage**.

### 2.3 Raw Lua numbers in `Loc_FormatText` work (**Official usage**)

Official code passes plain Lua numbers as arguments:
- `wonder.scar:683` `Loc_FormatText(11197864, 12)`; `religious.scar:1027` `Loc_FormatText(11195756, 3)`
- `combat_mode.scar:544` `Loc_FormatText(11161270, _combat_mode.round)`; `:820` `Loc_FormatText(11161279, timeToWinRound)`; `:1116` `Loc_FormatText(11161288, data.endTime - math.floor(World_GetGameTime()))`
- `gameplay/diplomacy.scar:1290` `Loc_FormatText(11161258, tribute.food, …)`
- `religious.scar:862` `Loc_FormatText(11184017, i)` ("Site %1NUMBER%")
- `missionomatic_artofwar.scar:144` `Loc_FormatText("$11202194", maxUnitsDied+1)`

The same code base also wraps values in `Loc_FormatInteger` (objectives.scar:2427), so both work. Recommendation:
- Use `Loc_FormatInteger(math.floor(x))` when `x` might be a float.
- Use `Loc_FormatNumber(x, d)` for an explicit number of decimals.
- **Unverified:** how a raw non-integer float renders, e.g. whether it shows "12.5" or "12.500000".

### 2.4 Format specs inside placeholders (**Observed in locdb**, identical in en/ru/de)

| Spec | Count (en) | Example |
|---|---|---|
| `:.0` | 108 | 1000665 `%1AMOUNT:.0% Bounty`; 11164353 `Spend %1AMOUNT:.0% Gold …` |
| `:.1` | 7 | 1000683 `%1AMOUNT:.1%`; 11145968 `+%1AMOUNT:.1%s` |
| `:.2` | 6 | 11114106 `%1Seconds:.2%s` (ru `%1Seconds:.2% с`) |
| `:02` (zero-pad to width 2) | 5 | 1254 `%1HOURS:02%:%2MINUTES:02%:%3SECONDS:02%`; 1272 `%1MINUTES:02%:%2SECONDS:02%` |
| `:0` | 3 | 11164353 `%2AMOUNT:0%` |

- `%%` is a literal `%`: 11145963 `%1AMOUNT:.0%%%` → "25%". There are 901 en entries with `%%`, e.g. 11143021 `… Food by %1%%%.`. fr inserts a no-break space: `%1AMOUNT:.0% %%`.
- Ten entries use `%2.1%` with no colon, e.g. 11161557 `every %2.1% seconds`. **Unverified** whether this is a format spec or a typo for `%2:.1%`. Do not copy it.
- **Unverified:** whether these specs apply to args passed through SCAR `Loc_FormatText` (most of these entries are probably filled by attrib/UI data bindings). For mod strings, prefer pre-formatting in SCAR with `Loc_FormatNumber(x, 1)` and a plain `%1%`.
- Percent string example for a mod: `"%1PERCENT%%%"` with `Loc_FormatInteger(math.floor(pct * 100 + 0.5))`.

### 2.5 Time strings

- The probable engine formats are entries 1272 (`%1MINUTES:02%:%2SECONDS:02%`) and 1254 (`%1HOURS:02%:…`). These are identical in every locale checked. **Inferred/unverified:** that `Loc_FormatTime_*` uses them, and what `leading_zeroes=false` changes (probably the first field is not padded: "5:07" vs "05:07").
- For "Xm Ys" text, official loc uses 11153690 `%2MINUTES%m %1SECONDS%s`, localized as ru `%2MINUTES%м %1SECONDS%с` and fr `… min … s`. Note the args are reversed (seconds = `%1`). Abbreviated units avoid plural agreement.
- Odd official idiom: `core_objectives.scar:2781` / `objectives.scar:2472` concatenate `data.text.."("..(Loc_FormatTime_M_S(currTime, true)[1])..")"` when `data.text` is a plain Lua string. This suggests a LocString is indexable and `[1]` yields something concatenable. **Unverified**; do not rely on it.

### 2.6 Thousands separators and locale behaviour

Nothing in the API doc, loc data or official code says whether `Loc_FormatInteger`/`Loc_FormatNumber` insert grouping separators or use a locale decimal comma. **Open question.** If you need a guaranteed format, build the digits yourself with `string.format` and wrap them with a raw-text loc key (`%1TEXT%`). That gives up locale-correct formatting.

---

## 3. Copy-paste examples

```lua
-- Integer count
Loc_FormatText(KEY_COLLECT, Loc_FormatInteger(200), resourceName)    -- "Collect at least 200 food"

-- One decimal place
Loc_FormatText(KEY_RATE, Loc_FormatNumber(gatherRate, 1))            -- "%1RATE%/s"

-- Percent: loc string "%1PERCENT%%%"
Loc_FormatText(KEY_PERCENT, Loc_FormatInteger(math.floor(frac * 100 + 0.5)))

-- Countdown, same idiom as rogue_objectives.scar:950
Loc_FormatText(KEY_STARTS_IN, Loc_FormatTime_M_S(math.ceil(remaining), true))   -- "Starts in %1TIME%"

-- Plural-free count (preferred)
Loc_FormatText(KEY_UNIT_COUNT, unitName, Loc_FormatInteger(n))       -- en "%1UNIT% ×%2COUNT%", ru "%1UNIT%: %2COUNT%"

-- English one/other split (see Mod_FormatCount above)
Mod_FormatCount({ one = KEY_VIL_ONE, other = KEY_VIL_MANY }, n, resourceName)
```

---

## 4. Gotchas

- **Blueprint names are singular.** Putting `screenName` after a count gives "3 House", and there is no plural name to use instead.
- **SCAR cannot detect the locale**, so a Lua-side `n == 1` branch is English logic. ru/pl/cs translators must use label or abbreviation forms. Brief them.
- **Extra args are ignored** (wonder.scar:825 passes `2` to a string without `%1`). This makes one/other pairs safe even when the "one" string omits the count. It also means a misnumbered placeholder fails silently and shows the raw `%2X%` or nothing.
- `Loc_FormatText` is a Lua wrapper (scarutil.scar:2382), not a documented engine function. The engine call is `Loc_FormatTextInternal(LocID, argTable)`.
- Placeholder numbers bind by position: 11153690 puts seconds in `%1` and minutes in `%2`.
- `%2.1%` (no colon) appears in official text but is probably not a valid spec.
- Do not use `Loc_ToAnsi` output for logic. It is debug-only in official code, and its behaviour for translated text is unverified.
- Official code rounds times before formatting (`math.ceil(remaining_time)`). Unrounded reals may show a seconds value that ticks inconsistently.
- Translators make mistakes too (ru 11159029 `%1% секунд` is wrong for 1–4). Plural-free source strings reduce the risk.

## 5. Open questions (need in-game test)

1. Does `Loc_FormatInteger(1234567)` add grouping ("1,234,567" / "1 234 567")? Does `Loc_FormatNumber(1.5, 1)` give "1,5" under de/fr/ru?
2. Exact output of `Loc_FormatTime_M_S(65, true)` vs `(65, false)`, and of `Loc_FormatTime_H_M_S` / `_M_S_MS`.
3. How a raw Lua float renders through `Loc_FormatText` (e.g. `Loc_FormatText(KEY, 12.5)`).
4. Do `:.1` / `:02` specs in a mod's locdb string apply to raw numbers passed from SCAR?
5. Does `Loc_ToAnsi(Loc_GetString(modKey))` return the translated text for a non-English client? This decides whether the `PLURAL_RULE` trick in §1.8.5 is viable.
6. What does `Loc_FormatTime_M_S(...)[1]` return (core_objectives.scar:2781)?
