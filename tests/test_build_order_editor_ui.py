import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from tests.scar_runtime import ScarRuntime


ROOT = Path(__file__).resolve().parents[1]
UI_SCAR = ROOT / "assets" / "scar" / "build_orders" / "editor_ui.scar"
MODEL_SCAR = ROOT / "assets" / "scar" / "build_orders" / "editor_model.scar"
SCHEMA_SCAR = ROOT / "assets" / "scar" / "build_orders" / "editor_schema.scar"

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


def extract_xaml(source: str) -> str:
    match = re.search(
        r"BUILD_ORDER_EDITOR_UI_XAML\s*=\s*\[\[(.*?)\]\]",
        source,
        flags=re.DOTALL,
    )
    if match is None:
        raise AssertionError("missing BUILD_ORDER_EDITOR_UI_XAML")
    return match.group(1)


def named(root: ET.Element, name: str) -> ET.Element:
    keys = (f"{{{XAML_NS}}}Name", f"{{{XAML_NS}}}Key")
    for element in root.iter():
        if any(element.get(key) == name for key in keys):
            return element
    raise AssertionError(f"missing x:Name/x:Key={name}")


def strip_xaml(source: str) -> str:
    return re.sub(
        r"BUILD_ORDER_EDITOR_UI_XAML\s*=\s*\[\[.*?\]\]",
        'BUILD_ORDER_EDITOR_UI_XAML = ""',
        source,
        flags=re.DOTALL,
    )


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

    def test_one_presenter_is_created_under_scar_default_with_failure_fallback(self) -> None:
        self.assertEqual(self.source.count("UI_AddChild("), 1)
        create = function_body(self.source, "BuildOrderEditorUI_CreatePresenter")
        self.assertIn(
            'UI_AddChild("ScarDefault", "XamlPresenter", BUILD_ORDER_EDITOR_UI_NAME',
            create,
        )
        self.assertIn("IsHitTestVisible = true", create)
        self.assertIn("Xaml = BUILD_ORDER_EDITOR_UI_XAML", create)
        self.assertIn("DataContext = UI_CreateDataContext(", create)

        ensure = function_body(self.source, "BuildOrderEditorUI_EnsureCreated")
        self.assertIn("if BUILD_ORDER_EDITOR_UI_STATE.created then", ensure)
        self.assertIn("pcall(BuildOrderEditorUI_CreatePresenter)", ensure)
        self.assertRegex(ensure, r"if not success then[\s\S]*?return false")
        self.assertIn("return true", ensure)

    def test_one_bound_model_switches_all_four_screens(self) -> None:
        for name, screen in (
            ("BuildOrderEditorUI_ShowSelector", "selector"),
            ("BuildOrderEditorUI_ShowEditor", "editor"),
            ("BuildOrderEditorUI_ShowNoSelectionConfirmation", "confirmation"),
            ("BuildOrderEditorUI_Hide", "hidden"),
        ):
            with self.subTest(name=name):
                body = function_body(self.source, name)
                self.assertIn(f'BuildOrderEditorUI_SetScreen("{screen}"', body)
        refresh = function_body(self.source, "BuildOrderEditorUI_Refresh")
        self.assertIn("UI_SetDataContext(BUILD_ORDER_EDITOR_UI_NAME", refresh)

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
        self.assertRegex(
            set_callbacks,
            r"commands = nil[\s\S]*?if BUILD_ORDER_EDITOR_UI_STATE.created then",
        )

    def test_editor_is_one_scrollable_column_with_a_sticky_action_header(self) -> None:
        editor = named(self.xaml_root, "BuildOrderEditorScreen")
        self.assertEqual(editor.tag, f"{{{PRESENTATION_NS}}}Grid")
        header = named(editor, "BuildOrderEditorActionHeader")
        self.assertIsNotNone(named(header, "BuildOrderCurrentCivilization"))
        self.assertIsNotNone(named(header, "BuildOrderTitleEditor"))
        header_xml = ET.tostring(header, encoding="unicode")
        self.assertIn("RaceIconSecondary", header_xml)
        for label in ("Save", "Cancel", "Create copy"):
            self.assertIn(f'Content="{label}"', header_xml)
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
        for token in (
            "Drag step",
            "Drag check",
            "Move up",
            "Move down",
            "Add check",
            "Delete step",
            "Delete check",
            "[errors]",
        ):
            with self.subTest(token=token):
                self.assertIn(token, self.xaml)
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
        for resource in ("food", "wood", "gold", "stone"):
            with self.subTest(resource=resource):
                self.assertIn(f"[{resource}][display_value]", resource_xml)
                self.assertIn(f'Content="{resource.title()}"', resource_xml)
        self.assertIn("positive integer (optional)", resource_xml)
        self.assertIn("[no_collect]", resource_xml)
        self.assertIn("Do not collect", resource_xml)

    def test_live_options_render_label_icon_and_internal_id_fallback(self) -> None:
        option_template = named(self.xaml_root, "BuildOrderLiveOptionTemplate")
        option_xml = ET.tostring(option_template, encoding="unicode")
        self.assertIn("[label]", option_xml)
        self.assertIn("[icon]", option_xml)
        self.assertIn("[id_fallback]", option_xml)
        self.assertIn("No compatible options discovered", self.xaml)

    def test_invalid_draft_disables_save(self) -> None:
        header = named(self.xaml_root, "BuildOrderEditorActionHeader")
        save = next(
            element
            for element in header.iter()
            if element.tag == f"{{{PRESENTATION_NS}}}Button"
            and element.get("Content") == "Save"
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
            "entities": [
                {
                    "id": "building_barracks_eng",
                    "kind": "entity",
                    "age": 1,
                    "label": "Barracks",
                    "icon": "barracks-icon",
                }
            ],
            "squads": [],
            "upgrades": [],
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
        self.assertEqual(len(step["flat_fields"]), 1)
        self.assertEqual(step["flat_fields"][1]["path"], "steps.1.title")
        check = find_view_node(root, "steps.1.checks.2")
        self.assertEqual(check["label"], "Build")
        self.assertEqual(check["kind"], "built")
        count = find_view_node(root, "steps.1.checks.2.payload.count")
        self.assertEqual(count["errors"].array(), ["must be a positive integer"])

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
            "entities": [],
            "squads": [],
            "upgrades": [],
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
            "entities": [],
            "squads": [],
            "upgrades": [],
            "families": [],
        }
        root = self.runtime.call(
            "BuildOrderEditorUI_ProjectDraft", draft, [], discovery, {}
        )
        field = find_view_node(root, "steps.1.checks.1.payload.id")
        self.assertEqual(len(field["options"]), 0)
        self.assertEqual(field["empty_options_visibility"], "Visible")

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


if __name__ == "__main__":
    unittest.main()
