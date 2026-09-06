import csv
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STARTUP_PATH = ROOT / "assets" / "scar" / "build_orders" / "startup.scar"
MAIN_PATH = ROOT / "assets" / "scar" / "winconditions" / "Macro Trainer.scar"
LOCDB_PATH = (
    ROOT / "assets" / "locdb" / "Macro Trainer_en.csv"
)


def function_body(source: str, name: str) -> str:
    match = re.search(
        rf"function {re.escape(name)}\([^)]*\)(.*?)(?=^function |\Z)",
        source,
        re.MULTILINE | re.DOTALL,
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


class BuildOrderStartupContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.startup = (
            STARTUP_PATH.read_text(encoding="utf-8")
            if STARTUP_PATH.exists()
            else ""
        )
        cls.main = MAIN_PATH.read_text(encoding="utf-8")

    def assert_order(self, body: str, first: str, second: str) -> None:
        self.assertLess(body.index(first), body.index(second))

    def test_no_selection_opens_error_with_dynamic_choice(self) -> None:
        start = function_body(self.startup, "BuildOrderStartup_Start")
        self.assertIn("BuildOrderStartup_ShowNoSelectionError()", start)
        self.assertNotIn("selectedBuildOrderID", start)
        self.assertNotIn("BUILD_ORDER_CATALOG", start)
        self.assertNotIn("BuildOrder_Start(", start)
        self.assertNotIn("Mod_StartSimspeedCycle()", start)

    def test_matching_build_starts_objectives_and_conditionally_starts_cycle(self) -> None:
        selected = function_body(self.startup, "BuildOrderStartup_StartSelected")
        self.assertIn("if _mod.buildOrderStarted then", selected)
        self.assertIn("_mod.buildOrderStarted = true", selected)
        self.assertIn("BuildOrder_Start(buildOrder, localPlayer)", selected)
        self.assertRegex(
            selected,
            r"BuildOrder_Start\(buildOrder, localPlayer\)\s*"
            r"if _mod\.simspeedEnabled then\s*"
            r"Mod_StartSimspeedCycle\(\)\s*end",
        )

    def test_missing_catalog_and_civilization_mismatch_use_distinct_alerts(self) -> None:
        selected = function_body(self.startup, "BuildOrderStartup_StartSelected")
        self.assertIn(
            "actualCiv ~= string.lower(buildOrder.civ)", selected
        )
        self.assertIn(
            "BuildOrderStartup_ShowInvalidBuildError(buildOrder or { civ = \"unknown\" }, actualCiv)",
            selected,
        )

        invalid = function_body(
            self.startup, "BuildOrderStartup_ShowInvalidBuildError"
        )
        self.assertIn("buildOrder.civ", invalid)
        self.assertIn("actualCiv", invalid)
        self.assertIn(
            '"Selected build order for " .. buildOrder.civ .. " but playing as " .. actualCiv',
            invalid,
        )
        self.assertIn("BuildOrderStartup_ShowError(", invalid)

        missing = function_body(
            self.startup, "BuildOrderStartup_ShowMissingBuildError"
        )
        self.assertIn("BUILD_ORDER_STARTUP_MISSING_BUILD_TITLE", missing)

    def test_error_modal_resets_buttons_and_offers_dynamic_choice(self) -> None:
        show = function_body(self.startup, "BuildOrderStartup_ShowError")
        self.assertIn("_mod.buildOrderDisabled = true", show)
        self.assertIn("_mod.startupAlertOpen = true", show)
        self.assertNotIn("Misc_SetSimRate(0)", show)
        self.assertIn("UI_MessageBoxSetText(title, message)", show)
        self.assertIn("BuildOrderStartup_ResetButtons()", show)
        self.assertIn("BuildOrderStartup_CollectCompatible()", show)
        self.assertRegex(
            show,
            r"UI_MessageBoxSetButton\(\s*DB_Button1,\s*"
            r'"Continue Without Build Order",\s*'
            r'"Resume the match without build-order objectives\.",\s*'
            r'"",\s*true\s*\)',
        )
        self.assertRegex(
            show,
            r"UI_MessageBoxSetButton\(\s*DB_Button2,\s*"
            r'"Choose Build Order",\s*'
            r'"Select from build orders loaded for this civilization\.",\s*'
            r'"",\s*#_mod\.compatibleBuildOrderIDs > 0\s*\)',
        )
        self.assertIn(
            "UI_MessageBoxShow(DC_Default, BuildOrderStartup_HandleErrorChoice)",
            show,
        )

        reset = function_body(self.startup, "BuildOrderStartup_ResetButtons")
        for button in ("DB_Button1", "DB_Button2", "DB_Button3", "DB_Button4"):
            self.assertRegex(
                reset,
                rf"UI_MessageBoxSetButton\(\s*{button},\s*\"\",\s*\"\",\s*\"\",\s*false\s*\)",
            )
        self.assertIn("Rule_Remove(BuildOrderStartup_PauseNextTick)", show)
        self.assertIn("Rule_Add(BuildOrderStartup_PauseNextTick)", show)
        self.assert_order(
            show,
            "Rule_Remove(BuildOrderStartup_PauseNextTick)",
            "Rule_Add(BuildOrderStartup_PauseNextTick)",
        )
        self.assert_order(
            show,
            "UI_MessageBoxShow(",
            "Rule_Add(BuildOrderStartup_PauseNextTick)",
        )

        pause = function_body(self.startup, "BuildOrderStartup_PauseNextTick")
        self.assertIn("Rule_RemoveMe()", pause)
        self.assertRegex(
            pause,
            r"Rule_RemoveMe\(\)\s*"
            r"if _mod\.startupAlertOpen then\s*"
            r"Misc_SetSimRate\(0\)\s*end",
        )

    def test_continue_without_order_is_idempotent_and_only_starts_enabled_cycle(self) -> None:
        resume = function_body(
            self.startup, "BuildOrderStartup_ContinueWithoutBuildOrder"
        )
        self.assertIn(
            "if not _mod.startupAlertOpen then", resume
        )
        self.assertIn("_mod.startupAlertOpen = false", resume)
        self.assertIn("Rule_Remove(BuildOrderStartup_PauseNextTick)", resume)
        self.assertIn("Misc_SetSimRate(NORMAL_SIM_RATE)", resume)
        self.assertRegex(
            resume,
            r"if _mod\.simspeedEnabled then\s*"
            r"Mod_StartSimspeedCycle\(\)\s*end",
        )
        self.assertNotIn("BuildOrder_Start(", resume)
        self.assert_order(
            resume, "_mod.startupAlertOpen = false", "Misc_SetSimRate(NORMAL_SIM_RATE)"
        )
        self.assert_order(
            resume,
            "_mod.startupAlertOpen = false",
            "Rule_Remove(BuildOrderStartup_PauseNextTick)",
        )
        self.assert_order(
            resume,
            "Rule_Remove(BuildOrderStartup_PauseNextTick)",
            "Misc_SetSimRate(NORMAL_SIM_RATE)",
        )

        handler = function_body(self.startup, "BuildOrderStartup_HandleErrorChoice")
        self.assertIn("if not _mod.startupAlertOpen then", handler)
        self.assertIn("if button == DB_Button1 then", handler)
        self.assertIn("BuildOrderStartup_ContinueWithoutBuildOrder()", handler)
        self.assertIn("elseif button == DB_Button2", handler)
        self.assertIn("BuildOrderStartup_ShowChooser()", handler)

    def test_compatible_choices_filter_local_civ_and_sort_title_then_id(self) -> None:
        collect = function_body(self.startup, "BuildOrderStartup_CollectCompatible")
        compare = function_body(self.startup, "BuildOrderStartup_ChoiceComesBefore")

        self.assertIn("Player_GetRaceName(Game_GetLocalPlayer())", collect)
        self.assertIn("string.lower(buildOrder.civ) == actualCiv", collect)
        self.assertIn("BuildOrderStartup_ChoiceComesBefore(id, existingID)", collect)
        self.assertIn("string.lower(left.title)", compare)
        self.assertIn("string.lower(right.title)", compare)
        self.assertIn("return leftID < rightID", compare)

    def test_chooser_configures_use_next_previous_and_cancel(self) -> None:
        chooser = function_body(self.startup, "BuildOrderStartup_ShowChooser")

        self.assertIn("BuildOrderStartup_ResetButtons()", chooser)
        self.assertIn('local message = "[" .. _mod.buildOrderChoiceIndex .. "/" .. count .. "] " .. buildOrder.title', chooser)
        self.assertIn('message = message .. "\\nCivilization: " .. buildOrder.civ', chooser)
        self.assertIn('if type(buildOrder.source) == "string" and buildOrder.source ~= "" then', chooser)
        self.assertIn('message = message .. "\\nSource: " .. buildOrder.source', chooser)
        for button, label in (
            ("DB_Button1", "Use This Build Order"),
            ("DB_Button2", "Next"),
            ("DB_Button3", "Previous"),
            ("DB_Button4", "Cancel"),
        ):
            self.assertRegex(
                chooser,
                rf'UI_MessageBoxSetButton\(\s*{button},\s*"{label}"',
            )

    def test_navigation_wraps_and_selection_starts_once(self) -> None:
        handler = function_body(
            self.startup, "BuildOrderStartup_HandleChooserChoice"
        )

        self.assertIn("if not _mod.startupAlertOpen then", handler)
        self.assertIn("BuildOrderStartup_WrapChoiceIndex", handler)
        self.assertIn("_mod.selectedBuildOrderID = selectedID", handler)
        self.assertIn("BuildOrderStartup_StartSelected(buildOrder)", handler)
        self.assertIn("BuildOrderStartup_ShowError(", handler)

        wrap = function_body(self.startup, "BuildOrderStartup_WrapChoiceIndex")
        self.assertIn("if index < 1 then", wrap)
        self.assertIn("return count", wrap)
        self.assertIn("if index > count then", wrap)
        self.assertIn("return 1", wrap)

    def test_startup_only_mutates_selection_when_chooser_is_confirmed(self) -> None:
        assignments = re.findall(r"_mod\.selectedBuildOrderID\s*=", self.startup)
        self.assertEqual(len(assignments), 1)
        chooser = function_body(
            self.startup, "BuildOrderStartup_HandleChooserChoice"
        )
        self.assertIn("_mod.selectedBuildOrderID = selectedID", chooser)
        self.assertNotRegex(self.startup, r"_mod\.simspeedEnabled\s*=")
        self.assertNotIn("Core_OnGameOver", self.startup)

    def test_main_delegates_start_and_cleans_each_system_once(self) -> None:
        startup_import = 'import("build_orders/startup.scar")'
        self.assertIn(startup_import, self.main)
        self.assertLess(
            self.main.index("Rule_AddOneShot(nextRule, phaseDuration)"),
            self.main.index(startup_import),
        )

        start = function_body(self.main, "Mod_Start")
        self.assertEqual(
            start.count("BuildOrderDatastore_Load(BuildOrderStartup_Start)"), 1
        )
        self.assertNotIn("BuildOrderStartup_Start()", start)
        self.assertNotIn("Mod_StartSimspeedCycle()", start)

        game_over = function_body(self.main, "Mod_OnGameOver")
        for call in (
            "BuildOrderDatastore_Stop()",
            "BuildOrderStartup_Stop()",
            "BuildOrder_Stop()",
            "Mod_StopSimspeedCycle()",
        ):
            self.assertEqual(game_over.count(call), 1)
        self.assert_order(
            game_over, "BuildOrderDatastore_Stop()", "BuildOrderStartup_Stop()"
        )
        self.assert_order(game_over, "BuildOrderStartup_Stop()", "BuildOrder_Stop()")
        self.assert_order(game_over, "BuildOrder_Stop()", "Mod_StopSimspeedCycle()")

        stop = function_body(self.startup, "BuildOrderStartup_Stop")
        self.assertIn("_mod.startupAlertOpen = false", stop)
        self.assertIn("_mod.compatibleBuildOrderIDs = {}", stop)
        self.assertIn("Rule_Remove(BuildOrderStartup_PauseNextTick)", stop)
        self.assertNotIn("Mod_StartSimspeedCycle", stop)
        self.assertNotIn("BuildOrder_Start", stop)

    def test_startup_alert_localization_rows_are_stable_and_referenced(self) -> None:
        rows = csv_rows(LOCDB_PATH)
        for identifier in range(25, 31):
            self.assertIn(identifier, rows)
        self.assertEqual(rows[25][-1], "No Training Systems Enabled")
        self.assertEqual(
            rows[26][-1],
            "The mod is not intended to be played with both off.",
        )
        self.assertEqual(rows[27][-1], "Build Order Disabled")
        self.assertEqual(rows[28][-1], "Selected build order is unavailable.")
        self.assertEqual(rows[29][-1], "Choose a Build Order")
        self.assertEqual(
            rows[30][-1],
            "Choose a build order loaded from the player datastore.",
        )
        for identifier in range(25, 31):
            self.assertIn(
                f'$dfb5645698a84afb91cf7a2dfb0f4a4e:{identifier}', self.startup
            )


if __name__ == "__main__":
    unittest.main()
