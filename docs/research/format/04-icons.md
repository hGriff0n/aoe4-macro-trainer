# 04 - Icons in SCAR UI (inline and alongside text)

Scope: every way SCAR can show an icon, with focus on icons inline with or next to text.
Sources: the aoe4-mcp index (`official_api`, `official_scar`, `official_ui`, `official_loc` source sets). File:line refers to that index, not to files in this repo.

Tags: **[API]** = official API doc (`Essence_ScarFunctions.api`). **[Usage]** = official SCAR/XAML usage (file:line). **[Loc/UI]** = observed in the loc DB or a UI resource. **[Inferred]** = not verified.

## Summary

| Need | How | Icon string format | Evidence |
|---|---|---|---|
| Icon inside a loc string | **Only input-binding glyphs**: `##ICON::<group>::<command>##` (e.g. `##ICON::menu_navigation::controller_a##`). No general image tag (`<icon=..>`, `[[A]]`, `{icon}`) exists | binding group + command name, as in `UI_AddCommandBinding` | [Loc/UI] 384 en rows, e.g. 999453 |
| Objective icon | `Obj_Create(..., icon, ...)`, `Obj_SetIcon(id, icon)`, or `objTable.Icon` with `Objective_Register` | Engine icon name: `"icons/objectives/objectives_capture_small"` | [API] + [Usage] core_objectives.scar:160,167 |
| Event cue icon | `UI_CreateEventCue(title, desc, template, icon, sfx, [vis, lifetime])` / `UI_CreateEventCueClickable(...)` | Engine icon name, either slash style: `"icons\\event_queue_high_priority"`, `"icons/event_queue_high_priority_large"`, or `""` | [API] + [Usage] ui.scar:516, event_cues.scar:331 |
| Icon + text + icon over a unit/building | `UI_CreateSquadKickerMessage` / `UI_CreatePositionKickerMessage` / `UI_CreateEntityKickerMessage` | Engine icon name (`"icons/resources/resource_food_icon"`) | [API] (squad/position), [Usage] missionomatic_upgrades.scar:1657 (entity) |
| Hint point / objective world marker icon | `HintPoint_Add(where, visible, text, height, actionType, iconName, ...)`, `Objective_AddUIElements(..., iconName, template)` | Engine icon name | [Usage] ui.scar:134, rogue_objectives.scar:777 |
| Minimap icon | `MapIcon_CreatePosition/Entity/Squad(target, icon, scale, r, g, b, a)` | Engine icon name: `"icons/minimap/area_circle"` | [API] + [Usage] ui.scar:781, core_objectives.scar:19 |
| Center-screen subtext with icon | `Game_SubTextFadeWithIcon(l1, l2, l3, in, dur, out, icon)` | Engine icon name [Inferred] | [Usage] ui.scar:739, cardinal_narrative.scar:264 |
| Call-to-action banner with an image | `EventCues_CallToAction(text, cta_type, intel, onClick, pos, duration, customImage, customStinger)` | `"icons/cta/illustrations/02_celebration"` | [Usage] event_cues.scar:342, rogue_objectives.scar:580 |
| Icon in **custom XAML** (the only way to put an icon inline in text) | `UI_AddChild(... "XamlPresenter" ...)` + `<Image Source="{Binding [key]}">`, inline in text with `<InlineUIContainer>` | **pack URI with `.png`**: `"pack://application:,,,/WPFGUI;component/icons/resources/resource_food_icon.png"` | [Usage] campaignpanel.scar:511, campaignpanel.scar#inline-xaml:1900, resourcetooltip.xaml:22-26 |
| Blueprint's own icon | `BP_GetSquadUIInfo(sbp, race).iconName`, `BP_GetEntityUIInfo(ebp).iconName`, `BP_GetUpgradeUIInfo(ubp).iconName` | Engine icon name (used directly as an event-cue icon) | [API] + [Usage] chart_a_course.scar:443 |
| Civ icon | `World_GetRaceIcon(Player_GetRace(p))`, then convert to pack URI | `icons\\races\\...` (no ext) -> pack URI | [Usage] campaignpanel.scar:507, diplomacy.scar:676 (not in API doc) |

**Main point:** there are two incompatible icon string formats.
1. **Engine icon name** (relative to the UI art root, no extension, `/` or `\\`). Native APIs take this format: objectives, event cues, kickers, hint points, map icons, subtext.
2. **WPF/Noesis image URI** (`pack://application:,,,/WPFGUI;component/<path>.png` or the short form `/WPFGUI;component/<path>.png`). XAML `Image.Source` takes this format.

Official SCAR converts format 1 to format 2 with `string.format("pack://application:,,,/WPFGUI;component/%s.png", string.gsub(name, "\\", "/"))`.

---

## 1. Inline icons inside localized strings: only input-binding glyphs (`##ICON::group::command##`)

> **Correction (verified by the coordinating session).** An earlier draft of this section said loc text contains no icon markup. That is wrong. 384 English rows contain a `##ICON::<group>::<command>##` token. The original scan missed it because it only looked for `<...>`, `[...]`, and `{...}`.

**[Loc/UI]** The token form is `##ICON::<binding_group>::<command_name>##`. Examples:
- 999453 "Move the camera over the Lumber Camp using ##ICON::menu_navigation::controller_left_stick_move## ."
- 999457 "Tilt ##ICON::menu_navigation::controller_right_stick_move## left or right to rotate the camera."

These are all the distinct tokens in the English locdb:
- `menu_navigation::` `controller_a`, `controller_b`, `controller_x`, `controller_y`, `controller_dpad`, `controller_dpad_up/down/left/right`, `controller_left_stick`, `controller_left_stick_move`, `controller_right_stick`, `controller_right_stick_move`, `controller_menu_1`, `controller_menu_2`, `left_bumper`, `right_bumper`, `left_trigger`, `right_trigger`, `open_summary_screen_diplomacy`
- `xbox_hud_dynamic_controller::open_diplomacy_panel`

**What it is [Inferred, strong]:** the `group::command` pairs are the same names official SCAR passes to `UI_AddCommandBinding(group, command, callback)`. For example, `UI_AddCommandBinding("menu_navigation", "controller_b", ...)` and `UI_AddCommandBinding("xbox_hud_dynamic_controller", "open_diplomacy_panel", ...)` appear at `gameplay/xbox_diplomacy_menus.scar:267-269`. So the token draws the glyph for **whatever input is bound to that command**. It is a key/button prompt, not a general-purpose image tag. You cannot point it at `icons/resources/...`. All official uses are controller/Xbox tutorial strings.

**Unknowns (need in-game test):**
- whether PC keyboard/mouse command groups (e.g. hotkey groups) also render through this token
- whether every display surface expands it (objectives, event cues, `Game_TextTitleFade`, XAML `Text` bindings)
- whether a token built at runtime and passed as a `Loc_FormatText` argument is expanded, or only a token baked into the loc entry itself

No SCAR code in the index builds `##ICON` strings; they appear only inside loc entries.

**[Loc/UI]** No other icon markup exists. The scan of every `locale='en'` row in `loc_entries` covered angle tags, square-bracket tokens, curly tokens, `$id` references, and non-ASCII characters above U+2000, including Private Use Area glyph-font characters. It found:
- no `<icon=...>`, `<img>`, `[[A]]`, `{icon:...}`, or PUA glyphs
- `<...>` hits that are literal help text, e.g. `<user>` and `<text>` in chat command help (11042766)
- `[...]` hits that are literal text: `[HINT]`, `[All]`, `[Team]`, `[%1KEY%]` (11225902). The brackets are printed; they are not markup.
- `%1NAME%`-style placeholders, which are text substitutions for `Loc_FormatText` and cannot inject images

**Conclusion:** apart from input glyphs, text shown by `Obj_Create`, event cues, kickers, `Game_TextTitleFade`, and similar APIs is plain text. To put an arbitrary icon (resource, unit, age) *inside* a run of text, you need custom XAML (section 5).

Elsewhere in the XAML UI, hotkey and mouse glyphs are drawn as images, for example `/WPFGUI;component/icons/dynamic_learning_left_click.png` (hudresources.xaml:2918) and `icons/xbox/radial_menu/dpad_arrow_up_selected.png` (relicradialmenu.xaml:768).

---

## 2. Icon parameters on native SCAR display APIs

All of these take the **engine icon name** format.

### 2.1 Objectives
- **[API]** `Obj_Create(PlayerID player, String title, String desc, String icon, String dataTemplate, String faction, ObjectiveType type, Integer parentID, String telemetryTitle)`
- **[API]** `Obj_SetIcon(Integer objectiveID, String icon)`: "Set icon path for the objective"
- **[API]** `UI_FlashObjectiveIcon(Integer objectiveID, Boolean stopOnClick)`
- **[Usage]** core_objectives.scar:160-167: `local icon = objTable.Icon or objTable.Type.objectiveIcon`, then `Obj_Create(owner, objTable.Title, objTable.Description or 0, icon, ...)`. So `Objective_Register({ ..., Icon = "..." })` is the high-level route.
- **[Usage]** objectives.scar:2180 compares `objTable.Icon == "icons/objectives/objectives_capture_small"`.
- **[Usage]** combat_mode.scar:680/712, regicide.scar:196 pass `_combat_mode.icons.*` / `_regicide.icons.objective` as the icon. The table values are not visible in the index.
- **[Loc/UI]** The objective list template renders the icon with `Source="{Binding Icon}"` (objectivetemplates.xaml:923). Its fallback is `<ImageSource x:Key="ObjectiveIcon">/WPFGUI;component/icons/objectives/objectives_generic_small.png</ImageSource>` (objectivetemplates.xaml:416). Icon size is `ObjectiveIconSize` = 24.

```lua
-- Objective with an explicit icon (engine icon name: no extension)
local obj = {
    Title = 11161274,            -- or a LocString
    Type  = OT_Primary,
    Icon  = "icons/objectives/objectives_capture_small",
}
Objective_Register(obj)
Objective_Start(obj, false, false)
-- change later:
Obj_SetIcon(obj.ID, "icons/objectives/objectives_warning_small")   -- [Inferred] path from the XAML list below, minus /WPFGUI;component/ and .png
```

### 2.2 Event cues
- **[API]** `UI_CreateEventCueClickable(Integer customEventType, Real lifetime, Integer repeatCount, Real repeatTime, String title, String description, String dataTemplate, String iconPath, String soundPath, Integer red, Integer green, Integer blue, Integer alpha, EventCueVisibility visibility, LuaFunction function)`
- **[API]** `UI_CreateEventCueClickableByType(UIEventType eventType, Real lifetime, String title, String description, String dataTemplate, String iconPath, String soundPath, r, g, b, a, EventCueVisibility visibility, LuaFunction function)`. There is also a `...CanQueue` variant.
- **[Usage]** ui.scar:516 Lua wrapper: `UI_CreateEventCue(title, description, data_template, icon_path, sound_path, [visibility, lifetime])`.
- **[Usage]** event_cues.scar:331: `UI_CreateEventCueClickable(-1, 10, 0, 0, text, description, "high_priority", "icons/event_queue_high_priority_large", "sfx_ui_event_queue_high_priority_play", 255, 255, 255, 255, ECV_Title, __DoNothing)`
- **[Usage]** king_of_the_hill_mode.scar:646, religious.scar:283, conquest.scar:810: `"event_with_player_color"` template + `"icons\\event_queue_high_priority"`. Many calls pass `""` for no icon (religious.scar:290).
- **[Usage]** chart_a_course.scar:443: `UI_CreateEventCue(upgrade_ui_info.briefText, Loc_Empty(), ..., upgrade_ui_info.iconName, ...)`. This shows that a blueprint UI-info `iconName` goes straight into the icon arg.
- **[Loc/UI]** The cue template binds `<Setter Property="Source" Value="{Binding Path=Icon}" />` with `DefaultEventCueImageStyle` (cardinalhudpage.xaml:6728, 10745).

```lua
-- Event cue with a resource icon
UI_CreateEventCue(LOC("Gather more food"), Loc_Empty(), "event_with_player_color",
    "icons/resources/resource_food_icon", "", ECV_Queue, 8)
```
(`"icons/resources/resource_food_icon"` as an engine icon name is [Usage] in missionomatic_upgrades.scar:1657. Its use in an event cue specifically is [Inferred].)

### 2.3 Kicker messages (icon + text + icon above a unit; the closest native "icon beside text")
- **[API]** `UI_CreateSquadKickerMessage(squad, locMessage, iconPath /*shown before message*/, symbolPath /*shown after message*/, durationSecs /*0 = default*/, xOffset, yOffset)`
- **[API]** `UI_CreatePositionKickerMessage(position, locMessage, iconPath, symbolPath, durationSecs, xOffset, yOffset)`
- **[API]** text-only: `UI_CreateSimpleSquadKickerMessage`, `UI_CreateSimplePositionKickerMessage`, `UI_CreateSimpleEntityKickerMessage`
- **[Usage, not in API doc]** missionomatic_upgrades.scar:1657: `UI_CreateEntityKickerMessage(entity, "$11255735", "icons/resources/resource_food_icon", "", 3, 0, 8)`
- **[Loc/UI]** Template (cardinalhudpage.xaml:4122-4126) is a horizontal StackPanel: `Image {Binding Icon}` (KickerIconStyle), `TextBlock {Binding Text}`, `Image {Binding Symbol}`.

```lua
UI_CreateSquadKickerMessage(sg_first_squad_here, LOC("+50"),
    "icons/resources/resource_food_icon", "", 3, 0, 8)
```

### 2.4 Hint points / objective world markers
- **[API]** `HintPoint_AddToEntity/Squad/Position(target, priority, visible, fn, dataTemplate, hint, arrow, arrowOffset, objectiveID, actionType, String iconName, visibleInFOW)`. These are documented as "internal use". The `EGroup`/`SGroup` variants are deprecated.
- **[Usage]** ui.scar:134 public wrapper: `HintPoint_Add(where, bVisible, hintText, height, actionType, iconName, priority, visibleInFOW, dataTemplate)`. Example: rogue_outlaws.scar:253 `HintPoint_Add(pos, true, text, 6, HPAT_Hint)`.
- **[Usage]** core_objectives.scar:765 `Objective_AddUIElements(objTable, pos[, ping, hintpointText, worldArrow, arrowOffset, arrowFacing, actionType, iconName, templateName])`. rogue_objectives.scar:777 passes `"icons/objectives/objectives_conqueror_small"` as `iconName`.

### 2.5 Minimap icons
- **[API]** `MapIcon_CreatePosition/Entity/Squad(target, String icon, Real scale, r, g, b, a)` returns an id. Also `MapIcon_SetFacing*`, `MapIcon_Destroy(id)`, `MapIcon_DestroyAll()`.
- **[Usage]** ui.scar:781 `MapIcon_CreatePosition(midpoint, "icons\\common\\minimap\\movement_arrow", math.floor(scale/1.8), r, g, b, a)`
- **[Usage]** core_objectives.scar:19-20 `AT_CIRCLE = "icons/minimap/area_circle"`, `AT_SQUARE = "icons/minimap/area_square"`
- **[Usage]** markerpaths.scar:68 defaults `iconName = "military_route_enemy"` after a "Setup the full icon name" comment. A prefix is probably added before the call, but that line is not visible in the index [Inferred].

### 2.6 Titles, subtitles, misc
- **[API]** `Game_TextTitleFade(String text, Real fadeIn, Real duration, Real fadeOut)`: **no icon parameter**.
- **[Usage]** ui.scar:739 `Game_SubTextFadeWithIcon(line1, line2, line3, fadeIn, duration, fadeOut, icon)` forwards to `Game_SubTextFadeInternal(..., icon)`. Used in cardinal_narrative.scar:264 with `titleCard.icon`.
- **[Usage]** event_cues.scar:342 `EventCues_CallToAction(text, cta_type, onTriggerIntel, onClickFunction, pos, duration, customImage, customStinger)`. `cta_type` is one of `CTA_ALARM`, `CTA_CELEBRATE`, `CTA_UNIQUE_STAKES`, `CTA_UNIQUE_CHANGE`. Example: `EventCues_CallToAction("$11270320", CTA_CELEBRATE, nil, nil, eg, 30, "icons/cta/illustrations/02_celebration")` (rogue_objectives.scar:580).
- **[API]** `Subtitle_PlayCharacterSpeech(String name, String text, String icon, String audioCtrlEvent)`
- **[API]** `UI_NewHUDFeature(HUDFeatureType, String featureText, String featureIcon, Real duration)`
- **[API]** `UI_MessageBoxSetButton(DialogResult, String text, String tooltip, String icon, Boolean isEnabled)`
- **[API]** `UI_GetAbilityIconName(ScarAbilityPBG abilityBag)`: "Returns the icon name for a given ability". No official usage was found.
- **[API]** `UI_OverrideUIProperty(pbg, propertyName, overrideValue)`: supports only `"screen_name"` and `"flag_icon"`, and must be called at script load time.

---

## 3. Getting a blueprint's icon

- **[API]** `BP_GetSquadUIInfo(sbp, rbp)`, `BP_GetEntityUIInfo(ebp)`, `BP_GetUpgradeUIInfo(ubp)` return the `ui_ext` info table.
- **[Usage]** Fields read by official SCAR: `screenName` (rogue_tech_tree.scar:391), `helpText` (current_dynasty_ui.scar:535), `briefText` and `iconName` (chart_a_course.scar:443, via `Game_ChartACourseGetPlayerUpgradeUIInfo`). No other field names were observed.
- **[Usage]** The official civ-flag pattern converts an engine icon name to a XAML URI (campaignpanel.scar:507, diplomacy.scar:676):
  ```lua
  civIcon = string.format("pack://application:,,,/WPFGUI;component/%s.png",
      string.gsub(World_GetRaceIcon(Player_GetRace(player)), "\\", "/"))
  ```
- **[Inferred]** The same conversion should work for `uiinfo.iconName` because it is in the same engine-icon-name format (2.2 passes it straight into an event cue). The official dynasty and age-up panels (`current_dynasty_ui.scar` / `templar_age_up_ui.scar` feeding `[squad][icon]`, `[building][icon]` in hudresources.xaml:1111/1134) do this somewhere. The exact assignment line is not in the index, so whether they convert first is **unverified**.

```lua
-- Helper (pattern copied from campaignpanel.scar:507)
local function IconToImageUri(iconName)
    if iconName == nil or iconName == "" then return "" end
    local path = string.gsub(iconName, "\\", "/")   -- gsub returns 2 values; keep the first
    if string.sub(path, -4) ~= ".png" then path = path .. ".png" end
    return "pack://application:,,,/WPFGUI;component/" .. path
end

local info = BP_GetSquadUIInfo(BP_GetSquadBlueprint("unit_villager_1_eng"), Player_GetRace(Game_GetLocalPlayer()))
local villagerIconUri = IconToImageUri(info.iconName)      -- for XAML Image.Source
local villagerIconName = info.iconName                     -- for event cues / objectives / kickers
```

**Gotcha:** `base_data_entries` `icon` fields are aoe4world.com URLs (e.g. `https://data.aoe4world.com/images\\units\\villager-1.png`). They are **not** game paths. Do not ship them. **[Loc/UI]**

---

## 4. Custom XAML: images and data binding

Lessons doc: custom UI = `UI_AddChild(parent, "XamlPresenter", name, { Xaml = ..., DataContext = UI_CreateDataContext(tbl) })`, refreshed with `UI_SetDataContext(name, tbl)`.
- **[Usage]** chaotic_climate_mode.scar:1073: `UI_AddChild("ScarDefault", "XamlPresenter", id, { IsHitTestVisible = false, Xaml = SeasonWidgetXaml, DataContext = UI_CreateDataContext(_match.data_context) })`
- **[API]** `UI_SetDataContext(String elementName, StackVarTable table)`. `UI_CreateDataContext` is used officially but is **not** in the API doc.

Image sources in official XAML:
- **Static, full pack URI:** `Source="pack://application:,,,/WPFGUI;component/icons/objectives/s11_dial_season_summer.png"` (chaotic_climate_mode.scar#inline-xaml:949).
- **Static, short form:** `Source="/WPFGUI;component/icons/HUD/events/cta_alert_event_icon.png"` (cardinalhudpage.xaml:10879). Also as a resource: `<ImageSource x:Key="ObjectiveIcon">/WPFGUI;component/icons/objectives/objectives_generic_small.png</ImageSource>` (objectivetemplates.xaml:416).
- **Bound from a Lua table** (indexer syntax `[key]`): `<Image Source="{Binding [resourceIcon]}" Width="32">` (campaignpanel.scar#inline-xaml:1900), fed by `resourceIcon = "pack://application:,,,/WPFGUI;component/icons/resources/resource_food_icon.png"` (campaignpanel.scar:511). Also `<Image Source="{Binding [imageSource]}" Opacity="{Binding [opacity]}" Width="32">` (diplomacy.scar#inline-xaml:1081).
- **Short form in Lua:** `_stone_icon = "/WPFGUI;component/icons/resources/resource_stone_icon.png"` (current_dynasty_ui.scar:246).
- **Hide when empty:** `Visibility="{Binding [icon], Converter={StaticResource NotNullOrEmptyStringToVis}, FallbackValue=Collapsed}"` (ageupmodalresources.xaml:902). The converter is declared in layoutresources.xaml:109. Whether a SCAR `XamlPresenter` can resolve it as a StaticResource is unverified.
- **No icon converter exists.** I found no `IconConverter`, `ImageConverter`, or similar in official XAML; converters matching icon/image/uri are only `SolidColorBrushConverter`, `LocalizedStringMultiConverter`, and `NullOrEmptyUri`. So convert to a URI in Lua before binding.

### Icon next to text (StackPanel; official pattern keytechs.xaml:47, teamheader.xaml:41-42)
```xml
<StackPanel Orientation="Horizontal">
    <Image Height="24" Source="{Binding [foodIcon]}" VerticalAlignment="Center" />
    <TextBlock Margin="4,0,0,0" VerticalAlignment="Center" Text="{Binding [foodText]}" />
</StackPanel>
```

## 5. Icons *inside* a line of text: `InlineUIContainer` (officially used)

**[Usage]** Official HUD XAML mixes `Run`s and images inside a single `TextBlock` with `InlineUIContainer`:
- resourcetooltip.xaml:22-26: `<Run Text="{esUtility:LocString $11168432}" />` `<Run Text="{Binding IncomePerMinute, Mode=OneWay}" />` `<InlineUIContainer>` `<Image ... VerticalAlignment="Bottom" Source="{Binding Icon}">`
- resourcespanel.xaml:~260-271 and xboxhudresources.xaml:3844: `</InlineUIContainer>` followed by `<Run Text="{Binding ..., Converter={StaticResource LocalizedStringConverter}, ConverterParameter=$11182589}" />`
- `<TextBlock.Inlines>` with `Run`s: campaignchangedifficultymodalpage.xaml:82, modsmanagepagemanagepane.xaml:256

So the UI framework (Noesis, WPF-compatible) supports `TextBlock` inlines: `Run` and `InlineUIContainer`. No `<Span>`, `<Hyperlink>`, or RichTextBox usage was found.

```xml
<!-- Inline icon in a sentence: "Gather [food icon] 200 food" -->
<TextBlock TextWrapping="Wrap" VerticalAlignment="Center">
    <Run Text="{Binding [prefix]}" />
    <InlineUIContainer BaselineAlignment="Center">
        <Image Width="20" Height="20" Margin="2,0,2,-4" Source="{Binding [foodIcon]}" />
    </InlineUIContainer>
    <Run Text="{Binding [suffix]}" />
</TextBlock>
```
```lua
local view = {
    prefix  = Loc_ToAnsi(LOC("Gather")),      -- or a localized string the binding accepts
    foodIcon = "pack://application:,,,/WPFGUI;component/icons/resources/resource_food_icon.png",
    suffix  = " 200",
}
UI_AddChild("ScarDefault", "XamlPresenter", "MT_InlineIconDemo",
    { IsHitTestVisible = false, Xaml = INLINE_ICON_XAML, DataContext = UI_CreateDataContext(view) })
```
[Inferred] `BaselineAlignment` and the negative bottom margin are standard WPF ways to align the image with the text. Official code uses `Margin="0,-8,0,0" VerticalAlignment="Bottom"` with a `RenderTransform` instead (resourcetooltip.xaml:26). Test both in-game.

Because loc text has no general-purpose icon markup, an inline icon at a variable position needs one of these:
- split the sentence into Runs and `InlineUIContainer`s yourself, or
- bind an `ItemsControl` (horizontal `WrapPanel`) to a list of `{kind="text"|"icon", value=...}` segments. [Inferred]

---

## 6. Verified icon paths

For XAML, use them with the `/WPFGUI;component/` or `pack://application:,,,/WPFGUI;component/` prefix and the `.png` suffix. For engine APIs, use them without either. Only the second column is confirmed as an engine icon name.

| Path (XAML form, relative to `WPFGUI;component/`) | Engine-name usage seen | Evidence |
|---|---|---|
| `icons/resources/resource_food_icon.png` | `icons/resources/resource_food_icon` (kicker) | campaignpanel.scar:511, missionomatic_upgrades.scar:1657 |
| `icons/resources/resource_wood_icon.png` | | campaignpanel.scar:513 |
| `icons/resources/resource_gold_icon.png` | | campaignpanel.scar:514 |
| `icons/resources/resource_stone_icon.png` | | current_dynasty_ui.scar:246, xboxselectioncard.xaml:2141 |
| `icons/resources/resource_silver_icon.png` | | xboxselectioncard.xaml:1675 |
| `icons/resources/resource_popcap.png` | | cardinalhudpage.xaml:9801 |
| `icons/resources/resource_idle_villager.png`, `resource_idle_villager_no_z.png`, `resource_no_villager.png` | | xboxhudresources.xaml:594, hudresources.xaml:6588, resourcespanel.xaml:24 |
| `icons/resources/resource_{berry,boar,deer,sheep,fish,farm}_icon.png` | | selectioncard.xaml:1743-1983 |
| `icons/resources/resource_relics_held_icon.png`, `resource_exp_icon.png`, `resource_taxes_collected_icon.png` | | cardinalhudpage.xaml:506, challengemissiondebriefingpage.xaml:336, selectioncard.xaml:1247 |
| `icons/HUD/governor/governor_villager.png`, `governor_food.png` | | keytechs.xaml:1372, 1296 |
| `images/fe/icon_age1.png` .. `icon_age4.png` | | xboxreplaytablepanel.xaml:370-376, replaystatviewer.xaml:218 |
| `icons/HUD/age/age_display_persistent_1.png` .. `_4.png` | | xboxhudresources.xaml:5832-5844 |
| `icons/objectives/objectives_generic_small.png` | | objectivetemplates.xaml:416 |
| `icons/objectives/objectives_capture_small.png` | `icons/objectives/objectives_capture_small` (objective) | objectives.scar:2180 |
| `icons/objectives/objectives_conqueror_small.png` | `icons/objectives/objectives_conqueror_small` (hintpoint) | rogue_objectives.scar:777 |
| `icons/objectives/objectives_{build,battle,warning,optional,leader,holy_site,wonder}_small.png` | | cardinalhudpage.xaml:4913-5216 |
| `icons/objectives/objective_complete.png`, `objective_failed.png`, `objective_tip.png` | | xboxhudresources.xaml:8368, hudresources.xaml:2637, cardinalhudpage.xaml:5017 |
| `icons/objectives/challenge_medal_{bronze,silver,gold}.png` | | cardinalhudpage.xaml:9566-9586 |
| `icons/HUD/objectives/objective_completed.png`, `objective_failed.png` | | cardinalhudpage.xaml:5554/5558 |
| `icons/HUD/events/cta_alert_event_icon.png`, `cta_celebration_event_icon.png`, `cta_raised_stakes_event_icon.png`, `cta_focus_change_event_icon.png` | | cardinalhudpage.xaml:10879-10924 |
| `icons/pings/cta_warning.png`, `ping_defend_icon.png`, `ping_lookhere_icon.png` | | cardinalhudpage.xaml:8117, xboxcardinalhudpage.xaml:11642 |
| `icons/production_warning.png`, `icons/garrisoned_unit.png`, `icons/tooltip_arrow_right.png`, `icons/transparent.png`, `icons/common/locked.png` | | hudresources.xaml:6681, cardinalhudpage.xaml:2690, ageupmodalresources.xaml:34, hudimageresources.xaml:165, challengepathsmodalpage.xaml:499 |
| `icons/notifications/circle_checkmark_icon.png`, `icons/races/chinese/dynasties/check_mark_gold.png` | | xboxnotificationtypes.xaml:459, hudresources.xaml:1198 |
| `icons/dynamic_learning_{left,right,middle,no}_click.png` (mouse glyphs) | | hudresources.xaml:2913-3053 |
| `icons/races/common/units/monk.png`, `trade_cart.png`; `icons/races/common/buildings/barracks.png` | | keytechs.xaml:170, xboxhudresources.xaml:8402, playerscores.xaml:67 |
| `images/civ_flags/civ_icon_secondary_<civ>.png` (english = `anglo_saxon_england`, `french`, `holy_roman_empirel`, `mongols`, `rus`, `chinese`, `abbasid`, `sultinates`, `malian`, `ottoman`, `byzantine`, `japanese`, ...; spellings as shipped) | | civflagicons.xaml:5-153 |
| | `icons/event_queue_high_priority`, `icons/event_queue_high_priority_large` | king_of_the_hill_mode.scar:646, event_cues.scar:331 |
| | `icons/minimap/area_circle`, `icons/minimap/area_square`, `icons\\common\\minimap\\movement_arrow` | core_objectives.scar:19-20, ui.scar:781 |
| | `icons\\races\\common\\victory_conditions\\victory_condition_conquest` | surrender.scar:207 |
| | `icons/cta/illustrations/{02_celebration,10_mongol_trebuchet,player_reinforcement_arrived,player_leader_has_arrived,announce_incoming_attack_naval}` | rogue_objectives.scar:533-1289, rogue_outlaws.scar:628 |

[Inferred] A file present in XAML form should also resolve as an engine icon name (drop the prefix and `.png`). The food icon is the only confirmed case.

---

## Gotchas

1. **Two formats.** Engine APIs use `icons/...` with no extension. XAML `Image.Source` uses `/WPFGUI;component/...png` or the `pack://` form. Passing the wrong one gives no image and probably no error [Inferred].
2. **Loc text cannot carry icons.** `[HINT]`, `[%1KEY%]` and similar are printed literally. Don't invent `<icon>` tags.
3. **`Game_TextTitleFade` has no icon.** Use `Game_SubTextFadeWithIcon` or an event cue.
4. **`string.gsub` returns two values.** Inside `string.format("%s", string.gsub(...))` the count is a harmless extra argument. As the last argument of a table constructor or call, wrap it in parentheses `(string.gsub(...))` to drop the count. In Lua, `"\\"` as a gsub pattern is a single literal backslash, which is fine.
5. **Undocumented but officially used:** `World_GetRaceIcon`, `UI_CreateEntityKickerMessage`, `UI_CreateDataContext`, `Game_SubTextFadeInternal`. They exist at runtime in shipped modes, but their signatures come only from call sites.
6. **`HintPoint_AddTo*`** are documented "internal use"/deprecated. Use the `HintPoint_Add` Lua wrapper or `Objective_AddUIElements`.
7. **base_data `icon` values are aoe4world URLs**, not game asset paths.
8. **`iconName` can be `""`.** Guard before converting, and hide the Image when it is empty.
9. **Project code to check.**
   - In the `gri-109-110-build-order-ui` worktree, `editor_discovery.scar:109` binds raw `uiInfo.iconName` to `Source="{Binding [icon]}"` (editor_ui.scar:102) with no pack-URI conversion. Its defaults use the `/WPFGUI;component/...png` form, so the two kinds of value are inconsistent. Likely needs `IconToImageUri` [Inferred].
   - In the `gri-51-hints` worktree, `Macro Trainer.scar:43` uses `SLOW_PHASE_HINT_ICON = "Icons_objectives_objective_secondary"`. This string does **not** appear anywhere in official SCAR/UI, so it is unverified and probably resolves to nothing. `"icons/objectives/objectives_optional_small"` or `"icons/objectives/objectives_generic_small"` are closer to known assets [Inferred].
10. **Xbox and high-contrast UIs use different art** (e.g. `*_xbox.png`, `*_hc.png`). Official SCAR branches on `UI_IsXboxUI()` (ui.scar:739).

## Open questions (need in-game test)

1. Does `Image.Source` bound to an engine icon name (`icons/races/...`, no pack and no `.png`) resolve? The official dynasty UI might do this; the assignment line is not indexed.
2. Does `BP_GetSquadUIInfo(...).iconName` use `\\` or `/`, and does it always start with `icons\\`? Print one with `print(info.iconName)`.
3. Do engine-name APIs (`Obj_SetIcon`, event cues, kickers) accept *any* `icons/...` art path, or only paths in a whitelisted atlas? For example, does `icons/resources/resource_wood_icon` work in an event cue?
4. Can a SCAR `XamlPresenter` use `{StaticResource NotNullOrEmptyStringToVis}` and `{StaticResource LocalizedStringConverter}` without redeclaring them?
5. `InlineUIContainer` vertical alignment inside a `XamlPresenter` TextBlock: compare `BaselineAlignment` with official-style negative margin.
6. Does `UI_GetAbilityIconName` return the same engine-name format?
7. Can mod-packaged PNGs be referenced (e.g. `pack://application:,,,/<ModAssembly>;component/...`)? No evidence either way. All verified sources are `WPFGUI;component`.
