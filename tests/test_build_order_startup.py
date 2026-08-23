import csv
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from tools.build_mod import BuildPaths
from tools.build_orders.compiler import compile_directory
from tools.build_orders.emitters import emit_outputs, reset_outputs


ROOT = Path(__file__).resolve().parents[1]
STARTUP_PATH = ROOT / "assets" / "scar" / "build_orders" / "startup.scar"
MAIN_PATH = ROOT / "assets" / "scar" / "winconditions" / "Macro Trainer.scar"
LOCDB_PATH = (
    ROOT / "build" / "templates" / "assets" / "locdb" / "Macro Trainer_en.csv"
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

    def test_no_selection_runs_only_the_enabled_cycle_or_alerts(self) -> None:
        start = function_body(self.startup, "BuildOrderStartup_Start")
        self.assertRegex(
            start,
            r"if selectedID == nil then\s*"
            r"if _mod\.simspeedEnabled then\s*"
            r"Mod_StartSimspeedCycle\(\)\s*"
            r"else\s*"
            r"BuildOrderStartup_ShowNoSystemsError\(\)\s*"
            r"end\s*return\s*end",
        )
        none_branch = start[: start.index("local buildOrder")]
        self.assertNotIn("BuildOrder_Start(", none_branch)
        self.assertNotIn("BuildOrderStartup_ShowInvalidBuildError", none_branch)

    def test_matching_build_starts_objectives_and_conditionally_starts_cycle(self) -> None:
        start = function_body(self.startup, "BuildOrderStartup_Start")
        self.assertIn("local buildOrder = BUILD_ORDER_CATALOG[selectedID]", start)
        self.assertIn("local localPlayer = Game_GetLocalPlayer()", start)
        self.assertIn(
            "local actualCiv = string.lower(Player_GetRaceName(localPlayer))", start
        )
        self.assertRegex(
            start,
            r"BuildOrder_Start\(buildOrder, localPlayer\)\s*"
            r"if _mod\.simspeedEnabled then\s*"
            r"Mod_StartSimspeedCycle\(\)\s*end",
        )
        self.assert_order(
            start,
            "BuildOrderStartup_ShowInvalidBuildError(buildOrder, actualCiv)",
            "BuildOrder_Start(buildOrder, localPlayer)",
        )

    def test_missing_catalog_and_civilization_mismatch_use_distinct_alerts(self) -> None:
        start = function_body(self.startup, "BuildOrderStartup_Start")
        self.assertIn(
            "if buildOrder == nil then",
            start,
        )
        self.assertIn(
            "BuildOrderStartup_ShowMissingBuildError()", start
        )
        self.assertIn(
            "if actualCiv ~= string.lower(buildOrder.civ) then", start
        )
        self.assertIn("BuildOrderStartup_ShowInvalidBuildError(buildOrder, actualCiv)", start)

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

    def test_templar_pbgname_survives_generation_and_matches_case_insensitively(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            templates = root / "templates"
            templates.mkdir()
            rdo_template = templates / "Macro Trainer.rdo"
            locdb_template = templates / "Macro Trainer_en.csv"
            rdo_template.write_text(
                "<!-- GENERATED_BUILD_ORDER_ENUM_ITEMS -->\n", encoding="utf-8"
            )
            shutil.copyfile(LOCDB_PATH, locdb_template)
            orders = root / "orders"
            orders.mkdir()
            (orders / "upper.yaml").write_text(
                "civ: templar\ntitle: Case Test\nsteps:\n  - hints:\n      - Scout\n",
                encoding="utf-8",
            )
            paths = BuildPaths(
                root,
                rdo_template,
                locdb_template,
                root / "assets" / "Macro Trainer.rdo",
                root / "assets" / "Macro Trainer_en.csv",
                root / "assets" / "generated" / "build_orders.scar",
            )
            reset_outputs(paths)
            emit_outputs(compile_directory(orders), paths)

            generated = paths.scar_output.read_text(encoding="utf-8")
            self.assertIn('civ = "templar"', generated)
            start = function_body(self.startup, "BuildOrderStartup_Start")
            self.assertIn(
                "actualCiv ~= string.lower(buildOrder.civ)", start
            )

    def test_alert_schedules_next_tick_pause_after_showing_continue_button(self) -> None:
        show = function_body(self.startup, "BuildOrderStartup_ShowError")
        self.assertIn("_mod.buildOrderDisabled = true", show)
        self.assertIn("_mod.startupAlertOpen = true", show)
        self.assertNotIn("Misc_SetSimRate(0)", show)
        self.assertIn("UI_MessageBoxSetText(title, message)", show)
        self.assertRegex(
            show,
            r"UI_MessageBoxSetButton\(\s*DB_Button1,\s*"
            r'"Continue Without Build Order",\s*'
            r'"Resume the match without build-order objectives\.",\s*'
            r'"",\s*true\s*\)',
        )
        self.assertIn(
            "UI_MessageBoxShow(DC_Default, BuildOrderStartup_Continue)", show
        )
        self.assertEqual(self.startup.count("UI_MessageBoxSetButton("), 1)
        for button in ("DB_Button2", "DB_Button3", "DB_Button4"):
            self.assertNotIn(button, self.startup)
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

    def test_continue_is_idempotent_and_only_starts_enabled_cycle(self) -> None:
        resume = function_body(self.startup, "BuildOrderStartup_Continue")
        self.assertIn(
            "if not _mod.startupAlertOpen or button ~= DB_Button1 then", resume
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

    def test_startup_never_mutates_selected_or_cycle_settings(self) -> None:
        self.assertNotRegex(self.startup, r"_mod\.selectedBuildOrderID\s*=")
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
        self.assertEqual(start.count("BuildOrderStartup_Start()"), 1)
        self.assertNotIn("Mod_StartSimspeedCycle()", start)

        game_over = function_body(self.main, "Mod_OnGameOver")
        for call in (
            "BuildOrderStartup_Stop()",
            "BuildOrder_Stop()",
            "Mod_StopSimspeedCycle()",
        ):
            self.assertEqual(game_over.count(call), 1)
        self.assert_order(game_over, "BuildOrderStartup_Stop()", "BuildOrder_Stop()")
        self.assert_order(game_over, "BuildOrder_Stop()", "Mod_StopSimspeedCycle()")

        stop = function_body(self.startup, "BuildOrderStartup_Stop")
        self.assertIn("_mod.startupAlertOpen = false", stop)
        self.assertIn("Rule_Remove(BuildOrderStartup_PauseNextTick)", stop)
        self.assertNotIn("Mod_StartSimspeedCycle", stop)
        self.assertNotIn("BuildOrder_Start", stop)

    def test_startup_alert_localization_rows_are_stable_and_referenced(self) -> None:
        rows = csv_rows(LOCDB_PATH)
        for identifier in range(25, 29):
            self.assertIn(identifier, rows)
        self.assertEqual(rows[25][-1], "No Training Systems Enabled")
        self.assertEqual(
            rows[26][-1],
            "The mod is not intended to be played with both off.",
        )
        self.assertEqual(rows[27][-1], "Build Order Disabled")
        self.assertEqual(rows[28][-1], "Selected build order is unavailable.")
        for identifier in range(25, 29):
            self.assertIn(
                f'$dfb5645698a84afb91cf7a2dfb0f4a4e:{identifier}', self.startup
            )


if __name__ == "__main__":
    unittest.main()
