import csv
import re
import unittest
from pathlib import Path

from tests.scar_runtime import LuaResults, ScarRuntime


ROOT = Path(__file__).resolve().parents[1]
STARTUP_PATH = ROOT / "assets" / "scar" / "build_orders" / "startup.scar"
EDITOR_PATH = ROOT / "assets" / "scar" / "build_orders" / "editor.scar"
MAIN_PATH = ROOT / "assets" / "scar" / "winconditions" / "Macro Trainer.scar"
LOCDB_PATH = ROOT / "assets" / "locdb" / "Macro Trainer_en.csv"
MOD_NAMESPACE = "dfb5645698a84afb91cf7a2dfb0f4a4e"


def function_body(source: str, name: str) -> str:
    match = re.search(
        rf"^function {re.escape(name)}\([^\n]*\)\n(.*?)(?=^function |\Z)",
        source,
        flags=re.MULTILINE | re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"missing function {name}")
    return match.group(1)


def csv_rows(path: Path) -> dict[int, list[str]]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        return {
            int(row[0]): row
            for row in csv.reader(source)
            if row and row[0].isdigit()
        }


def build_order(order_id: str, title: str, civ: str = "english") -> dict:
    return {
        "id": order_id,
        "civ": civ,
        "title": title,
        "steps": [],
    }


class BuildOrderStartupBehaviorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = STARTUP_PATH.read_text(encoding="utf-8")
        self.runtime = ScarRuntime(self.source)
        self.runtime.globals["NORMAL_SIM_RATE"] = 8
        self.runtime.globals["DB_Button1"] = "button-1"
        self.runtime.globals["DB_Button2"] = "button-2"
        self.runtime.globals["DB_Button3"] = "button-3"
        self.runtime.globals["DB_Button4"] = "button-4"
        self.runtime.globals["DC_Default"] = "default-dialog"
        self.runtime.globals["_mod"] = self.runtime.table(
            {
                "selectedBuildOrderID": None,
                "simspeedEnabled": True,
                "simspeedStarted": False,
                "buildOrderStarted": False,
                "startupStarted": False,
                "startupActive": False,
                "startupAwaitingChoice": False,
                "startupFallbackOpen": False,
                "startupScreen": "hidden",
                "startupPriorSelectionID": None,
                "startupMessage": None,
                "compatibleBuildOrderIDs": [],
            }
        )
        self.catalog = {
            "english-zulu": build_order("english-zulu", "Zulu"),
            "french-alpha": build_order("french-alpha", "Alpha", "french"),
            "english-alpha-b": build_order("english-alpha-b", "Alpha"),
            "english-alpha-a": build_order("english-alpha-a", "Alpha"),
        }
        self.runtime.globals["BUILD_ORDER_CATALOG"] = self.runtime.table(
            self.catalog
        )

        self.rule_adds = []
        self.rule_removes = []
        self.rule_remove_me = 0
        self.sim_rates = []
        self.objective_starts = []
        self.cycle_starts = 0
        self.callback_tables = []
        self.selector_models = []
        self.confirmation_models = []
        self.ui_hides = 0
        self.selector_result = True
        self.confirmation_result = True
        self.create_callbacks = []
        self.edit_calls = []
        self.message_box_text = []
        self.message_box_buttons = []
        self.message_box_callbacks = []

        self.runtime.globals["Game_GetLocalPlayer"] = lambda: "local-player"
        self.runtime.globals["Player_GetRaceName"] = (
            lambda player: "english" if player == "local-player" else "french"
        )
        self.runtime.globals["Rule_Add"] = self.rule_adds.append
        self.runtime.globals["Rule_Remove"] = self.rule_removes.append
        self.runtime.globals["Rule_RemoveMe"] = self.remove_me
        self.runtime.globals["Misc_SetSimRate"] = self.sim_rates.append
        self.runtime.globals["BuildOrder_Start"] = (
            lambda order, player: self.objective_starts.append((order, player))
        )
        self.runtime.globals["Mod_StartSimspeedCycle"] = self.start_cycle
        self.runtime.globals["BuildOrderEditorUI_SetCallbacks"] = (
            self.callback_tables.append
        )
        self.runtime.globals["BuildOrderEditorUI_ShowSelector"] = (
            self.show_selector
        )
        self.runtime.globals["BuildOrderEditorUI_ShowNoSelectionConfirmation"] = (
            self.show_confirmation
        )
        self.runtime.globals["BuildOrderEditorUI_Hide"] = self.hide_ui
        self.runtime.globals["BuildOrderEditor_OpenCreate"] = self.open_create
        self.runtime.globals["BuildOrderEditor_OpenEdit"] = self.open_edit
        self.runtime.globals["UI_MessageBoxSetText"] = (
            lambda title, message: self.message_box_text.append((title, message))
        )
        self.runtime.globals["UI_MessageBoxSetButton"] = (
            lambda *arguments: self.message_box_buttons.append(arguments)
        )
        self.runtime.globals["UI_MessageBoxShow"] = (
            lambda dialog, callback: self.message_box_callbacks.append(
                (dialog, callback)
            )
        )

    def call(self, name: str, *arguments):
        self.assertIn(name, self.runtime.globals, f"missing function {name}")
        return self.runtime.call(name, *arguments)

    def remove_me(self) -> None:
        self.rule_remove_me += 1

    def start_cycle(self) -> None:
        self.cycle_starts += 1

    def show_selector(self, model):
        self.selector_models.append(model)
        return self.selector_result

    def show_confirmation(self, model):
        self.confirmation_models.append(model)
        return self.confirmation_result

    def hide_ui(self):
        self.ui_hides += 1
        return True

    def open_create(self, callback):
        self.create_callbacks.append(callback)
        return True

    def open_edit(self, order_id, callback):
        self.edit_calls.append((order_id, callback))
        return True

    @staticmethod
    def invoke(callback, value=None):
        result = callback(value)
        if isinstance(result, LuaResults):
            return result.values[0] if result.values else None
        return result

    def start(self):
        return self.call("BuildOrderStartup_Start")

    def selector_orders(self):
        return self.selector_models[-1]["orders"].array()

    def test_start_collects_local_orders_schedules_pause_and_is_idempotent(self) -> None:
        self.runtime.globals["_mod"]["selectedBuildOrderID"] = "english-zulu"

        self.assertTrue(self.start())
        pause = self.runtime.globals.get("BuildOrderStartup_PauseNextTick")
        self.assertIsNotNone(pause)
        self.assertEqual(self.rule_adds, [pause])
        self.assertEqual(self.sim_rates, [])
        self.assertEqual(len(self.selector_models), 1)
        self.assertEqual(
            [option["id"] for option in self.selector_orders()],
            [
                self.runtime.globals["BUILD_ORDER_STARTUP_NEW_ORDER_ID"],
                "english-alpha-a",
                "english-alpha-b",
                "english-zulu",
            ],
        )
        self.assertFalse(self.selector_orders()[0]["editable"])
        self.assertEqual(self.selector_orders()[0]["label"], "New Build Order")
        self.assertTrue(self.selector_orders()[-1]["selected"])
        self.assertEqual(
            self.runtime.globals["_mod"]["selectedBuildOrderID"],
            "english-zulu",
        )

        self.assertFalse(self.start())
        self.assertEqual(self.rule_adds, [pause])
        self.assertEqual(len(self.selector_models), 1)

        pause()
        self.assertEqual(self.rule_remove_me, 1)
        self.assertEqual(self.sim_rates, [0])

    def test_startup_uses_the_discovery_canonical_civilization_conversion(self) -> None:
        self.runtime.globals["BUILD_ORDER_CATALOG"] = self.runtime.table(
            {
                "ayyubids-feudal": build_order(
                    "ayyubids-feudal", "Feudal", "ayyubids"
                )
            }
        )
        self.runtime.globals["Player_GetRaceName"] = lambda _player: "ayyubid_cmp"
        self.runtime.globals["BuildOrderDiscovery_CanonicalCivID"] = (
            lambda race_name: "ayyubids"
            if race_name == "ayyubid_cmp"
            else race_name.lower()
        )

        compatible = self.call("BuildOrderStartup_CollectCompatible")

        self.assertEqual(compatible.array(), ["ayyubids-feudal"])

    def test_select_changes_state_without_resuming_and_edit_cancel_restores_it(self) -> None:
        self.start()
        self.assertTrue(
            self.call("BuildOrderStartup_Select", {"id": "english-alpha-a"})
        )
        state = self.runtime.globals["_mod"]
        self.assertEqual(state["selectedBuildOrderID"], "english-alpha-a")
        self.assertEqual(self.sim_rates, [])
        self.assertEqual(self.objective_starts, [])
        self.assertTrue(self.selector_orders()[1]["selected"])

        self.assertTrue(
            self.call("BuildOrderStartup_Edit", {"id": "english-alpha-a"})
        )
        self.assertEqual(self.edit_calls[0][0], "english-alpha-a")
        self.assertEqual(state["selectedBuildOrderID"], "english-alpha-a")
        self.invoke(self.edit_calls[0][1], None)
        self.assertEqual(state["selectedBuildOrderID"], "english-alpha-a")
        self.assertTrue(self.selector_orders()[1]["selected"])

    def test_create_cancel_restores_prior_selection_and_save_selects_saved_id(self) -> None:
        state = self.runtime.globals["_mod"]
        state["selectedBuildOrderID"] = "english-zulu"
        self.start()

        self.assertTrue(self.call("BuildOrderStartup_Create"))
        self.assertEqual(state["selectedBuildOrderID"], "english-zulu")
        self.invoke(self.create_callbacks[-1], None)
        self.assertEqual(state["selectedBuildOrderID"], "english-zulu")
        self.assertTrue(self.selector_orders()[-1]["selected"])

        self.assertTrue(self.call("BuildOrderStartup_Create"))
        saved_id = "english-saved"
        self.catalog[saved_id] = build_order(saved_id, "Saved")
        self.runtime.globals["BUILD_ORDER_CATALOG"][saved_id] = self.runtime.table(
            self.catalog[saved_id]
        )
        self.invoke(self.create_callbacks[-1], saved_id)
        self.assertEqual(state["selectedBuildOrderID"], saved_id)
        saved_option = next(
            option for option in self.selector_orders() if option["id"] == saved_id
        )
        self.assertTrue(saved_option["selected"])

    def test_contextual_action_creates_new_and_edits_stored_orders(self) -> None:
        self.start()

        self.assertTrue(
            self.call(
                "BuildOrderStartup_Action",
                {"id": self.runtime.globals["BUILD_ORDER_STARTUP_NEW_ORDER_ID"]},
            )
        )
        self.assertEqual(len(self.create_callbacks), 1)
        self.invoke(self.create_callbacks[-1], None)

        self.assertTrue(
            self.call("BuildOrderStartup_Action", {"id": "english-alpha-a"})
        )
        self.assertEqual(self.edit_calls[-1][0], "english-alpha-a")

    def test_selected_order_unpauses_once_and_is_the_only_objective_start(self) -> None:
        self.start()
        self.call("BuildOrderStartup_Select", {"id": "english-alpha-a"})

        self.assertTrue(self.call("BuildOrderStartup_Unpause"))
        self.assertEqual(len(self.objective_starts), 1)
        selected, player = self.objective_starts[0]
        self.assertEqual(selected["id"], "english-alpha-a")
        self.assertEqual(player, "local-player")
        self.assertEqual(self.sim_rates, [8])
        self.assertEqual(self.cycle_starts, 1)
        self.assertEqual(self.ui_hides, 1)

        self.assertFalse(self.call("BuildOrderStartup_Unpause"))
        self.assertEqual(len(self.objective_starts), 1)
        self.assertEqual(self.sim_rates, [8])
        self.assertEqual(self.cycle_starts, 1)

        start_selected = function_body(
            self.source, "BuildOrderStartup_StartSelected"
        )
        self.assertIn("BuildOrder_Start(buildOrder, localPlayer)", start_selected)
        self.assertEqual(self.source.count("BuildOrder_Start("), 1)

    def test_new_build_order_unpauses_without_objectives_or_confirmation(self) -> None:
        self.start()

        self.assertTrue(self.call("BuildOrderStartup_Unpause"))
        self.assertEqual(self.confirmation_models, [])
        self.assertEqual(self.sim_rates, [8])
        self.assertEqual(self.cycle_starts, 1)
        self.assertEqual(self.objective_starts, [])
        self.assertFalse(self.call("BuildOrderStartup_Unpause"))
        self.assertEqual(self.sim_rates, [8])
        self.assertEqual(self.cycle_starts, 1)

    def test_missing_selection_returns_to_selector_without_resuming(self) -> None:
        state = self.runtime.globals["_mod"]
        state["selectedBuildOrderID"] = "english-missing"
        self.assertTrue(self.start())
        self.assertEqual(
            self.selector_models[-1]["message"],
            f"${MOD_NAMESPACE}:51",
        )
        self.assertEqual(state["selectedBuildOrderID"], "english-missing")

        self.assertFalse(self.call("BuildOrderStartup_Unpause"))
        self.assertEqual(self.sim_rates, [])
        self.assertEqual(self.objective_starts, [])
        self.assertEqual(self.selector_models[-1]["message"], f"${MOD_NAMESPACE}:51")

        self.assertFalse(
            self.call("BuildOrderStartup_Select", {"id": "not-in-selector"})
        )
        self.assertEqual(state["selectedBuildOrderID"], "english-missing")

    def test_wrong_civilization_selection_uses_mismatch_message_without_resuming(
        self,
    ) -> None:
        state = self.runtime.globals["_mod"]
        state["selectedBuildOrderID"] = "french-alpha"

        self.assertTrue(self.start())
        self.assertEqual(
            self.selector_models[-1]["message"],
            f"${MOD_NAMESPACE}:52",
        )
        self.assertEqual(state["selectedBuildOrderID"], "french-alpha")

        self.assertFalse(self.call("BuildOrderStartup_Unpause"))
        self.assertEqual(self.selector_models[-1]["message"], f"${MOD_NAMESPACE}:52")
        self.assertEqual(self.sim_rates, [])
        self.assertEqual(self.objective_starts, [])

    def test_ui_creation_failure_uses_two_choice_escape_and_never_auto_resumes(self) -> None:
        self.selector_result = False
        self.start()
        self.assertEqual(len(self.message_box_text), 1)
        enabled = [
            arguments
            for arguments in self.message_box_buttons
            if len(arguments) == 5 and arguments[4] is True
        ]
        self.assertEqual(
            [arguments[0] for arguments in enabled], ["button-1", "button-2"]
        )
        self.assertEqual(self.sim_rates, [])
        self.rule_adds[0]()
        self.assertEqual(self.sim_rates, [0])

        _, fallback_callback = self.message_box_callbacks[-1]
        self.invoke(fallback_callback, "button-2")
        self.assertEqual(self.sim_rates, [0])
        self.assertEqual(self.objective_starts, [])
        self.assertGreaterEqual(len(self.message_box_callbacks), 2)

        _, fallback_callback = self.message_box_callbacks[-1]
        self.invoke(fallback_callback, "button-1")
        self.assertEqual(self.sim_rates, [0, 8])
        self.assertEqual(self.cycle_starts, 1)
        self.assertEqual(self.objective_starts, [])

    def test_stop_is_idempotent_and_cancels_pending_pause_without_resuming(self) -> None:
        self.start()
        pause = self.runtime.globals["BuildOrderStartup_PauseNextTick"]

        self.assertTrue(self.call("BuildOrderStartup_Stop"))
        self.assertFalse(self.call("BuildOrderStartup_Stop"))
        self.assertEqual(self.rule_removes.count(pause), 2)
        self.assertEqual(self.ui_hides, 1)
        self.assertEqual(self.sim_rates, [])
        state = self.runtime.globals["_mod"]
        self.assertFalse(state["startupStarted"])
        self.assertFalse(state["startupAwaitingChoice"])
        self.assertEqual(state["compatibleBuildOrderIDs"].array(), [])

    def test_stop_preserves_non_nil_selection_for_a_later_start(self) -> None:
        state = self.runtime.globals["_mod"]
        state["selectedBuildOrderID"] = "english-zulu"
        self.start()

        self.assertTrue(self.call("BuildOrderStartup_Stop"))
        self.assertEqual(state["selectedBuildOrderID"], "english-zulu")

        self.assertTrue(self.start())
        self.assertEqual(state["selectedBuildOrderID"], "english-zulu")
        selected = [
            option
            for option in self.selector_orders()
            if option["selected"] is True
        ]
        self.assertEqual([option["id"] for option in selected], ["english-zulu"])


class BuildOrderStartupContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.startup = STARTUP_PATH.read_text(encoding="utf-8")
        cls.main = MAIN_PATH.read_text(encoding="utf-8")

    def test_startup_registers_only_local_ui_callbacks_and_no_network_events(self) -> None:
        callbacks = function_body(self.startup, "BuildOrderStartup_Callbacks")
        for name in (
            "BuildOrderStartup_Select",
            "BuildOrderStartup_Edit",
            "BuildOrderStartup_Create",
            "BuildOrderStartup_Unpause",
            "BuildOrderStartup_Cancel",
            "BuildOrderStartup_ConfirmNoOrder",
        ):
            self.assertIn(name, callbacks)
        self.assertIn("Game_GetLocalPlayer()", self.startup)
        self.assertNotRegex(self.startup, r"\b(?:Event|Network|Net)_")

    def test_main_delegates_load_and_cleans_every_system_once(self) -> None:
        start = function_body(self.main, "Mod_Start")
        self.assertEqual(
            start.count("BuildOrderDatastore_Load(BuildOrderStartup_Start)"), 1
        )

        game_over = function_body(self.main, "Mod_OnGameOver")
        for call in (
            "BuildOrderDatastore_Stop()",
            "BuildOrderStartup_Stop()",
            "BuildOrderEditor_Stop()",
            "BuildOrder_Stop()",
            "Mod_StopSimspeedCycle()",
        ):
            with self.subTest(call=call):
                self.assertEqual(game_over.count(call), 1)

    def test_startup_visible_strings_use_stable_fully_qualified_localization(self) -> None:
        rows = csv_rows(LOCDB_PATH)
        expected = {
            29: "Choose a Build Order",
            31: "New Build Order",
            44: "Continue without a build order?",
            45: "No build-order objectives will be started.",
            47: "Build Order UI Unavailable",
            48: "The build-order screen could not be opened. Continue without build-order objectives?",
            49: "Continue Without Build Order",
            50: "Stay Paused",
            51: "The selected build order is no longer available. Choose another option.",
            52: "The selected build order is not compatible with the current civilization.",
        }
        for loc_id, text in expected.items():
            with self.subTest(loc_id=loc_id):
                self.assertIn(loc_id, rows)
                self.assertEqual(rows[loc_id][6], text)
                if loc_id == 31:
                    self.assertIn('"New Build Order"', self.startup)
                else:
                    self.assertIn(f'"${MOD_NAMESPACE}:{loc_id}"', self.startup)


class BuildOrderGameOverBehaviorTests(unittest.TestCase):
    def test_game_over_runs_ui_teardown_once_through_editor_stop(self) -> None:
        editor = EDITOR_PATH.read_text(encoding="utf-8")
        main = MAIN_PATH.read_text(encoding="utf-8")
        game_over = "function Mod_OnGameOver()\n" + function_body(
            main, "Mod_OnGameOver"
        )
        runtime = ScarRuntime(editor + "\n" + game_over)
        calls = {
            "datastore": 0,
            "startup": 0,
            "discovery": 0,
            "ui": 0,
            "objectives": 0,
            "simspeed": 0,
        }

        def record(name):
            def callback():
                calls[name] += 1

            return callback

        runtime.globals["BuildOrderDatastore_Stop"] = record("datastore")
        runtime.globals["BuildOrderStartup_Stop"] = record("startup")
        runtime.globals["BuildOrderDiscovery_Clear"] = record("discovery")
        runtime.globals["BuildOrderEditorUI_Stop"] = record("ui")
        runtime.globals["BuildOrder_Stop"] = record("objectives")
        runtime.globals["Mod_StopSimspeedCycle"] = record("simspeed")
        runtime.globals["BUILD_ORDER_EDITOR_STATE"]["draft"] = runtime.table(
            {"title": "Open draft"}
        )

        runtime.call("Mod_OnGameOver")

        self.assertEqual(
            calls,
            {
                "datastore": 1,
                "startup": 1,
                "discovery": 1,
                "ui": 1,
                "objectives": 1,
                "simspeed": 1,
            },
        )
        self.assertIsNone(runtime.globals["BUILD_ORDER_EDITOR_STATE"]["draft"])


if __name__ == "__main__":
    unittest.main()
