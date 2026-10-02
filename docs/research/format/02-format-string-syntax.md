# 02 - Format-string syntax inside AoE4 localized strings

Scope: what can appear **inside** the text of a loc entry that is shown by the game or passed through `Loc_FormatText`. This covers placeholders, number specs, escapes, inline icons and other markup, and how SCAR supplies arguments.

**Method.** I streamed every `en` row of `loc_entries` (`source_set='official_loc'`, 30,919 rows covering 30,637 distinct ids; some ids appear more than once) from `E:\Docs\github\aoemod\aoe4-mcp\data\index.sanitized.sqlite3` and ran a hand-written tokenizer and regexes over the text. I compared the results against the 25 other locales (`cardinal.*`, `zh-hans`, `zh-hant`). I extracted every `Loc_FormatText(...)` call from `code_records` (`official_scar`, 97 distinct calls) and every `LocalizedStringConverter` binding from `official_ui` (282 distinct id/binding pairs), then joined them to the loc text.

**Tags.**
- **Observed in locdb**: the pattern is in the official text.
- **Official usage**: official code uses it (`file:line` is cited).
- **Inferred/unverified**: my reading, not confirmed in game.

Unless stated otherwise, counts are `en` official rows.

---

## 1. Summary grammar

```
text        := ( literal | placeholder | pct_escape | bs_escape | icon_tag )*
placeholder := "%" DIGIT+ suffix? ( ":" spec )? "%"
suffix      := any chars except "%" and ":"     ; descriptive label, ignored by the formatter (inferred, strong evidence)
spec        := ".0" | ".1" | ".2" | "02" | "0"  ; all specs seen in en
pct_escape  := "%%"                             ; literal "%"
bs_escape   := "\r\n" | "\n" | "\t"             ; stored as literal backslash sequences
icon_tag    := "##ICON::" category "::" name "##"
```

| Construct | Example | en rows (occurrences) | Status |
|---|---|---|---|
| `%N%`, bare numbered placeholder | `%1% has been injured` (11189636) | 1532 (2676) | Observed + Official usage |
| `%NNAME%`, with a name suffix | `%1PLAYER_NAME% surrendered` (11161289) | 901 (1142) | Observed + Official usage |
| `%NNAME:spec%` | `%1AMOUNT:.0%` (11144600) | 84 (99) | Observed + Official (UI) usage |
| `%N:spec%` | `%1:.0% Health` (11163718) | 25 (30) | Observed + Official (UI) usage |
| `%%`, literal percent | `%1AMOUNT:.0%%%` (11145977) | 891 (1239) | Observed + Official (UI) usage |
| `\r\n` | most multi-line descriptions | 1726 | Observed |
| bare `\n` | `%1ITEM%\n%2ITEM%` (999212) | 156 | Observed |
| `\t` | 1000738 | 1 (10) | Observed |
| `##ICON::cat::name##` | `Press ##ICON::menu_navigation::controller_a## ...` (1000996) | 381 (488) | Observed + Official usage |
| `$<id>` as the whole text (alias) | `$11196693` (11197316) | 4 | Observed |
| Markdown link and `_italic_` | `[View on website](https://aoe.ms/nda)` (11205210) | 9 links, 3 italic | Observed (beta/NDA strings only) |
| printf `%s` / `%d` / `%1!d!` | `[%s] GB free` (11141489), `Error code: %1!d!` (11205341) | 2 / 1 / 2 | Observed (native/launcher strings, not SCAR) |
| `{0}`, `${x}`, `[[x]]`, `<color>`, `<b>`, BBCode, `<img>`, `[icon:..]` | none | **0** | Not present |
| plural / gender / select syntax | none | **0** | Not present |

Highest placeholder index used: **9**. Index usage counts: `%1`=2537, `%2`=896, `%3`=293, `%4`=111, `%5`=48, `%6`=30, `%7`=14, `%8`=10, `%9`=8. **Observed in locdb.**

---

## 2. Placeholders

### 2.1 Number part (`%N...%`)
- Indexes are 1-based and refer to the varargs of `Loc_FormatText(id, arg1, arg2, ...)`. **Official usage**: `scarutil.scar:2382` has `function Loc_FormatText(LocID, ...)`, which packs `{...}` and calls the native `Loc_FormatTextInternal(LocID, arg)` (`scarutil.scar:2386`).
- **Out of order is allowed.** In `en`, 47 rows use placeholders out of order:
  - `%2MINUTES%m %1SECONDS%s` (11153690)
  - `%3DAYS%d %2HOURS%h %1MINUTES%m` (11221549)
  - `... +%1%%% ... +%3%%%. ... +%2%%%.` (11265378)

  Translations reorder placeholders in **748** rows; for example cs 11161258 `%2PLAYER_NAME% ti posílá %1AMOUNT% jídla`. Official SCAR passes the same arguments for every locale (`diplomacy.scar:1290`), so the index is what binds. **Observed in locdb** + **Official usage**.
- **Repeats are allowed.** 12 rows reference the same index twice:
  - `costs -%1%%% and researches %1%%% faster` (11220658)
  - `Cannot assign Villagers to %1ResourceType%. No available %1ResourceType% sources` (1001597)
  - `+%1%/%1% armor` (11253493)

  **Observed in locdb.**
- **Gaps are allowed.** 32 rows skip indexes. For example, `%2TEXT%` alone (11166909) ignores argument 1. **Observed in locdb.**
- **Extra arguments are harmless.** `wonder.scar:825` calls `Loc_FormatText("$11197866", 2)`, and that entry's text is `1 minute until Wonder Victory`, which has no placeholder. **Official usage.** (That the engine silently ignores the extra argument is inferred: the code ships.)

### 2.2 Name suffix (`%1PLAYER_NAME%`)
There are 290 distinct suffixes in `en`, for example `ERRORCODE` (168), `AMOUNT` (90), `PLAYER_NAME` (73), `datavalue` (59), `NAME` (49), `TEXT` (36) and `COUNT` (29). Case is free (`PlayerName`, `PLAYERNAME`, `Player`, `name`).

**The suffix carries no meaning to the formatter.** Treat it as a translator comment. Evidence:
- **Same suffix, different arguments.** 11200672 is `Bronze Medal (Goal %1TIME_REQUIREMENT%m %2TIME_REQUIREMENT%s)` and is called with `(goal_m, goal_s)` (**Official usage** `missionomatic/missionomatic_artofwar.scar:80`).
- **Translators localize the suffix.** In 103 translated rows the suffix differs from `en` while the indexes stay the same:
  - pt-br `%1QUANTIDADE:.1%%%` (11272902)
  - cs `%3HODINY%h %2MINUTY%m %1SEKUNDY%s` (11153689)
  - cs `%1HOD.:02%` (1254, which shows a `.` can appear inside the suffix)
  - pt-br `%1NÚMERO%` (11272739, non-ASCII)

  **Observed in locdb.**
- **The suffix type does not need to match the argument type.** `%1AMOUNT:.0%` (11144600) is bound to `SelectedMissionScenario.DisplayYear` and `Score` (`official_ui/loading/pages/loadcampaignpage.xaml:102`). `%1REMAINING_TIME%` receives a plain number (`combat_mode.scar:1116`). **Official usage.**
- **A suffix can contain a space.** One row has `%2UNIT NAME%` (11046953). **Observed in locdb**; whether it renders correctly is unverified.

**Inferred parse rule:** `%` + digits + everything up to the next `%`. A `:` within that span introduces the spec, and whatever else is in the span is ignored.

### 2.3 Spec after `:`
Distinct specs in `en`:

| Spec | Occurrences | Examples | Bound value (official UI) |
|---|---|---|---|
| `.0` | 108 | `%1AMOUNT:.0%` (11144600), `%1:.0%/min` (11163721), `%1SCORE:.0%` (11193765) | Float and Int bindings, e.g. `StateModel.Float[military_score]` (`hud/controls/playerscores.xaml:176`) |
| `.1` | 7 | `%1AMOUNT:.1%` (1000683), `%1AMOUNT:.1%%%` (11272902), `%1COUNT:.1% GB VRAM \|` (11207730) | `VillagersEfficiency` (`replaystatviewer.xaml:2107`) |
| `.2` | 6 | `%1:.2% Tiles/s` (11163720), `%1VALUE:.2%` (11203565), `%1Seconds:.2%s` (11114106) | `TilesRange`, `Penetration` (`selectioncardtooltip.xaml:451,471`) |
| `02` | 5 | `%1HOURS:02%:%2MINUTES:02%:%3SECONDS:02%` (1254), `%1MINUTES:02%:%2SECONDS:02%` (1272) | (not found in a binding) |
| `0` | 3 | `%1:0% / %2:0% XP` (11168859), `%2AMOUNT:0%` (11164353) | (not found in a binding) |

Readings:
- `.N` means "N decimal places". This is inferred from the numbers involved (`Tiles/s` with 2 decimals, `GB VRAM` with 1).
- `02` likely means "zero-pad to width 2" (it is used in `HH:MM:SS`). Inferred.
- `0` alone is unclear. It may be "0 decimals" or "width 0". Unverified.
- **No `+` spec exists.** A leading plus is literal text: `+%1AMOUNT:.0%` (11219207) and `%1AMOUNT:.0%+` (11232238).

Translator errors seen in other locales: `%1:,2%` (cs 11163720), `%1:0.0%` (es/es-419 11163718), `%1MENGDE:. 1%` (no 11272902), `%2AMOUNT:./+%` (ja 11265646) and `%1UNREST:.%0` (tr 11255772). This suggests the game tolerates bad specs without crashing, but that is **Inferred/unverified**.

Precision without a colon: `%2.1%` (10 rows), `%1.1%` (4) and `%4.1%` (1), e.g. `range by %2.1%` (11142976) and `You have used %1.1% out of %2.1% MB` (11268887). Under the parse rule in 2.2, `.1` would be a suffix, which would make these plain placeholders with no precision. **Inferred/unverified.**

**Every spec-bearing official usage is in WPF XAML** (`Converter=LocalizedStringConverter, ConverterParameter=$id`). **None** of the 91 literal-id `Loc_FormatText` calls in official SCAR targets a string with a spec. Whether `Loc_FormatText` (the SCAR path) honors `:.1` when given a Lua float is **unverified**. The SCAR API also has `Loc_FormatNumber(Real number, Integer numDecimalPlaces)` and `Loc_FormatInteger(Integer)` (from `api_functions`), which is the documented way to control decimals from SCAR.

### 2.4 Percent handling
- `%%` produces a literal `%`. The common pattern `%1%%%` means placeholder 1 followed by a literal percent. Examples: `%1%%% reduced Ranged damage.` (11248741) and `%1AMOUNT:.0%%%` (11145977, bound to `PercentageValue` in `castermode/selectioncard.xaml:640`). **Observed + Official (UI) usage.**
- **Lone `%` appears in static strings:** 681 occurrences such as `+20% Armor` (11180935) and `50% Complete` (11168286). These strings are never formatted, so the `%` survives. **Observed in locdb.**
- Seven formatted strings also contain a lone `%`. They look like authoring bugs:
  - `Sabotage Points: %1%%` (11272122)
  - `%1PLAYER_INDEX% %2AILEVEL%%` (11262605)
  - `%1%+ Traders: +10% Food` (11251706)

  How the engine renders a stray `%` in a formatted string is **unverified**.
- **Tokenizer rule (inferred):**
  - `%` followed by a digit starts a placeholder.
  - `%` followed by `%` is a literal percent.
  - Anything else is a literal `%`.

  Under this rule, `%1%%2%` is two adjacent placeholders (seen in `%1TEXT%%2TEXT%`, 3 rows). `%1%%%` is a placeholder followed by `%%`.

### 2.5 Other placeholder dialects (not for SCAR)
- `[%s]` (11141489, 11206288), `[ %d ]` (11051138) and `%1!d!` (11205341, 11205342) are C printf and Win32 `FormatMessage` styles. They appear in launcher, system and RAM-warning strings that the native code formats. Do not author these for `Loc_FormatText`. **Observed in locdb**; the rendering path is inferred.
- `%1X%.%2Y%` (id 1) looks like a version-style "X.Y" template. The official UI binds it to a single float (`hudresources.xaml:5580`, `Float[master_hunter_bounty_total_rus]`), so its exact behavior is an **open question**.

---

## 3. Escapes and line breaks
- The `.ucs` source is one entry per line in the form `id<TAB>text` (the MCP parser is `aoe4_mcp/loc_parser.py:99`, `parse_loc_ucs`). Line breaks therefore **cannot** be stored raw: no row contains a real CR or LF. They are stored as **literal two-character sequences**: `\r\n` (1726 rows), `\n` (156 rows) and `\t` (1 row). The game turns them into real breaks or tabs at display time; this is **Inferred**, based on how they are used in tooltips and descriptions.
- No lone `\r` was seen.
- Other backslash pairs exist only in non-text data, such as Windows paths in 11265405 and `map_gen_biome\minspec` debug strings, and the list of forbidden filename characters in 11050296. So **`\` is not a general escape character**. Only `\r`, `\n` and `\t` appear to be interpreted. **Inferred.**
- There are no `&amp;` or other XML entities, and no quote escaping: `"` and `'` appear raw.
- There is no real tab character in any text; a tab would break the `.ucs` format.
- Non-breaking spaces (U+00A0) appear 89 times in 66 rows, e.g. `Destroyed %1PLAYER_NAME%'s Wonder` (11198647). This is how authors prevent a line wrap. **Observed in locdb.**
- Bullets and punctuation are plain Unicode: `•` (531 occurrences), `…` (380), `–` (228), `—` (39). There is no bullet markup. **Observed in locdb.**

## 4. Markup and rich text
- **Inline icons: `##ICON::<category>::<name>##`.**
  - 488 occurrences in 381 `en` rows.
  - There are 20 distinct icons: 19 in category `menu_navigation` (`controller_a`/`b`/`x`/`y`, `left_trigger`, `right_bumper`, `controller_dpad_*`, `controller_left_stick_move`, `controller_menu_1`/`2`, `open_summary_screen_diplomacy`, ...) and 1 in `xbox_hud_dynamic_controller::open_diplomacy_panel`.
  - Translators keep the tag. 12,121 occurrences across locales; pseudo-loc builds even mangle it, e.g. `##ÎÇÔŃ::...` in pt-br 11254265.
  - It is used by official SCAR training goals, e.g. `Message = 1000978` in `training/coretraininggoals.scar:165` and `Message = 1001021` in `training/abbasidtraininggoals.scar:153`.
  - No `en` string combines `##ICON##` with a `%N%` placeholder.
  - Whether the tag renders in every widget (objective titles, event cues, our UI), and whether non-controller icon categories exist, is **unverified**.
- **Whole-string alias: `$<id>`.** The entire text is a reference to another entry: `$11196693` → `Bureau Brothers' Workshop` (11197316/11197317), and `$11199747` → `Warring Islands` (11199751). 4 rows. **Observed**; that the engine resolves it is **inferred**, because `$id` is also the syntax SCAR and XAML use for loc keys (section 5).
- **Markdown-style links and italics**, found only in the closed-beta/NDA strings:
  - `[View on website](https://aoe.ms/nda)` (11205210)
  - `Welcome to the _Age of Empires IV_ Closed Beta!` (11205172)
  - `[_Age_ Insider Non-Disclosure Agreement (NDA)](https://aoe.ms/nd...)` (11205169)

  These are probably rendered by a dedicated front-end widget. Do not expect this to work in SCAR-driven HUD text. **Inferred.**
- **XML-like text is data, not markup.** `<locstring name="screen_name" value="11218603" />` (11265625) and `<file name="animator" .../>` (11265405) are data blobs. `<user>`, `<N> <M>`, `<text>`, `<Search>` and `<Chat Here>` are literal user-facing placeholder text in chat help, and translators translate them (`<Nutzer>`, `<Suche>`). **Observed in locdb.**
- **Square brackets are literal text**: `[No Selection]`, `[Team]`, `[NO LONGER VALID]`, `[%1TIME%]` (11155193), `[%1KEY%]` (11225902). **Observed.**
- **`|` is a literal separator**: `%1DATE% | %2TIME%` (11189970), 8 rows. **Observed.**
- **`#` is literal text**: `Tutorial Title #1` (11169877). **Observed.**
- **Absent entirely:** color tags, `<b>`/`<i>`, font size, `<img>`, `<icon>`, `[icon:...]`, BBCode, `{0}`/`{name}`, `${...}`, `[[...]]`. These were checked with regex over all `en` rows and found in **no** locale. Text color and style come from the WPF template, not from the string.

## 5. Plural, gender and select
**No syntax exists.** There is no `{n, plural, ...}`, no `%1:plural%`, and no `|` alternatives. Official text either:
- hard-codes separate entries: `1 minute until Wonder Victory` (11197866) vs `%1MINUTES_REMAINING% minutes until Wonder Victory` (11197864), where SCAR chooses the id (`wonder.scar:683` vs `:825`); or
- uses unit abbreviations: `%1MINUTES%m %2SECONDS%s`.

**Observed + Official usage.**

## 6. How SCAR supplies arguments: verified official pairs

The first argument of `Loc_FormatText` takes three forms:
- a `"$<id>"` string (most calls);
- an integer id, e.g. `Loc_FormatText(11120883, ...)` (`core_objectives.scar:2733`);
- an already-resolved LocString or id held in a variable, e.g. `_events.age.textAge4` (`gameplay/event_cues.scar:194`) and `resource.help` (`gameplay/diplomacy.scar:714`).

The result is a LocString.

| Loc id | en text | Official call (file:line) | Argument type for each placeholder |
|---|---|---|---|
| 11161289 | `%1PLAYER_NAME% surrendered` | `winconditions/surrender.scar:186` `Core_GetPlayerName(playerID)` | LocString (player name) |
| 11164967 | `Food for %1PLAYER_NAME%` | `campaignpanel.scar:511` `Player_GetDisplayName(player)` | LocString |
| 11161258 | `%1AMOUNT% food received from %2PLAYER_NAME%` | `gameplay/diplomacy.scar:1290` `(tribute.food, Player_GetDisplayName(...))` | %1 = Lua number, %2 = LocString |
| 11159070 | `Defend %1PLAYER_NAME%'s Wonder` | `winconditions/wonder.scar:941` `player_owner.playerName` | LocString (`playerName = Player_GetDisplayName(id)`, `core.scar:400`) |
| 11268922 | `Waves Starting in %1%` | `rogue/rogue_objectives.scar:949` `Loc_FormatTime_M_S(math.ceil(t), true)` | LocString (formatted time) |
| 11271501 | `Firing in %1%` | `rogue/rogue_objectives.scar:1473` `Loc_FormatTime_M_S(...)` | LocString (time) |
| 11161288 | `Next round starts in: %1REMAINING_TIME%` | `gamemodes/combat_mode.scar:1116` `data.endTime - math.floor(World_GetGameTime())` | Lua number (seconds) |
| 11161272 | `Round %1ROUND_NUMBER%: Build an army` | `gamemodes/combat_mode.scar:677` `_combat_mode.round` | Lua number |
| 11161293 | `%1ROUNDS_WON%/%2TOTAL_ROUNDS%` | `gamemodes/combat_mode.scar:1474` | number, number |
| 11184017 | `Site %1NUMBER%` | `winconditions/religious.scar:863` `i` | Lua number (loop index) |
| 11197864 | `%1MINUTES_REMAINING% minutes until Wonder Victory` | `winconditions/wonder.scar:683` `12` | number literal |
| 11270162 | `Raided %1%` | `rogue/rogue_objectives.scar:1261` `thisRaidReward` | Lua number (computed, e.g. `* 10` at :1246) |
| 11189636 | `%1% has been injured` | `missionomatic/missionomatic_leader.scar:243` `leaderData.name` | LocString (forced via `Loc_GetString` at :15; `fatal` if not `ST_LOCSTRING`, :20) |
| 39300 | `Objective Completed: %1OBJECTIVE_TITLE%` | `core_objectives.scar:2248` `title` | LocString (objective title) |
| 11200672 | `Bronze Medal (Goal %1TIME_REQUIREMENT%m %2TIME_REQUIREMENT%s)` | `missionomatic/missionomatic_artofwar.scar:80` | number, number (same suffix, two arguments) |
| 11202194 | `Bronze Medal (Fewer Than %1UNITS_LOST% Units Lost)` | `missionomatic/missionomatic_artofwar.scar:144` `maxUnitsDied+1` | number expression |
| 11120883 / 11129961 | *(not in current locdb)* | `core_objectives.scar:2733`, `:2783` `(data.text, Loc_FormatInteger(hp), Loc_FormatInteger(total))` | LocString plus LocStrings from `Loc_FormatInteger` and `Loc_FormatTime_M_S` |

Notes:
- **Raw Lua strings.** No official `Loc_FormatText` call passes a raw Lua string. Official helpers convert strings first: `Setup_Player` runs "accept raw strings for now... convert them to LocString" via `LOC(playerName)` (`scarutil.scar:146-147`), and `_ReturnLocVersion` does `LOC(item)` for `ST_STRING` (`gameplay/event_cues.scar:301`). So for user-typed or raw text, wrap it as `LOC(str)` before passing it. Whether a bare Lua string also works is **unverified**.
- **Numbers.** Plain Lua numbers (integers in every official case) are passed directly to bare or named placeholders. For decimals, the official SCAR pattern is to pre-format with `Loc_FormatInteger`, `Loc_FormatTime_*` (or `Loc_FormatNumber`), and to use `%1%`, not a `:.N` spec. **Official usage.**
- **UI path.** The WPF path (`LocalizedStringConverter`, `ConverterParameter=$id`, a single bound value as `%1`) is where `:.N` specs are used. 282 binding pairs were found, e.g. `$11163718` with `CombatEfficiency.MaxHealth` (`hud/controls/selectioncardtooltip.xaml:175`). `LocalizedStringMultiConverter` (`lobby/widgets/taskbarwidget.xaml:273`) is the multi-argument variant. **Official usage.**

## 7. Gotchas
1. **The suffix is not a key.** `%1COUNT% %1RESOURCE%` prints argument 1 twice. This bug is live in this repo: `assets/locdb/Macro Trainer_en.csv` ids **170-173** use `%1...` for every slot. Id 172 also has a stray ` | ` between count and resource. They need `%1..%2..%3..%4..`. (Observed in the project file; the official counter-example is 11200672.)
2. **`%2.1%` is not `%2:.1%`.** Without the colon, `.1` is most likely just a suffix, so no precision is applied. Always write `:`.
3. **A literal percent after a placeholder is `%1%%%`.** `%1%%` leaves a dangling `%` (bug pattern in 11272122).
4. **Do not use printf (`%s`, `%d`) or .NET (`{0}`) syntax.** They are native-only or nonexistent.
5. **Newlines.** Write `\r\n` (or `\n`) as literal backslash sequences in the loc source. Our CSV pipeline must not convert them into real newlines (inferred from the `.ucs` line format).
6. **No plural or select syntax.** Use separate ids and branch in SCAR.
7. **Placeholder order is free; argument order is fixed.** Translators reorder `%N`, so never build sentences by concatenating fragments when a single template with numbered placeholders would do.
8. **Specs are only proven on the XAML converter path.** For SCAR text, pre-format numbers (`Loc_FormatInteger`, `Loc_FormatNumber`, `Loc_FormatTime_M_S`).
9. **Use a non-breaking space** before a placeholder to keep "Destroyed %1PLAYER_NAME%" on one line (official 11198647).

## 8. Open questions (need in-game test)
1. Does `Loc_FormatText` honor `:.0`, `:.1` and `:.2` with a Lua float (e.g. `3.14159` → `3.14`)? What does `:02` do in the SCAR path?
2. What does a raw Lua string argument do: rendered as is, rejected, or shown as an id? Compare with `LOC(str)`.
3. Is a missing argument (placeholder index greater than the number of args) rendered as empty, as `%2%`, or as an error?
4. Does `##ICON::menu_navigation::controller_a##` render in objective titles and event cues on PC? Do other icon categories (resources, units) exist?
5. Is a `$<id>` whole-string alias resolved when the alias id is fetched via `Loc_FormatText` or `Loc_GetString`?
6. How are a stray single `%` and a space-containing suffix (`%2UNIT NAME%`) rendered?
7. Does a placeholder whose argument is itself a LocString containing `%1%` get re-expanded (recursive formatting)? This matters for nesting our `%1TEXT%` wrappers (project ids 143, 145, 146, 153, 154).
8. What are the semantics of spec `0` (`%1:0%`, 11168859) and of the `%1X%.%2Y%` template (id 1) bound to a single float?
