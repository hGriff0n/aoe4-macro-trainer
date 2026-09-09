import csv
import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from tests.scar_runtime import LuaResults, ScarRuntime


ROOT = Path(__file__).resolve().parents[1]
UI_SCAR = ROOT / "assets" / "scar" / "build_orders" / "editor_ui.scar"
MODEL_SCAR = ROOT / "assets" / "scar" / "build_orders" / "editor_model.scar"
SCHEMA_SCAR = ROOT / "assets" / "scar" / "build_orders" / "editor_schema.scar"
LOCDB_PATH = ROOT / "assets" / "locdb" / "Macro Trainer_en.csv"
MOD_NAMESPACE = "dfb5645698a84afb91cf7a2dfb0f4a4e"

PRESENTATION_NS = "http://schemas.microsoft.com/winfx/2006/xaml/presentation"
XAML_NS = "http://schemas.microsoft.com/winfx/2006/xaml"
NS = {"p": PRESENTATION_NS}


def function_body(source: str, name: str) -> str:
    match = re.search(
        rf"^function {re.escape(name)}\([^\n]*\)\n(.*?)(?=^function |\Z)",
        source,
        flags=re.MULTILINE | re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"missing function {name}")
    return match.group(1)


def extract_long_string(source: str, name: str) -> str:
    match = re.search(
        rf"{re.escape(name)}\s*=\s*\[\[(.*?)\]\]",
        source,
        flags=re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"missing {name}")
    return match.group(1)


def extract_xaml(source: str) -> str:
    return extract_long_string(source, "BUILD_ORDER_EDITOR_UI_XAML")


def named(root: ET.Element, name: str) -> ET.Element:
    keys = (f"{{{XAML_NS}}}Name", f"{{{XAML_NS}}}Key")
    for element in root.iter():
        if any(element.get(key) == name for key in keys):
            return element
    raise AssertionError(f"missing x:Name/x:Key={name}")


def strip_xaml(source: str) -> str:
    source = re.sub(
        r"BUILD_ORDER_EDITOR_UI_PROBE_XAML\s*=\s*\[\[.*?\]\]",
        'BUILD_ORDER_EDITOR_UI_PROBE_XAML = ""',
        source,
        flags=re.DOTALL,
    )
    return re.sub(
        r"BUILD_ORDER_EDITOR_UI_XAML\s*=\s*\[\[.*?\]\]",
        'BUILD_ORDER_EDITOR_UI_XAML = ""',
        source,
        flags=re.DOTALL,
    )


def csv_rows(path: Path) -> dict[int, list[str]]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        return {
            int(row[0]): row
            for row in csv.reader(source)
            if row and row[0].isdigit()
        }


def child_nodes(node):
    for key in ("fields", "items", "checks", "resource_groups"):
        values = node[key]
        if values is not None:
            yield from values.array()


def find_view_node(root, path: str):
    pending = [root]
    while pending:
        node = pending.pop()
        if node["path"] == path:
            return node
        pending.extend(child_nodes(node))
    raise AssertionError(f"missing projected node {path}")


class BuildOrderEditorUIContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = UI_SCAR.read_text(encoding="utf-8")
        cls.xaml = extract_xaml(cls.source)
        cls.xaml_root = ET.fromstring(cls.xaml)

    def test_exports_the_ui_lifecycle_contract(self) -> None:
        for name in (
            "BuildOrderEditorUI_EnsureCreated",
            "BuildOrderEditorUI_ShowSelector",
            "BuildOrderEditorUI_ShowEditor",
            "BuildOrderEditorUI_ShowNoSelectionConfirmation",
            "BuildOrderEditorUI_Hide",
            "BuildOrderEditorUI_Stop",
            "BuildOrderEditorUI_SetCallbacks",
        ):
            with self.subTest(name=name):
                function_body(self.source, name)
        stop = function_body(self.source, "BuildOrderEditorUI_Stop")
        self.assertIn("BUILD_ORDER_EDITOR_UI_STATE.callbacks = {}", stop)
        self.assertIn("BUILD_ORDER_EDITOR_UI_STATE.commands = nil", stop)

    def test_probe_layers_editor_region_over_selector_in_one_root(self) -> None:
        probe_xaml = extract_long_string(self.source, "BUILD_ORDER_EDITOR_UI_PROBE_XAML")
        root = ET.fromstring(probe_xaml)

        self.assertEqual(root.tag, f"{{{PRESENTATION_NS}}}Grid")
        self.assertEqual(root.get(f"{{{XAML_NS}}}Name"), "BuildOrderEditorProbe")
        selector = named(root, "BuildOrderSelectorProbe")
        editor_overlay = named(root, "BuildOrderEditorOverlayProbe")
        editor = named(root, "BuildOrderEditorShellProbe")
        self.assertIsNone(selector.get("Visibility"))
        self.assertEqual(
            editor_overlay.get("Visibility"), "{Binding [editor_visibility]}"
        )
        self.assertEqual(list(root).index(editor_overlay), list(root).index(selector) + 1)
        self.assertEqual(editor.get(f"{{{XAML_NS}}}Name"), "BuildOrderEditorShellProbe")
        self.assertNotIn(f"${MOD_NAMESPACE}:", probe_xaml)

        dropdown = named(selector, "BuildOrderSelectorDropdown")
        self.assertEqual(dropdown.get("ItemsSource"), "{Binding [selector_options]}")
        self.assertEqual(
            dropdown.get("SelectedIndex"),
            "{Binding [selected_index], Mode=OneWay}",
        )
        self.assertIsNone(dropdown.get("SelectedItem"))
        self.assertEqual(dropdown.get("DisplayMemberPath"), "[label]")
        dropdown_xml = ET.tostring(dropdown, encoding="unicode")
        self.assertIn("CallCommandTrigger", dropdown_xml)
        self.assertIn("{Binding [commands][select]}", dropdown_xml)

        action = named(selector, "BuildOrderSelectorAction")
        self.assertEqual(action.get("Content"), "{Binding [action_label]}")
        self.assertEqual(action.get("Command"), "{Binding [commands][action]}")
        self.assertIsNone(action.get("CommandParameter"))
        unpause = named(selector, "BuildOrderSelectorUnpause")
        self.assertEqual(unpause.get("Command"), "{Binding [commands][unpause]}")
        save = named(editor, "BuildOrderEditorSave")
        self.assertEqual(save.get("IsEnabled"), "False")
        cancel = named(editor, "BuildOrderEditorCancel")
        self.assertEqual(cancel.get("Command"), "{Binding [commands][cancel]}")
        self.assertEqual(
            [button.get(f"{{{XAML_NS}}}Name") for button in selector.findall(".//p:Button", NS)],
            ["BuildOrderSelectorAction", "BuildOrderSelectorUnpause"],
        )
        self.assertEqual(
            [button.get(f"{{{XAML_NS}}}Name") for button in editor.findall(".//p:Button", NS)],
            ["BuildOrderEditorSave", "BuildOrderEditorCancel"],
        )
        self.assertNotIn("DataTemplate", probe_xaml)

    def test_probe_creates_one_presenter_for_both_regions(self) -> None:
        self.assertEqual(self.source.count("UI_AddChild("), 1)
        create = function_body(self.source, "BuildOrderEditorUI_CreatePresenter")
        self.assertIn(
            'UI_AddChild("ScarDefault", "XamlPresenter", BUILD_ORDER_EDITOR_UI_SELECTOR_NAME',
            create,
        )
        self.assertIn("IsHitTestVisible = true", create)
        self.assertIn("Xaml = BUILD_ORDER_EDITOR_UI_PROBE_XAML", create)
        self.assertIn("DataContext", create)
        ensure = function_body(self.source, "BuildOrderEditorUI_EnsureCreated")
        self.assertIn("if BUILD_ORDER_EDITOR_UI_STATE.created then", ensure)
        self.assertIn("pcall(BuildOrderEditorUI_CreatePresenter)", ensure)
        self.assertRegex(ensure, r"if not success then[\s\S]*?return false")
        self.assertIn("return true", ensure)

    def test_probe_lifecycle_shows_editor_by_updating_the_existing_presenter(self) -> None:
        runtime = ScarRuntime(strip_xaml(self.source))
        additions = []
        removals = []
        updates = []
        runtime.globals["print"] = lambda _message: None
        runtime.globals["UI_CreateCommand"] = lambda name: f"command:{name}"
        runtime.globals["UI_CreateDataContext"] = lambda value: value
        runtime.globals["UI_AddChild"] = (
            lambda parent, kind, name, properties: additions.append(
                (parent, kind, name, properties)
            )
        )
        runtime.globals["UI_SetDataContext"] = (
            lambda name, value: updates.append((name, value))
        )
        runtime.globals["UI_Remove"] = lambda name: removals.append(name)

        def lua_pcall(function, *arguments):
            try:
                result = function(*arguments)
            except Exception as error:
                return LuaResults((False, str(error)))
            return LuaResults((True, result))

        runtime.globals["pcall"] = lua_pcall
        runtime.call(
            "BuildOrderEditorUI_SetCallbacks",
            {
                "select": "SelectCallback",
                "create": "CreateCallback",
                "edit": "EditCallback",
                "action": "ActionCallback",
                "unpause": "UnpauseCallback",
            },
        )
        self.assertTrue(
            runtime.call(
                "BuildOrderEditorUI_ShowSelector",
                {
                    "orders": [
                        {
                            "id": "__new_build_order__",
                            "label": "New Build Order",
                            "editable": False,
                            "selected": True,
                        }
                    ]
                },
            )
        )
        self.assertEqual([addition[2] for addition in additions], ["BuildOrderSelectorUI"])
        selector_context = additions[0][3]["DataContext"]
        self.assertEqual(selector_context["selected_option"]["label"], "New Build Order")
        self.assertEqual(selector_context["selected_index"], 0)
        self.assertEqual(selector_context["action_label"], "Create")
        self.assertEqual(
            selector_context["commands"]["action"], "command:ActionCallback"
        )

        runtime.call("BuildOrderEditorUI_SetCallbacks", {"cancel": "CancelCallback"})
        self.assertTrue(runtime.call("BuildOrderEditorUI_ShowEditor", {}))
        self.assertEqual([addition[2] for addition in additions], ["BuildOrderSelectorUI"])
        self.assertEqual(removals, [])
        self.assertEqual(updates[-1][0], "BuildOrderSelectorUI")
        self.assertEqual(updates[-1][1]["selector_visibility"], "Visible")
        self.assertEqual(updates[-1][1]["editor_visibility"], "Visible")
        self.assertEqual(
            updates[-1][1]["commands"]["cancel"], "command:CancelCallback"
        )

        self.assertTrue(runtime.call("BuildOrderEditorUI_Hide"))
        self.assertEqual(removals, [])
        self.assertEqual(
            runtime.globals["BUILD_ORDER_EDITOR_UI_STATE"]["screen"], "selector"
        )

    def test_probe_view_model_switches_create_and_edit_for_selected_option(self) -> None:
        runtime = ScarRuntime(strip_xaml(self.source))
        state = runtime.globals["BUILD_ORDER_EDITOR_UI_STATE"]
        state["commands"] = runtime.table(
            {
                "select": "select-command",
                "create": "create-command",
                "edit": "edit-command",
                "unpause": "unpause-command",
                "cancel": "cancel-command",
            }
        )
        model = {
            "orders": [
                {
                    "id": "__new_build_order__",
                    "label": "New Build Order",
                    "editable": False,
                    "selected": True,
                },
                {
                    "id": "english-opening",
                    "label": "English Opening",
                    "editable": True,
                    "selected": False,
                },
            ]
        }

        view = runtime.call("BuildOrderEditorUI_BuildProbeViewModel", "selector", model)
        self.assertEqual(view["selected_option"]["id"], "__new_build_order__")
        self.assertEqual(view["selected_index"], 0)
        self.assertEqual(view["action_label"], "Create")

        model["orders"][0]["selected"] = False
        model["orders"][1]["selected"] = True
        view = runtime.call("BuildOrderEditorUI_BuildProbeViewModel", "selector", model)
        self.assertEqual(view["selected_option"]["id"], "english-opening")
        self.assertEqual(view["selected_index"], 1)
        self.assertEqual(view["action_label"], "Edit")

        editor = runtime.call("BuildOrderEditorUI_BuildProbeViewModel", "editor", {})
        self.assertEqual(editor["selector_visibility"], "Visible")
        self.assertEqual(editor["editor_visibility"], "Visible")
        self.assertFalse(editor["save_enabled"])

    def test_callbacks_are_commands_but_ui_does_not_mutate_the_draft(self) -> None:
        create = function_body(self.source, "BuildOrderEditorUI_CreateCommands")
        for callback in (
            "select",
            "create",
            "edit",
            "copy",
            "save",
            "cancel",
            "unpause",
            "confirm_unpause",
            "field_change",
            "add",
            "add_check",
            "delete",
            "expand",
            "collapse",
            "reorder",
        ):
            with self.subTest(callback=callback):
                self.assertIn(f'BuildOrderEditorUI_CommandName("{callback}")', create)
        self.assertIn("UI_CreateCommand(", create)
        self.assertNotIn("BuildOrderEditor_Move(", self.source)

        set_callbacks = function_body(self.source, "BuildOrderEditorUI_SetCallbacks")
        self.assertNotIn("BuildOrderEditorUI_RefreshProbe", set_callbacks)

    def test_editor_is_one_scrollable_column_with_a_sticky_action_header(self) -> None:
        editor = named(self.xaml_root, "BuildOrderEditorScreen")
        self.assertEqual(editor.tag, f"{{{PRESENTATION_NS}}}Grid")
        header = named(editor, "BuildOrderEditorActionHeader")
        self.assertIsNotNone(named(header, "BuildOrderCurrentCivilization"))
        self.assertIsNotNone(named(header, "BuildOrderTitleEditor"))
        header_xml = ET.tostring(header, encoding="unicode")
        self.assertIn("RaceIconSecondary", header_xml)
        for loc_id in (38, 39, 40):
            self.assertIn(f'Content="${MOD_NAMESPACE}:{loc_id}"', header_xml)
        scroll = named(editor, "BuildOrderEditorScroll")
        self.assertEqual(scroll.tag, f"{{{PRESENTATION_NS}}}ScrollViewer")
        columns = editor.findall("./p:Grid.ColumnDefinitions", NS)
        self.assertEqual(columns, [])
        self.assertNotIn("Sidebar", self.xaml)
        self.assertNotIn("sidebar", self.xaml)

    def test_step_cards_contain_expandable_reorderable_check_cards(self) -> None:
        step_template = named(self.xaml_root, "BuildOrderStepCardTemplate")
        check_template = named(self.xaml_root, "BuildOrderCheckCardTemplate")
        self.assertIsNotNone(step_template.find(".//p:Expander", NS))
        self.assertIsNotNone(check_template.find(".//p:Expander", NS))
        nested_checks = next(
            element
            for element in step_template.findall(".//p:ItemsControl", NS)
            if element.get("ItemsSource") == "{Binding [checks]}"
        )
        self.assertEqual(
            nested_checks.get("ItemTemplate"),
            "{StaticResource BuildOrderCheckCardTemplate}",
        )
        for loc_id in (
            71,
            67,
            70,
            69,
            42,
            72,
            68,
        ):
            token = f"${MOD_NAMESPACE}:{loc_id}"
            with self.subTest(loc_id=loc_id):
                self.assertIn(token, self.xaml)
        self.assertIn("[errors]", self.xaml)
        self.assertIn(
            'ItemsSource="{Binding [flat_fields]}"',
            ET.tostring(step_template, encoding="unicode"),
        )

    def test_pointer_reorder_uses_all_three_routed_events_and_command_parameters(self) -> None:
        for event in (
            "UIElement.PreviewMouseLeftButtonDown",
            "UIElement.MouseEnter",
            "UIElement.PreviewMouseLeftButtonUp",
        ):
            with self.subTest(event=event):
                self.assertIn(f'RoutedEvent="{event}"', self.xaml)
        self.assertGreaterEqual(self.xaml.count("esActions:CallCommandAction"), 3)
        self.assertGreaterEqual(self.xaml.count("CommandParameter=\"{Binding}\""), 3)

        for template_name, handle_name in (
            ("BuildOrderStepCardTemplate", "BuildOrderStepDragHandle"),
            ("BuildOrderCheckCardTemplate", "BuildOrderCheckDragHandle"),
        ):
            with self.subTest(handle=handle_name):
                handle = named(named(self.xaml_root, template_name), handle_name)
                self.assertEqual(handle.tag, f"{{{PRESENTATION_NS}}}Border")

        for template_name in (
            "BuildOrderStepCardTemplate",
            "BuildOrderCheckCardTemplate",
        ):
            with self.subTest(leave_target=template_name):
                template_xml = ET.tostring(
                    named(self.xaml_root, template_name), encoding="unicode"
                )
                self.assertIn('RoutedEvent="UIElement.MouseLeave"', template_xml)
                self.assertIn("[drag_target_leave_command]", template_xml)
        editor_xml = ET.tostring(
            named(self.xaml_root, "BuildOrderEditorScreen"), encoding="unicode"
        )
        self.assertIn('RoutedEvent="UIElement.MouseLeave"', editor_xml)
        self.assertIn("[commands][drag_cancel]", editor_xml)

        begin = function_body(self.source, "BuildOrderEditorUI_BeginDrag")
        target = function_body(self.source, "BuildOrderEditorUI_UpdateDragTarget")
        commit = function_body(self.source, "BuildOrderEditorUI_CommitDrag")
        self.assertIn("drag_source_path = path", begin)
        self.assertIn("BuildOrderEditorUI_AreCompatiblePaths", target)
        self.assertIn("drag_target_path = path", target)
        self.assertIn("BUILD_ORDER_EDITOR_UI_STATE.draggable_paths[sourcePath]", commit)
        self.assertIn("BUILD_ORDER_EDITOR_UI_STATE.draggable_paths[targetPath]", commit)
        self.assertRegex(
            commit, r'BuildOrderEditorUI_InvokeCallback\(\s*"reorder"'
        )
        self.assertIn("BuildOrderEditorUI_ClearDrag()", commit)

    def test_current_civilization_is_read_only_and_uses_the_cardinal_hud_flag(self) -> None:
        self.assertIn(
            "{Binding DataContext.LocalPlayer.RaceIconSecondary, RelativeSource={RelativeSource AncestorType={x:Type pages:CardinalHUDPage}}}",
            self.xaml,
        )
        civ = named(self.xaml_root, "BuildOrderCurrentCivilization")
        self.assertEqual(civ.tag, f"{{{PRESENTATION_NS}}}TextBlock")
        self.assertEqual(civ.get("Text"), "{Binding [current_civ]}")
        self.assertNotIn('SelectedValue="{Binding [current_civ]', self.xaml)
        self.assertNotIn("civ_dropdown", self.source.lower())

    def test_resource_cards_show_four_optional_positive_inputs_and_separate_no_collect(self) -> None:
        resource_template = named(self.xaml_root, "BuildOrderResourceFieldsTemplate")
        resource_xml = ET.tostring(resource_template, encoding="unicode")
        for resource, loc_id in (
            ("food", 62),
            ("wood", 63),
            ("gold", 64),
            ("stone", 65),
        ):
            with self.subTest(resource=resource):
                self.assertIn(f"[{resource}][display_value]", resource_xml)
                self.assertIn(
                    f'Content="${MOD_NAMESPACE}:{loc_id}"', resource_xml
                )
        self.assertIn(f"${MOD_NAMESPACE}:61", resource_xml)
        self.assertIn("[no_collect]", resource_xml)
        self.assertIn(f"${MOD_NAMESPACE}:66", resource_xml)

    def test_live_options_render_label_icon_and_internal_id_fallback(self) -> None:
        option_template = named(self.xaml_root, "BuildOrderLiveOptionTemplate")
        option_xml = ET.tostring(option_template, encoding="unicode")
        self.assertIn("[label]", option_xml)
        self.assertIn("[icon]", option_xml)
        self.assertIn("[id_fallback]", option_xml)
        self.assertIn(f"${MOD_NAMESPACE}:58", self.xaml)

    def test_each_step_has_a_schema_populated_check_kind_chooser(self) -> None:
        step = named(self.xaml_root, "BuildOrderStepCardTemplate")
        chooser = named(step, "BuildOrderCheckKindChooser")
        combo = named(chooser, "BuildOrderCheckKindOptions")
        self.assertEqual(combo.get("ItemsSource"), "{Binding [options]}")
        self.assertEqual(
            combo.get("SelectedItem"),
            "{Binding [selected_option], Mode=TwoWay}",
        )
        add = named(chooser, "BuildOrderAddCheck")
        self.assertEqual(add.get("Command"), "{Binding [add_check_command]}")
        self.assertEqual(add.get("CommandParameter"), "{Binding}")
        self.assertIn(f"${MOD_NAMESPACE}:43", ET.tostring(chooser, encoding="unicode"))

    def test_static_xaml_labels_use_stable_fully_qualified_localization(self) -> None:
        rows = csv_rows(LOCDB_PATH)
        seen = set()
        for element in self.xaml_root.iter():
            for attribute in ("Text", "Content"):
                value = element.get(attribute)
                if value is None or value.startswith("{"):
                    continue
                match = re.fullmatch(rf"\${MOD_NAMESPACE}:(\d+)", value)
                self.assertIsNotNone(
                    match,
                    f"unlocalized static {attribute}={value!r}",
                )
                seen.add(int(match.group(1)))
        self.assertTrue(seen)
        self.assertTrue(seen.issubset(rows))

    def test_dynamic_validation_template_renders_localized_label_and_message_separately(self) -> None:
        template = named(self.xaml_root, "BuildOrderValidationMessageTemplate")
        text_blocks = list(template.iter(f"{{{PRESENTATION_NS}}}TextBlock"))
        self.assertEqual(
            [block.get("Text") for block in text_blocks],
            ["{Binding [label]}", "{Binding [message]}"],
        )

    def test_invalid_draft_disables_save(self) -> None:
        header = named(self.xaml_root, "BuildOrderEditorActionHeader")
        save = next(
            element
            for element in header.iter()
            if element.tag == f"{{{PRESENTATION_NS}}}Button"
            and element.get("Content") == f"${MOD_NAMESPACE}:38"
        )
        self.assertEqual(save.get("IsEnabled"), "{Binding [save_enabled]}")


class BuildOrderEditorUIProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        ui_source = UI_SCAR.read_text(encoding="utf-8")
        cls.xaml_root = ET.fromstring(extract_xaml(ui_source))
        cls.runtime = ScarRuntime(
            MODEL_SCAR.read_text(encoding="utf-8")
            + "\n"
            + SCHEMA_SCAR.read_text(encoding="utf-8")
            + "\n"
            + strip_xaml(ui_source)
        )

    def configure_reorder_callback(self):
        calls = []
        globals_table = self.runtime.table({})
        globals_table["BuildOrderEditorUITest_RecordReorder"] = (
            lambda parent_path, from_index, to_index: calls.append(
                (parent_path, from_index, to_index)
            )
        )
        self.runtime.globals["_G"] = globals_table
        state = self.runtime.globals["BUILD_ORDER_EDITOR_UI_STATE"]
        state["callbacks"] = self.runtime.table(
            {"reorder": "BuildOrderEditorUITest_RecordReorder"}
        )
        state["draggable_paths"] = self.runtime.table(
            {
                "steps.1": {
                    "parent_path": "steps",
                    "index": 1,
                    "max_index": 2,
                    "card_kind": "step",
                },
                "steps.2": {
                    "parent_path": "steps",
                    "index": 2,
                    "max_index": 2,
                    "card_kind": "step",
                },
            }
        )
        self.runtime.call("BuildOrderEditorUI_ClearDrag")
        return state, calls

    def test_nested_objects_and_object_list_entries_project_and_render_recursively(
        self,
    ) -> None:
        schema = {
            "node_type": "object",
            "label": "Root",
            "fields": [
                {
                    "key": "settings",
                    "node_type": "object",
                    "label": "Settings",
                    "fields": [
                        {
                            "key": "name",
                            "node_type": "primitive",
                            "label": "Name",
                            "value_type": "string",
                            "required": True,
                        },
                        {
                            "key": "advanced",
                            "node_type": "object",
                            "label": "Advanced",
                            "fields": [
                                {
                                    "key": "note",
                                    "node_type": "primitive",
                                    "label": "Note",
                                    "value_type": "string",
                                    "required": False,
                                }
                            ],
                        },
                    ],
                },
                {
                    "key": "groups",
                    "node_type": "list",
                    "label": "Groups",
                    "min_items": 0,
                    "item": {
                        "node_type": "object",
                        "label": "Group",
                        "fields": [
                            {
                                "key": "name",
                                "node_type": "primitive",
                                "label": "Name",
                                "value_type": "string",
                                "required": True,
                            }
                        ],
                    },
                },
            ],
        }
        draft = {
            "settings": {"name": "Default", "advanced": {"note": "Careful"}},
            "groups": [{"name": "First"}],
        }
        root = self.runtime.call(
            "BuildOrderEditorUI_ProjectDraft",
            draft,
            [],
            None,
            {"settings": False, "groups.1": False},
            schema,
        )

        settings = find_view_node(root, "settings")
        self.assertEqual(settings["node_type"], "object")
        self.assertEqual(settings["object_visibility"], "Visible")
        self.assertFalse(settings["expanded"])
        self.assertEqual(
            find_view_node(root, "settings.advanced")["path"], "settings.advanced"
        )
        self.assertEqual(
            find_view_node(root, "settings.advanced.note")["value"], "Careful"
        )

        group = find_view_node(root, "groups.1")
        self.assertEqual(group["node_type"], "object")
        self.assertEqual(group["object_visibility"], "Visible")
        self.assertFalse(group["expanded"])
        self.assertEqual(find_view_node(root, "groups.1.name")["value"], "First")

        flat_fields = self.runtime.table([])
        self.runtime.call("BuildOrderEditorUI_CollectFlatFields", root, flat_fields)
        self.assertEqual(
            [field["path"] for field in flat_fields.array()],
            ["settings", "groups"],
        )

        object_template = named(self.xaml_root, "BuildOrderObjectCardTemplate")
        object_xml = ET.tostring(object_template, encoding="unicode")
        self.assertIn('IsExpanded="{Binding [expanded], Mode=OneWay}"', object_xml)
        self.assertIn('ItemsSource="{Binding [fields]}"', object_xml)
        self.assertIn(
            'ItemTemplate="{DynamicResource BuildOrderFieldTemplate}"', object_xml
        )

        list_item_template = named(self.xaml_root, "BuildOrderListItemTemplate")
        list_item_xml = ET.tostring(list_item_template, encoding="unicode")
        self.assertIn('Content="{Binding}"', list_item_xml)
        self.assertIn(
            'ContentTemplate="{DynamicResource BuildOrderFieldTemplate}"',
            list_item_xml,
        )

        field_template = named(self.xaml_root, "BuildOrderFieldTemplate")
        field_xml = ET.tostring(field_template, encoding="unicode")
        self.assertIn("[object_visibility]", field_xml)
        self.assertIn("BuildOrderObjectCardTemplate", field_xml)
        self.assertIn('ItemsSource="{Binding [items]}"', field_xml)

    def test_recursive_projection_uses_stable_paths_expansion_and_exact_errors(self) -> None:
        draft = {
            "civ": "english",
            "title": "Feudal pressure",
            "steps": [
                {
                    "title": "Opening",
                    "inferred_age": 1,
                    "checks": [
                        {
                            "kind": "vils",
                            "optional": False,
                            "payload": {"food": 7, "no_collect": ["gold"]},
                        },
                        {
                            "kind": "built",
                            "optional": False,
                            "payload": {
                                "alternatives": ["building_barracks_eng"],
                                "count": 0,
                            },
                        },
                    ],
                }
            ],
        }
        errors = [
            {
                "path": "steps.1.checks.2.payload.count",
                "message": "must be a positive integer",
            }
        ]
        discovery = {
            "buildings": [
                {
                    "id": "building_barracks_eng",
                    "kind": "building",
                    "age": 1,
                    "label": "Barracks",
                    "icon": "barracks-icon",
                }
            ],
            "squads": [],
            "technologies": [],
            "age_ups": [],
            "families": [],
        }
        root = self.runtime.call(
            "BuildOrderEditorUI_ProjectDraft",
            draft,
            errors,
            discovery,
            {"steps.1": False},
        )

        step = find_view_node(root, "steps.1")
        self.assertEqual(step["node_type"], "object")
        self.assertFalse(step["expanded"])
        self.assertEqual(step["inferred_age"], 1)
        self.assertEqual(step["age_label"], f"${MOD_NAMESPACE}:110")
        self.assertEqual(step["age_number"], 1)
        self.assertEqual(len(step["flat_fields"]), 1)
        self.assertEqual(step["flat_fields"][1]["path"], "steps.1.title")
        check = find_view_node(root, "steps.1.checks.2")
        self.assertEqual(check["label"], f"${MOD_NAMESPACE}:75")
        self.assertEqual(check["kind"], "built")
        count = find_view_node(root, "steps.1.checks.2.payload.count")
        self.assertEqual(count["errors"].array(), [f"${MOD_NAMESPACE}:111"])

        alternative = find_view_node(
            root, "steps.1.checks.2.payload.alternatives.1"
        )
        option = alternative["options"][1]
        self.assertEqual(option["label"], "Barracks")
        self.assertEqual(option["icon"], "barracks-icon")
        self.assertEqual(option["id_fallback"], "building_barracks_eng")

    def test_resource_projection_keeps_all_four_inputs_and_no_collect_separate(self) -> None:
        draft = {
            "civ": "english",
            "title": "Economy",
            "steps": [
                {
                    "title": "Opening",
                    "inferred_age": 1,
                    "checks": [
                        {
                            "kind": "vils",
                            "optional": False,
                            "payload": {"food": 7, "no_collect": ["stone"]},
                        }
                    ],
                }
            ],
        }
        root = self.runtime.call(
            "BuildOrderEditorUI_ProjectDraft", draft, [], None, {}
        )
        expected = {
            "food": 7,
            "wood": None,
            "gold": None,
            "stone": None,
        }
        for resource, value in expected.items():
            node = find_view_node(
                root, f"steps.1.checks.1.payload.{resource}"
            )
            self.assertEqual(node["value"], value)
            self.assertTrue(node["optional"])
            self.assertTrue(node["inline_optional"])
        no_collect = find_view_node(
            root, "steps.1.checks.1.payload.no_collect"
        )
        self.assertEqual(no_collect["node_type"], "list")
        self.assertTrue(no_collect["is_no_collect"])
        self.assertEqual(no_collect["items"][1]["value"], "stone")

        check = find_view_node(root, "steps.1.checks.1")
        self.assertEqual(len(check["resource_groups"]), 1)
        resource_group = check["resource_groups"][1]
        for resource in ("food", "wood", "gold", "stone"):
            self.assertEqual(
                resource_group[resource]["path"],
                f"steps.1.checks.1.payload.{resource}",
            )
        self.assertEqual(resource_group["no_collect"]["path"], no_collect["path"])

    def test_entering_an_incompatible_card_clears_a_previous_drag_target(self) -> None:
        state = self.runtime.globals["BUILD_ORDER_EDITOR_UI_STATE"]
        state["draggable_paths"] = self.runtime.table(
            {
                "steps.1": {
                    "parent_path": "steps",
                    "index": 1,
                    "card_kind": "step",
                },
                "steps.2": {
                    "parent_path": "steps",
                    "index": 2,
                    "card_kind": "step",
                },
                "steps.2.checks.1": {
                    "parent_path": "steps.2.checks",
                    "index": 1,
                    "card_kind": "check",
                },
            }
        )
        self.assertTrue(self.runtime.call("BuildOrderEditorUI_BeginDrag", "steps.1"))
        self.assertTrue(
            self.runtime.call("BuildOrderEditorUI_UpdateDragTarget", "steps.2")
        )
        self.assertEqual(state["drag_target_path"], "steps.2")
        self.assertFalse(
            self.runtime.call(
                "BuildOrderEditorUI_UpdateDragTarget", "steps.2.checks.1"
            )
        )
        self.assertIsNone(state["drag_target_path"])

    def test_compatible_hover_then_leave_cannot_commit_a_stale_target(self) -> None:
        state, calls = self.configure_reorder_callback()
        leave_target = self.runtime.globals.get(
            "BuildOrderEditorUI_LeaveDragTarget"
        )
        self.assertIsNotNone(leave_target)

        self.assertTrue(self.runtime.call("BuildOrderEditorUI_BeginDrag", "steps.1"))
        self.assertTrue(
            self.runtime.call("BuildOrderEditorUI_UpdateDragTarget", "steps.2")
        )
        self.assertTrue(
            self.runtime.call("BuildOrderEditorUI_LeaveDragTarget", "steps.2")
        )
        self.assertFalse(self.runtime.call("BuildOrderEditorUI_CommitDrag", None))
        self.assertIsNone(state["drag_source_path"])
        self.assertIsNone(state["drag_target_path"])
        self.assertEqual(calls, [])

    def test_commit_requires_target_to_still_be_actively_hovered(self) -> None:
        state, calls = self.configure_reorder_callback()
        self.assertTrue(self.runtime.call("BuildOrderEditorUI_BeginDrag", "steps.1"))
        self.assertTrue(
            self.runtime.call("BuildOrderEditorUI_UpdateDragTarget", "steps.2")
        )
        state["drag_target_active"] = False

        self.assertFalse(self.runtime.call("BuildOrderEditorUI_CommitDrag", None))
        self.assertEqual(calls, [])

    def test_leaving_editor_cancels_drag_before_external_mouse_up(self) -> None:
        state, calls = self.configure_reorder_callback()
        cancel_drag = self.runtime.globals.get("BuildOrderEditorUI_CancelDrag")
        self.assertIsNotNone(cancel_drag)

        self.assertTrue(self.runtime.call("BuildOrderEditorUI_BeginDrag", "steps.1"))
        self.assertTrue(
            self.runtime.call("BuildOrderEditorUI_UpdateDragTarget", "steps.2")
        )
        self.assertTrue(self.runtime.call("BuildOrderEditorUI_CancelDrag", None))
        self.assertFalse(self.runtime.call("BuildOrderEditorUI_CommitDrag", None))
        self.assertIsNone(state["drag_source_path"])
        self.assertIsNone(state["drag_target_path"])
        self.assertEqual(calls, [])

    def test_live_projection_keeps_an_unknown_saved_internal_id_as_a_fallback(self) -> None:
        draft = {
            "civ": "english",
            "title": "Legacy",
            "steps": [
                {
                    "title": "Opening",
                    "inferred_age": 1,
                    "checks": [
                        {
                            "kind": "built",
                            "optional": False,
                            "payload": {
                                "alternatives": ["legacy_building_eng"],
                                "count": 1,
                            },
                        }
                    ],
                }
            ],
        }
        discovery = {
            "buildings": [],
            "squads": [],
            "technologies": [],
            "age_ups": [],
            "families": [],
        }
        root = self.runtime.call(
            "BuildOrderEditorUI_ProjectDraft", draft, [], discovery, {}
        )
        field = find_view_node(
            root, "steps.1.checks.1.payload.alternatives.1"
        )
        self.assertEqual(len(field["options"]), 1)
        fallback = field["options"][1]
        self.assertEqual(fallback["id"], "legacy_building_eng")
        self.assertEqual(fallback["label"], "legacy_building_eng")
        self.assertEqual(fallback["id_fallback"], "legacy_building_eng")
        self.assertEqual(fallback["icon"], "")
        self.assertTrue(fallback["selected"])
        self.assertTrue(fallback["is_fallback"])
        self.assertEqual(field["live_candidate_count"], 0)
        self.assertEqual(field["empty_options_visibility"], "Visible")

    def test_empty_live_discovery_projects_an_explicit_empty_state(self) -> None:
        draft = {
            "civ": "english",
            "title": "Technology",
            "steps": [
                {
                    "title": "Opening",
                    "inferred_age": 1,
                    "checks": [
                        {
                            "kind": "upgrades",
                            "optional": False,
                            "payload": {"queued": False},
                        }
                    ],
                }
            ],
        }
        discovery = {
            "buildings": [],
            "squads": [],
            "technologies": [],
            "age_ups": [],
            "families": [],
        }
        root = self.runtime.call(
            "BuildOrderEditorUI_ProjectDraft", draft, [], discovery, {}
        )
        field = find_view_node(root, "steps.1.checks.1.payload.id")
        self.assertEqual(len(field["options"]), 0)
        self.assertEqual(field["empty_options_visibility"], "Visible")

    def test_age_up_live_options_are_exactly_the_inferred_next_age(self) -> None:
        context = {
            "civ": "english",
            "current_age": 2,
            "discovery": {
                "buildings": [],
                "technologies": [
                    {
                        "id": "ordinary_technology",
                        "kind": "technology",
                        "age": 3,
                        "label": "Ordinary technology",
                        "icon": "tech",
                    }
                ],
                "age_ups": [
                    {"id": "prior_age", "kind": "age_up", "age": 1},
                    {"id": "current_age", "kind": "age_up", "age": 2},
                    {"id": "next_age", "kind": "age_up", "age": 3},
                    {"id": "future_age", "kind": "age_up", "age": 4},
                ],
                "squads": [],
                "families": [],
            },
        }

        options = self.runtime.call(
            "BuildOrderEditorUI_LiveOptions",
            "live_age_up",
            None,
            "steps.1.checks.1.payload.alternatives.1",
            context,
        )

        self.assertEqual(
            [option["id"] for option in options.array()],
            ["next_age"],
        )

    def test_family_option_value_retains_label_icon_and_canonical_ids(self) -> None:
        option = self.runtime.call(
            "BuildOrderEditorUI_NormalizeOption",
            {
                "ids": ["unit_spearman_1_eng", "unit_spearman_2_eng"],
                "kind": "family",
                "label": "Spearman",
                "icon": "unit_spearman",
            },
            "steps.1.checks.1.payload.family",
            {},
        )

        self.assertEqual(option["value"]["label"], "Spearman")
        self.assertEqual(option["value"]["icon"], "unit_spearman")
        self.assertEqual(
            option["value"]["ids"].array(),
            ["unit_spearman_1_eng", "unit_spearman_2_eng"],
        )

    def test_validation_messages_use_friendly_localized_labels_instead_of_internal_paths(self) -> None:
        messages = self.runtime.call(
            "BuildOrderEditorUI_ValidationMessages",
            [
                {
                    "path": "steps.1.checks.2.payload.count",
                    "message": "must be a positive integer",
                }
            ],
        )

        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[1]["label"], f"${MOD_NAMESPACE}:94")
        self.assertEqual(messages[1]["message"], f"${MOD_NAMESPACE}:111")

    def test_validation_paths_use_explicit_semantic_field_labels(self) -> None:
        cases = (
            ("age_up", 97),
            ("assignments", 90),
            ("building", 92),
            ("buildings", 93),
            ("builders", 95),
            ("choice", 99),
            ("choices", 98),
            ("civ", 85),
            ("civilization", 85),
            ("title", 86),
            ("steps", 87),
            ("steps.1.checks", 89),
            ("steps.1.checks.1.kind", 107),
            ("steps.1.checks.1.payload", 142),
            ("steps.1.checks.1.optional", 83),
            ("steps.1.checks.1.payload.alternatives", 98),
            ("steps.1.checks.1.payload.alternatives.1", 98),
            ("steps.1.checks.1.payload.id", 99),
            ("steps.1.checks.1.payload.family", 102),
            ("steps.1.checks.1.payload.queued", 101),
            ("steps.1.checks.1.payload.constant", 103),
            ("steps.1.checks.1.payload.vils", 95),
            ("steps.1.checks.1.payload.location", 96),
            ("steps.1.checks.1.payload.count", 94),
            ("steps.1.checks.1.payload.entering_age", 110),
            ("steps.1.checks.1.payload.food", 62),
            ("steps.1.checks.1.payload.wood", 63),
            ("steps.1.checks.1.payload.gold", 64),
            ("steps.1.checks.1.payload.stone", 65),
            ("steps.1.checks.1.payload.no_collect", 66),
            ("steps.1.checks.1.payload.resource", 91),
            ("steps.1.checks.1.payload.text", 106),
            ("steps.1.checks.1.payload.hint", 105),
            ("steps.1.checks.1.payload.rallypoint", 74),
            ("steps.1.checks.1.payload.resources", 104),
            ("steps.1.checks.1.payload.technology", 100),
            ("steps.1.checks.1.payload.unit_family", 102),
            ("steps.1.checks.1.payload.inferred_age", 110),
        )

        for path, loc_id in cases:
            with self.subTest(path=path):
                self.assertEqual(
                    self.runtime.call("BuildOrderEditorUI_FriendlyErrorLabel", path),
                    f"${MOD_NAMESPACE}:{loc_id}",
                )

    def test_unknown_projection_labels_are_stable_localization_ids(self) -> None:
        unknown_check = self.runtime.call(
            "BuildOrderEditorUI_ProjectVariant",
            {"discriminator": "kind", "variants": {}},
            {"kind": "retired"},
            "steps.1.checks.1",
            {"error_map": {}, "expanded": {}},
        )
        unknown_field = self.runtime.call(
            "BuildOrderEditorUI_ProjectNode",
            None,
            None,
            "unexpected",
            {"error_map": {}, "expanded": {}},
        )

        self.assertEqual(unknown_check["label"], f"${MOD_NAMESPACE}:108")
        self.assertEqual(unknown_field["label"], f"${MOD_NAMESPACE}:109")

    def test_schema_labels_and_error_mappings_use_stable_localization_ids(self) -> None:
        labels = self.runtime.globals["BUILD_ORDER_EDITOR_FIELD_LABELS"]
        errors = self.runtime.globals["BUILD_ORDER_EDITOR_ERROR_LABELS"]
        rows = csv_rows(LOCDB_PATH)

        self.assertEqual(labels["build_order"], f"${MOD_NAMESPACE}:84")
        self.assertEqual(labels["assignments"], f"${MOD_NAMESPACE}:90")
        self.assertEqual(labels["count"], f"${MOD_NAMESPACE}:94")
        self.assertEqual(labels["entering_age"], f"${MOD_NAMESPACE}:110")
        self.assertEqual(labels["check_details"], f"${MOD_NAMESPACE}:142")
        self.assertEqual(
            errors["must contain a title that can form an ID"],
            f"${MOD_NAMESPACE}:133",
        )
        self.assertEqual(errors["id_collision"], f"${MOD_NAMESPACE}:140")
        self.assertEqual(errors["persistence_error"], f"${MOD_NAMESPACE}:141")
        self.assertEqual(rows[110][6], "Entering age")
        self.assertEqual(rows[141][6], "The build order could not be saved.")

    def test_editor_view_disables_save_while_errors_exist(self) -> None:
        model = {
            "draft": {
                "civ": "english",
                "title": "Invalid",
                "steps": [],
            },
            "errors": [{"path": "steps", "message": "is required"}],
        }
        view = self.runtime.call(
            "BuildOrderEditorUI_BuildViewModel", "editor", model
        )
        self.assertFalse(view["save_enabled"])

        model["errors"] = []
        view = self.runtime.call(
            "BuildOrderEditorUI_BuildViewModel", "editor", model
        )
        self.assertTrue(view["save_enabled"])

    def test_projected_check_kind_options_use_stable_localized_labels(self) -> None:
        state = self.runtime.globals["BUILD_ORDER_EDITOR_UI_STATE"]
        state["commands"] = self.runtime.table(
            {"add_check": "add-check-command"}
        )
        model = {
            "draft": {
                "civ": "english",
                "title": "Kinds",
                "steps": [
                    {
                        "title": "Opening",
                        "inferred_age": 1,
                        "checks": [
                            {
                                "kind": "hints",
                                "optional": True,
                                "payload": {"text": "Start"},
                            }
                        ],
                    }
                ],
            },
            "errors": [],
            "discovery": {
                "buildings": [],
                "squads": [],
                "technologies": [],
                "age_ups": [],
                "families": [],
            },
        }

        view = self.runtime.call(
            "BuildOrderEditorUI_BuildViewModel", "editor", model
        )
        add_check = view["steps"][1]["check_add"]
        self.assertIsNotNone(add_check)
        self.assertEqual(add_check["path"], "steps.1.checks")
        self.assertEqual(add_check["add_check_command"], "add-check-command")
        self.assertEqual(
            [
                (option["id"], option["label"])
                for option in add_check["options"].array()
            ],
            [
                ("vils", f"${MOD_NAMESPACE}:73"),
                ("rallypoint", f"${MOD_NAMESPACE}:74"),
                ("built", f"${MOD_NAMESPACE}:75"),
                ("age_up", f"${MOD_NAMESPACE}:76"),
                ("upgrades", f"${MOD_NAMESPACE}:77"),
                ("produce", f"${MOD_NAMESPACE}:78"),
                ("resources", f"${MOD_NAMESPACE}:79"),
                ("buildings", f"${MOD_NAMESPACE}:80"),
                ("units", f"${MOD_NAMESPACE}:81"),
                ("hints", f"${MOD_NAMESPACE}:82"),
            ],
        )
        self.assertEqual(add_check["selected_option"]["id"], "vils")
        rows = csv_rows(LOCDB_PATH)
        self.assertEqual(
            [rows[loc_id][6] for loc_id in range(73, 83)],
            [
                "Villagers",
                "Rally point",
                "Build",
                "Age up",
                "Technology",
                "Produce",
                "Resources",
                "Existing buildings",
                "Existing units",
                "Hint",
            ],
        )

    def test_projected_optional_field_uses_stable_localized_label(self) -> None:
        draft = {
            "civ": "english",
            "title": "Technology",
            "steps": [
                {
                    "title": "Opening",
                    "inferred_age": 1,
                    "checks": [
                        {
                            "kind": "upgrades",
                            "optional": False,
                            "payload": {"id": "", "queued": False},
                        }
                    ],
                }
            ],
        }
        discovery = {
            "buildings": [],
            "squads": [],
            "technologies": [],
            "age_ups": [],
            "families": [],
        }

        root = self.runtime.call(
            "BuildOrderEditorUI_ProjectDraft", draft, [], discovery, {}
        )
        optional = find_view_node(root, "steps.1.checks.1.optional")

        self.assertEqual(optional["label"], f"${MOD_NAMESPACE}:83")
        self.assertEqual(csv_rows(LOCDB_PATH)[83][6], "Optional")


if __name__ == "__main__":
    unittest.main()
