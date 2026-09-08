import re
import unittest
from pathlib import Path

from tests.scar_runtime import LuaResults, LuaTable, ScarRuntime
from tools.build_orders.datastore import _render_value, parse_datastore


ROOT = Path(__file__).resolve().parents[1]
EDITOR_SCAR = ROOT / "assets" / "scar" / "build_orders" / "editor.scar"
DATASTORE_SCAR = ROOT / "assets" / "scar" / "build_orders" / "datastore.scar"
DISCOVERY_SCAR = ROOT / "assets" / "scar" / "build_orders" / "editor_discovery.scar"
MODEL_SCAR = ROOT / "assets" / "scar" / "build_orders" / "editor_model.scar"
SCHEMA_SCAR = ROOT / "assets" / "scar" / "build_orders" / "editor_schema.scar"
UI_SCAR = ROOT / "assets" / "scar" / "build_orders" / "editor_ui.scar"


def function_body(source: str, name: str) -> str:
    match = re.search(
        rf"^function {re.escape(name)}\([^\n]*\)\n(.*?)(?=^function |\Z)",
        source,
        flags=re.MULTILINE | re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"missing function {name}")
    return match.group(1)


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


def lua_to_python(value):
    if isinstance(value, LuaTable):
        array = value.array()
        if len(value.data) == len(array):
            return [lua_to_python(item) for item in array]
        return {key: lua_to_python(item) for key, item in value.data.items()}
    return value


def parse_saved_editor_order(order) -> object:
    saved = lua_to_python(order)
    datastore = {
        "schema_version": 1,
        "build_orders": {saved["id"]: saved},
    }
    return parse_datastore("LuaDataStore = " + _render_value(datastore, 0) + "\n")


def valid_order(
    order_id: str = "english-feudal-pressure",
    title: str = "Feudal Pressure",
):
    return {
        "id": order_id,
        "civ": "english",
        "title": title,
        "source": "test",
        "steps": [
            {
                "title": "Opening",
                "checks": [
                    {
                        "id": f"{order_id}:1:hints:1",
                        "kind": "hints",
                        "title": "[HINT] Keep building villagers",
                        "optional": True,
                        "payload": {"text": "Keep building villagers"},
                    }
                ],
            }
        ],
    }


def age_order():
    order_id = "english-age-test"
    return {
        "id": order_id,
        "civ": "english",
        "title": "Age Test",
        "steps": [
            {
                "title": "Opening",
                "checks": [
                    {
                        "id": f"{order_id}:1:hints:1",
                        "kind": "hints",
                        "title": "[HINT] Open",
                        "optional": True,
                        "payload": {"text": "Open"},
                    }
                ],
            },
            {
                "title": "Age up",
                "checks": [
                    {
                        "id": f"{order_id}:2:age_up:1",
                        "kind": "age_up",
                        "title": "Age up: landmark_feudal",
                        "optional": False,
                        "payload": {"id": "landmark_feudal"},
                    }
                ],
            },
            {
                "title": "Production",
                "checks": [
                    {
                        "id": f"{order_id}:3:buildings:1",
                        "kind": "buildings",
                        "title": "Have barracks_feudal",
                        "optional": False,
                        "payload": {"id": "barracks_feudal", "count": 1},
                    }
                ],
            },
        ],
    }


def discovery_snapshot():
    return {
        "civ": "english",
        "civ_name": "English",
        "buildings": [
            {
                "id": "house_dark",
                "kind": "building",
                "age": 1,
                "label": "House",
                "icon": "house",
            },
            {
                "id": "barracks_feudal",
                "kind": "building",
                "age": 2,
                "label": "Barracks",
                "icon": "barracks",
            },
            {
                "id": "keep_castle",
                "kind": "building",
                "age": 3,
                "label": "Keep",
                "icon": "keep",
            },
        ],
        "age_ups": [
            {
                "id": "landmark_feudal",
                "kind": "age_up",
                "age": 2,
                "label": "Feudal Landmark",
                "icon": "landmark",
            }
        ],
        "squads": [],
        "technologies": [],
        "families": [],
    }


class BuildOrderEditorContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not EDITOR_SCAR.exists():
            raise AssertionError(f"missing editor controller: {EDITOR_SCAR}")
        cls.source = EDITOR_SCAR.read_text(encoding="utf-8")

    def test_exports_controller_contract_and_single_owned_state_table(self) -> None:
        for name in (
            "BuildOrderEditor_OpenCreate",
            "BuildOrderEditor_OpenEdit",
            "BuildOrderEditor_CreateCopy",
            "BuildOrderEditor_Save",
            "BuildOrderEditor_Cancel",
            "BuildOrderEditor_HandleCommand",
            "BuildOrderEditor_AddCheck",
            "BuildOrderEditor_Stop",
        ):
            with self.subTest(name=name):
                function_body(self.source, name)
        for field in (
            "draft = nil",
            "original_id = nil",
            "discovery = nil",
            "errors = {}",
            "on_complete = nil",
        ):
            with self.subTest(field=field):
                self.assertIn(field, self.source)

    def test_controller_does_not_resume_gameplay_or_own_selector_transitions(self) -> None:
        self.assertNotIn("Game_SetSimRate", self.source)
        self.assertNotIn("BuildOrderEditorUI_ShowSelector", self.source)
        self.assertNotIn("BuildOrderStartup_", self.source)


class BuildOrderEditorBehaviorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        editor_source = EDITOR_SCAR.read_text(encoding="utf-8")
        cls.runtime_source = "\n".join(
            (
                DATASTORE_SCAR.read_text(encoding="utf-8"),
                DISCOVERY_SCAR.read_text(encoding="utf-8"),
                MODEL_SCAR.read_text(encoding="utf-8"),
                SCHEMA_SCAR.read_text(encoding="utf-8"),
                strip_xaml(UI_SCAR.read_text(encoding="utf-8")),
                editor_source,
            )
        )

    def setUp(self) -> None:
        self.runtime = ScarRuntime(self.runtime_source)
        self.runtime.globals["tonumber"] = self.lua_tonumber
        self.runtime.globals["tostring"] = lambda value: str(value)
        self.runtime.globals["pcall"] = self.lua_pcall
        self.runtime.globals["string"]["gmatch"] = (
            lambda value, _pattern: value.split(".")
        )

        self.collect_players = []
        self.discovery_clears = 0
        self.callback_tables = []
        self.editor_models = []
        self.ui_hides = 0
        self.ui_stops = 0
        self.apply_calls = []
        self.apply_result = (True, "")
        self.apply_exception = None

        self.runtime.globals["Game_GetLocalPlayer"] = lambda: "local-player"
        self.real_discovery_collect = self.runtime.globals[
            "BuildOrderDiscovery_Collect"
        ]
        self.real_datastore_apply = self.runtime.globals["BuildOrderDatastore_Apply"]
        self.runtime.globals["BuildOrderDiscovery_Collect"] = self.collect
        self.runtime.globals["BuildOrderDiscovery_Clear"] = self.clear_discovery
        self.runtime.globals["BuildOrderEditorUI_SetCallbacks"] = (
            self.set_callbacks
        )
        self.runtime.globals["BuildOrderEditorUI_ShowEditor"] = self.show_editor
        self.runtime.globals["BuildOrderEditorUI_Hide"] = self.hide_ui
        self.runtime.globals["BuildOrderEditorUI_Stop"] = self.stop_ui
        self.runtime.globals["BuildOrderDatastore_Apply"] = self.apply
        self.runtime.globals["BUILD_ORDER_CATALOG"] = self.runtime.table({})

    @staticmethod
    def lua_tonumber(value):
        if isinstance(value, (int, float)):
            return value
        if not isinstance(value, str) or value.strip() == "":
            return None
        try:
            number = float(value)
        except ValueError:
            return None
        return int(number) if number.is_integer() else number

    @staticmethod
    def lua_pcall(function, *arguments):
        try:
            result = function(*arguments)
        except Exception as error:  # pragma: no cover - exercised via Save
            return LuaResults((False, str(error)))
        if isinstance(result, LuaResults):
            return LuaResults((True, *result.values))
        return LuaResults((True, result))

    def collect(self, player):
        self.collect_players.append(player)
        return self.runtime.table(discovery_snapshot())

    def clear_discovery(self):
        self.discovery_clears += 1

    def set_callbacks(self, callbacks):
        self.callback_tables.append(callbacks)

    def show_editor(self, model):
        self.editor_models.append(model)
        return True

    def hide_ui(self):
        self.ui_hides += 1
        return True

    def stop_ui(self):
        self.ui_stops += 1

    def apply(self, original_id, new_id, order):
        self.apply_calls.append((original_id, new_id, order))
        if self.apply_exception is not None:
            raise self.apply_exception
        return LuaResults(self.apply_result)

    def set_catalog(self, orders):
        self.runtime.globals["BUILD_ORDER_CATALOG"] = self.runtime.table(
            {order["id"]: order for order in orders}
        )

    def test_non_string_race_handle_creates_and_saves_with_canonical_civ_id(self) -> None:
        race_handle = object()
        property_groups = {
            "entity-properties": ["building_house_eng"],
            "squad-properties": [],
            "upgrade-properties": [],
        }
        stored = []

        self.runtime.globals["BuildOrderDiscovery_Collect"] = (
            self.real_discovery_collect
        )
        self.runtime.globals["BuildOrderDatastore_Apply"] = self.real_datastore_apply
        self.runtime.globals["BuildOrderEditorUI_SetCallbacks"] = lambda _callbacks: None
        self.runtime.globals["BuildOrderEditorUI_ShowEditor"] = lambda _model: True
        self.runtime.globals["BuildOrderEditorUI_Hide"] = lambda: None
        self.runtime.globals["PBG_EntityProperties"] = "entity-properties"
        self.runtime.globals["PBG_SquadProperties"] = "squad-properties"
        self.runtime.globals["PBG_UpgradeProperties"] = "upgrade-properties"
        self.runtime.globals["table"]["sort"] = lambda _values, _compare: None
        self.runtime.globals["Player_GetRace"] = lambda _player: race_handle
        self.runtime.globals["Player_GetRaceName"] = lambda _player: "English"
        self.runtime.globals["BP_GetPropertyBagGroupCount"] = (
            lambda group: len(property_groups[group])
        )
        self.runtime.globals["BP_GetPropertyBagGroupPathName"] = (
            lambda group, index: property_groups[group][index]
        )
        self.runtime.globals["BP_GetEntityTypeExtRaceCount"] = lambda _path: 1
        self.runtime.globals["BP_GetEntityTypeExtRaceBlueprintAtIndex"] = (
            lambda _path, _index: race_handle
        )
        self.runtime.globals["BP_GetSquadTypeExtRaceCount"] = lambda _path: 0
        self.runtime.globals["BP_GetSquadTypeExtRaceBlueprintAtIndex"] = (
            lambda _path, _index: None
        )
        self.runtime.globals["BP_GetEntityBlueprint"] = lambda path: path
        self.runtime.globals["BP_GetSquadBlueprint"] = lambda path: path
        self.runtime.globals["BP_GetUpgradeBlueprint"] = lambda path: path
        self.runtime.globals["Entity_IsEBPOfType"] = (
            lambda _pbg, kind: kind == "building"
        )
        self.runtime.globals["Squad_IsSBPOfType"] = lambda _pbg, _kind: False
        self.runtime.globals["BP_IsUpgradeOfType"] = lambda _pbg, _kind: False
        self.runtime.globals["BP_GetEntityUIInfo"] = lambda _pbg: self.runtime.table(
            {"screenName": "House", "iconName": "house"}
        )
        self.runtime.globals["BP_GetSquadUIInfo"] = lambda _pbg, _race: None
        self.runtime.globals["BP_GetUpgradeUIInfo"] = lambda _pbg: None
        self.runtime.globals["Loc_ToAnsi"] = lambda value: value
        self.runtime.globals["AI_CombatFitnessGetSquadArchetypeNames"] = (
            lambda: self.runtime.table([])
        )
        self.runtime.globals["AI_CombatFitnessGetSquadArchetypePBGs"] = (
            lambda _name: self.runtime.table([])
        )
        self.runtime.globals["Game_StoreTableData"] = (
            lambda datastore_id, value: stored.append((datastore_id, value))
        )
        self.runtime.globals["Game_SaveTextDataStore"] = lambda _datastore_id, _path: None

        self.assertTrue(self.runtime.call("BuildOrderEditor_OpenCreate", None))
        draft = self.runtime.globals["BUILD_ORDER_EDITOR_STATE"]["draft"]
        self.assertEqual(draft["civ"], "english")
        draft["title"] = "Race Handle"
        draft["steps"] = self.runtime.table(
            [
                {
                    "title": "Opening",
                    "checks": [
                        {
                            "kind": "hints",
                            "optional": True,
                            "payload": {"text": "Scout"},
                        }
                    ],
                }
            ]
        )

        self.assertTrue(self.runtime.call("BuildOrderEditor_Save"))
        saved = self.runtime.globals["BUILD_ORDER_CATALOG"]["english-race-handle"]
        self.assertEqual(saved["civ"], "english")
        self.assertEqual(len(stored), 1)

    def call_with_callback(self, name, *arguments):
        result = self.runtime.globals[name](*arguments)
        if not isinstance(result, LuaResults):
            return result
        if len(result.values) == 0:
            return None
        if len(result.values) == 1:
            return result.values[0]
        return result.values

    def project_latest_model(self):
        model = self.editor_models[-1]
        result = self.runtime.globals["BuildOrderEditorUI_ProjectDraft"](
            model["draft"],
            model["errors"],
            model["discovery"],
            model["expanded"],
            self.runtime.globals["BUILD_ORDER_EDITOR_SCHEMA"],
            None,
        )
        return result.values[0]

    def test_create_and_edit_each_collect_fresh_local_player_discovery(self) -> None:
        order = valid_order()
        self.set_catalog([order])

        self.assertTrue(self.runtime.call("BuildOrderEditor_OpenCreate", None))
        state = self.runtime.globals["BUILD_ORDER_EDITOR_STATE"]
        first_discovery = state["discovery"]
        self.assertEqual(state["draft"]["civ"], "english")
        self.assertIsNone(state["original_id"])

        self.assertTrue(
            self.runtime.call("BuildOrderEditor_OpenEdit", order["id"], None)
        )
        state = self.runtime.globals["BUILD_ORDER_EDITOR_STATE"]
        self.assertEqual(self.collect_players, ["local-player", "local-player"])
        self.assertIsNot(state["discovery"], first_discovery)
        self.assertEqual(state["original_id"], order["id"])
        self.assertEqual(state["draft"]["original_id"], order["id"])
        self.assertGreaterEqual(self.discovery_clears, 2)

        callbacks = self.callback_tables[-1]
        for command in (
            "copy",
            "save",
            "cancel",
            "field_change",
            "add",
            "add_check",
            "delete",
            "expand",
            "collapse",
            "reorder",
        ):
            with self.subTest(command=command):
                self.assertIsInstance(callbacks[command], str)
                self.assertTrue(callbacks[command].startswith("BuildOrderEditor_"))

    def test_copy_deep_copies_current_draft_and_chooses_free_numbered_title(self) -> None:
        original = valid_order()
        copy_one = valid_order("english-feudal-pressure-copy", "Feudal Pressure (copy)")
        copy_two = valid_order(
            "english-feudal-pressure-copy-2", "Feudal Pressure (copy 2)"
        )
        self.set_catalog([original, copy_one, copy_two])
        self.runtime.call("BuildOrderEditor_OpenEdit", original["id"], None)
        old_draft = self.runtime.globals["BUILD_ORDER_EDITOR_STATE"]["draft"]

        self.assertTrue(self.runtime.call("BuildOrderEditor_CreateCopy"))
        state = self.runtime.globals["BUILD_ORDER_EDITOR_STATE"]
        copied = state["draft"]
        self.assertIsNot(copied, old_draft)
        self.assertIsNot(copied["steps"], old_draft["steps"])
        self.assertEqual(copied["title"], "Feudal Pressure (copy 3)")
        self.assertIsNone(copied["original_id"])
        self.assertIsNone(copied["original_civ"])
        self.assertIsNone(copied["original_title"])
        self.assertIsNone(state["original_id"])

        copied["steps"][1]["title"] = "Changed only in copy"
        self.assertEqual(old_draft["steps"][1]["title"], "Opening")

    def test_dotted_path_mutations_validate_and_refresh_after_each_change(self) -> None:
        order = valid_order()
        self.set_catalog([order])
        self.runtime.call("BuildOrderEditor_OpenEdit", order["id"], None)
        initial_refreshes = len(self.editor_models)

        self.assertTrue(
            self.runtime.call(
                "BuildOrderEditor_HandleCommand",
                "field_change",
                "steps.1.title",
                "Renamed step",
            )
        )
        state = self.runtime.globals["BUILD_ORDER_EDITOR_STATE"]
        self.assertEqual(state["draft"]["steps"][1]["title"], "Renamed step")
        self.assertEqual(len(self.editor_models), initial_refreshes + 1)
        self.assertEqual(len(state["errors"]), 0)

        self.assertTrue(
            self.runtime.call(
                "BuildOrderEditor_HandleCommand",
                "add",
                "steps",
                {"title": "Second", "checks": []},
            )
        )
        self.assertEqual(len(self.editor_models), initial_refreshes + 2)
        self.assertGreater(len(state["errors"]), 0)

        self.assertTrue(
            self.runtime.call(
                "BuildOrderEditor_HandleCommand",
                "delete",
                "steps.2",
                None,
            )
        )
        self.assertEqual(len(self.editor_models), initial_refreshes + 3)
        self.assertEqual(len(state["errors"]), 0)

        self.assertFalse(
            self.runtime.call(
                "BuildOrderEditor_HandleCommand",
                "field_change",
                "steps.9.title",
                "Not routed",
            )
        )
        self.assertEqual(len(self.editor_models), initial_refreshes + 3)

    def test_age_up_mutation_recomputes_step_ages_and_live_option_filter(self) -> None:
        order = age_order()
        order["steps"] = [order["steps"][0], order["steps"][2]]
        self.set_catalog([order])
        self.runtime.call("BuildOrderEditor_OpenEdit", order["id"], None)
        state = self.runtime.globals["BUILD_ORDER_EDITOR_STATE"]
        self.assertEqual(
            [step["inferred_age"] for step in state["draft"]["steps"].array()],
            [1, 1],
        )

        age_up = {
            "kind": "age_up",
            "optional": False,
            "payload": {"alternatives": ["landmark_feudal"]},
        }
        self.assertTrue(
            self.runtime.call(
                "BuildOrderEditor_HandleCommand",
                "field_change",
                "steps.1.checks.1",
                age_up,
            )
        )
        self.assertEqual(
            [step["inferred_age"] for step in state["draft"]["steps"].array()],
            [1, 2],
        )

        root = self.project_latest_model()
        building = find_view_node(root, "steps.2.checks.1.payload.id")
        self.assertEqual(
            [option["id"] for option in building["options"].array()],
            ["house_dark", "barracks_feudal"],
        )

    def test_pointer_and_accessible_reorder_share_model_move_and_refresh_ages(self) -> None:
        order = age_order()
        self.set_catalog([order])
        self.runtime.call("BuildOrderEditor_OpenEdit", order["id"], None)
        state = self.runtime.globals["BUILD_ORDER_EDITOR_STATE"]
        self.assertEqual(
            [step["inferred_age"] for step in state["draft"]["steps"].array()],
            [1, 1, 2],
        )

        self.assertTrue(
            self.runtime.call("BuildOrderEditor_Reorder", "steps", 2, 1)
        )
        self.assertEqual(
            [step["title"] for step in state["draft"]["steps"].array()],
            ["Age up", "Opening", "Production"],
        )
        self.assertEqual(
            [step["inferred_age"] for step in state["draft"]["steps"].array()],
            [1, 2, 2],
        )
        self.assertIn("BuildOrderEditor_Move(", function_body(
            EDITOR_SCAR.read_text(encoding="utf-8"),
            "BuildOrderEditor_HandleCommand",
        ))

        root = self.project_latest_model()
        building = find_view_node(root, "steps.3.checks.1.payload.id")
        self.assertNotIn(
            "keep_castle", [option["id"] for option in building["options"].array()]
        )

    def test_invalid_save_keeps_draft_open_with_visible_errors(self) -> None:
        completions = []
        self.call_with_callback(
            "BuildOrderEditor_OpenCreate", lambda saved_id: completions.append(saved_id)
        )
        state = self.runtime.globals["BUILD_ORDER_EDITOR_STATE"]
        draft = state["draft"]

        self.assertFalse(self.runtime.call("BuildOrderEditor_Save"))
        self.assertIs(state["draft"], draft)
        self.assertGreater(len(state["errors"]), 0)
        self.assertEqual(self.apply_calls, [])
        self.assertEqual(completions, [])
        self.assertEqual(self.ui_hides, 0)
        self.assertIs(self.editor_models[-1]["draft"], draft)

    def test_valid_save_applies_original_and_new_ids_then_releases_state(self) -> None:
        order = valid_order()
        self.set_catalog([order])
        completions = []
        self.call_with_callback(
            "BuildOrderEditor_OpenEdit",
            order["id"],
            lambda saved_id: completions.append(saved_id),
        )
        self.runtime.call(
            "BuildOrderEditor_HandleCommand",
            "field_change",
            "title",
            "Renamed Pressure",
        )

        self.assertTrue(self.runtime.call("BuildOrderEditor_Save"))
        self.assertEqual(len(self.apply_calls), 1)
        original_id, new_id, saved = self.apply_calls[0]
        self.assertEqual(original_id, order["id"])
        self.assertEqual(new_id, "english-renamed-pressure")
        self.assertEqual(saved["id"], new_id)
        self.assertEqual(saved["title"], "Renamed Pressure")
        self.assertEqual(completions, [new_id])

        state = self.runtime.globals["BUILD_ORDER_EDITOR_STATE"]
        self.assertIsNone(state["draft"])
        self.assertIsNone(state["original_id"])
        self.assertIsNone(state["discovery"])
        self.assertEqual(state["errors"].array(), [])
        self.assertIsNone(state["on_complete"])
        self.assertEqual(self.ui_hides, 1)

    def test_editor_save_round_trips_canonical_check_ids_through_python_datastore_parser(self) -> None:
        order = valid_order()
        self.set_catalog([order])
        self.runtime.call("BuildOrderEditor_OpenEdit", order["id"], None)

        self.assertTrue(self.runtime.call("BuildOrderEditor_Save"))
        saved = self.apply_calls[0][2]
        self.assertEqual(saved["steps"][1]["checks"][1]["id"], f"{order['id']}:1:1")

        parsed = parse_saved_editor_order(saved)
        self.assertEqual(parsed.build_orders[0].id, order["id"])
        self.assertEqual(parsed.build_orders[0].steps[0].checks[0].kind, "hints")

    def test_family_selected_option_keeps_presentation_through_ui_command_and_save(self) -> None:
        discovery = discovery_snapshot()
        discovery["families"] = [
            {
                "ids": ["unit_spearman_1_eng", "unit_spearman_2_eng"],
                "kind": "family",
                "age": 1,
                "label": "Spearman",
                "icon": "unit_spearman",
            }
        ]
        self.runtime.globals["BuildOrderDiscovery_Collect"] = (
            lambda _player: self.runtime.table(discovery)
        )

        for kind, expected_title in (
            ("produce", "Produce 2 Spearman"),
            ("units", "Have 2 active Spearman"),
        ):
            with self.subTest(kind=kind):
                self.apply_calls.clear()
                self.assertTrue(self.runtime.call("BuildOrderEditor_OpenCreate", None))
                state = self.runtime.globals["BUILD_ORDER_EDITOR_STATE"]
                state["draft"]["title"] = f"{kind.title()} family"
                payload = {"family": {"ids": []}, "count": 2}
                if kind == "produce":
                    payload["constant"] = False
                    payload["queued"] = False
                state["draft"]["steps"] = self.runtime.table(
                    [
                        {
                            "title": "Opening",
                            "checks": [
                                {
                                    "kind": kind,
                                    "optional": False,
                                    "payload": payload,
                                }
                            ],
                        }
                    ]
                )
                self.assertTrue(self.runtime.call("BuildOrderEditor_Refresh"))

                root = self.project_latest_model()
                field = find_view_node(root, "steps.1.checks.1.payload.family")
                option = field["options"][1]
                self.assertEqual(option["value"]["label"], "Spearman")
                self.assertEqual(option["value"]["icon"], "unit_spearman")
                self.assertEqual(
                    option["value"]["ids"].array(),
                    ["unit_spearman_1_eng", "unit_spearman_2_eng"],
                )

                self.assertTrue(
                    self.runtime.call(
                        "BuildOrderEditor_FieldChange",
                        {
                            "path": "steps.1.checks.1.payload.family",
                            "selected_option": option,
                        },
                    )
                )
                selected = state["draft"]["steps"][1]["checks"][1]["payload"]["family"]
                self.assertEqual(selected["label"], "Spearman")
                self.assertEqual(selected["icon"], "unit_spearman")
                self.assertEqual(
                    selected["ids"].array(),
                    ["unit_spearman_1_eng", "unit_spearman_2_eng"],
                )

                self.assertTrue(self.runtime.call("BuildOrderEditor_Save"))
                saved = self.apply_calls[0][2]["steps"][1]["checks"][1]
                self.assertEqual(saved["title"], expected_title)
                self.assertEqual(
                    saved["payload"]["ids"].array(),
                    ["unit_spearman_1_eng", "unit_spearman_2_eng"],
                )

    def test_unknown_saved_internal_id_survives_controller_validation_and_save(self) -> None:
        order = valid_order()
        order["steps"][0]["checks"] = [
            {
                "id": f"{order['id']}:1:buildings:1",
                "kind": "buildings",
                "title": "Have retired_internal_barracks",
                "optional": False,
                "payload": {"id": "retired_internal_barracks", "count": 1},
            }
        ]
        self.set_catalog([order])
        self.runtime.call("BuildOrderEditor_OpenEdit", order["id"], None)

        self.assertTrue(self.runtime.call("BuildOrderEditor_Save"))
        saved = self.apply_calls[0][2]
        self.assertEqual(
            saved["steps"][1]["checks"][1]["payload"]["id"],
            "retired_internal_barracks",
        )

    def test_collision_and_persistence_errors_stay_visible_without_clearing(self) -> None:
        order = valid_order()
        self.set_catalog([order])
        completions = []
        self.call_with_callback(
            "BuildOrderEditor_OpenEdit",
            order["id"],
            lambda saved_id: completions.append(saved_id),
        )
        state = self.runtime.globals["BUILD_ORDER_EDITOR_STATE"]
        draft = state["draft"]

        self.apply_result = (False, "id_collision")
        self.assertFalse(self.runtime.call("BuildOrderEditor_Save"))
        self.assertIs(state["draft"], draft)
        self.assertEqual(state["errors"][1]["path"], "save")
        self.assertEqual(
            state["errors"][1]["message"],
            "$dfb5645698a84afb91cf7a2dfb0f4a4e:140",
        )
        self.assertEqual(completions, [])

        self.apply_exception = RuntimeError("datastore unavailable")
        self.assertFalse(self.runtime.call("BuildOrderEditor_Save"))
        self.assertIs(state["draft"], draft)
        self.assertEqual(
            state["errors"][1]["message"],
            "$dfb5645698a84afb91cf7a2dfb0f4a4e:141",
        )
        self.assertEqual(completions, [])

    def test_ui_parameter_adapters_route_values_toggles_and_shared_reorder(self) -> None:
        order = valid_order()
        order["steps"][0]["checks"] = [
            {
                "id": f"{order['id']}:1:vils:1",
                "kind": "vils",
                "title": "Assign 7 food",
                "optional": False,
                "payload": {"food": 7},
            }
        ]
        self.set_catalog([order])
        self.runtime.call("BuildOrderEditor_OpenEdit", order["id"], None)
        state = self.runtime.globals["BUILD_ORDER_EDITOR_STATE"]

        self.assertTrue(
            self.runtime.call(
                "BuildOrderEditor_FieldChange",
                {
                    "path": "steps.1.checks.1.payload.food",
                    "value_type": "positive_integer",
                    "display_value": "9",
                },
            )
        )
        self.assertEqual(state["draft"]["steps"][1]["checks"][1]["payload"]["food"], 9)

        self.assertTrue(
            self.runtime.call(
                "BuildOrderEditor_FieldChange",
                {
                    "path": "steps.1.checks.1.payload.no_collect",
                    "id": "gold",
                    "selected": True,
                },
            )
        )
        no_collect = state["draft"]["steps"][1]["checks"][1]["payload"]["no_collect"]
        self.assertEqual(no_collect.array(), ["gold"])

        self.assertTrue(
            self.runtime.call(
                "BuildOrderEditor_FieldChange",
                {
                    "path": "steps.1.checks.1.payload.no_collect",
                    "id": "gold",
                    "selected": False,
                },
            )
        )
        self.assertEqual(no_collect.array(), [])

    def test_add_check_defaults_omitted_kind_and_constructs_explicit_selected_kind(self) -> None:
        self.assertIn("BuildOrderEditor_AddCheck", self.runtime.globals)
        order = valid_order()
        self.set_catalog([order])
        self.runtime.call("BuildOrderEditor_OpenEdit", order["id"], None)
        checks = self.runtime.globals["BUILD_ORDER_EDITOR_STATE"]["draft"][
            "steps"
        ][1]["checks"]

        self.assertTrue(
            self.runtime.call(
                "BuildOrderEditor_AddCheck",
                {"path": "steps.1.checks"},
            )
        )
        omitted = checks[2]
        self.assertEqual(omitted["kind"], "vils")
        self.assertFalse(omitted["optional"])
        self.assertEqual(omitted["payload"]["no_collect"].array(), [])

        self.assertTrue(
            self.runtime.call(
                "BuildOrderEditor_AddCheck",
                {
                    "path": "steps.1.checks",
                    "selected_option": {"id": "built", "value": "built"},
                },
            )
        )
        explicit = checks[3]
        self.assertEqual(explicit["kind"], "built")
        self.assertFalse(explicit["optional"])
        self.assertEqual(explicit["payload"]["alternatives"].array(), [])
        self.assertEqual(explicit["payload"]["count"], 1)

    def test_cancel_and_stop_clear_state_discovery_errors_and_callbacks(self) -> None:
        cancel_completions = []
        self.call_with_callback(
            "BuildOrderEditor_OpenCreate",
            lambda saved_id: cancel_completions.append(saved_id),
        )
        self.assertTrue(self.runtime.call("BuildOrderEditor_Cancel"))
        self.assertEqual(cancel_completions, [None])
        state = self.runtime.globals["BUILD_ORDER_EDITOR_STATE"]
        self.assertIsNone(state["draft"])
        self.assertIsNone(state["discovery"])
        self.assertEqual(state["errors"].array(), [])
        self.assertIsNone(state["on_complete"])
        self.assertEqual(self.ui_hides, 1)

        stop_completions = []
        self.call_with_callback(
            "BuildOrderEditor_OpenCreate",
            lambda saved_id: stop_completions.append(saved_id),
        )
        self.runtime.call("BuildOrderEditor_Stop")
        self.assertEqual(stop_completions, [])
        self.assertIsNone(state["draft"])
        self.assertIsNone(state["discovery"])
        self.assertEqual(state["errors"].array(), [])
        self.assertIsNone(state["on_complete"])
        self.assertEqual(self.ui_stops, 1)
        self.assertGreaterEqual(self.discovery_clears, 4)


if __name__ == "__main__":
    unittest.main()
