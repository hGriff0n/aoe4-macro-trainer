import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATASTORE_PATH = ROOT / "assets" / "scar" / "build_orders" / "datastore.scar"
MAIN_PATH = ROOT / "assets" / "scar" / "winconditions" / "Macro Trainer.scar"


def function_body(source: str, name: str) -> str:
    match = re.search(
        rf"function {re.escape(name)}\([^)]*\)(.*?)(?=^function |\Z)",
        source,
        re.MULTILINE | re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"missing function {name}")
    return match.group(1)


class BuildOrderDatastoreContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.datastore = (
            DATASTORE_PATH.read_text(encoding="utf-8")
            if DATASTORE_PATH.exists()
            else ""
        )
        cls.main = MAIN_PATH.read_text(encoding="utf-8")

    def test_load_waits_one_rule_tick_then_retrieves_named_global(self) -> None:
        load = function_body(self.datastore, "BuildOrderDatastore_Load")
        finish = function_body(self.datastore, "BuildOrderDatastore_FinishLoad")

        self.assertIn(
            'Game_LoadTextDataStore(BUILD_ORDER_DATASTORE_ID, "")', load
        )
        self.assertIn("Rule_Add(BuildOrderDatastore_FinishLoad)", load)
        self.assertNotIn("Game_RetrieveTableData", load)
        self.assertIn("Rule_RemoveMe()", finish)
        self.assertIn(
            "Game_RetrieveTableData(BUILD_ORDER_DATASTORE_ID, false)", finish
        )
        self.assertIn("local loaded = _G[BUILD_ORDER_DATASTORE_ID]", finish)

    def test_main_imports_datastore_after_bundled_catalog_before_startup(self) -> None:
        bundled = 'import("generated/build_orders.scar")'
        datastore = 'import("build_orders/datastore.scar")'
        startup = 'import("build_orders/startup.scar")'

        self.assertEqual(self.main.count(datastore), 1)
        self.assertLess(self.main.index(bundled), self.main.index(datastore))
        self.assertLess(self.main.index(datastore), self.main.index(startup))

    def test_mod_start_waits_for_datastore_and_game_over_cancels_load(self) -> None:
        start = function_body(self.main, "Mod_Start")
        game_over = function_body(self.main, "Mod_OnGameOver")

        self.assertEqual(
            start.count("BuildOrderDatastore_Load(BuildOrderStartup_Start)"), 1
        )
        self.assertNotIn("BuildOrderStartup_Start()", start)
        self.assertEqual(game_over.count("BuildOrderDatastore_Stop()"), 1)
        self.assertLess(
            game_over.index("BuildOrderDatastore_Stop()"),
            game_over.index("BuildOrderStartup_Stop()"),
        )

    def test_only_supported_catalog_records_overlay_bundled_ids(self) -> None:
        merge = function_body(self.datastore, "BuildOrderDatastore_Merge")

        self.assertIn(
            "loaded.schema_version ~= BUILD_ORDER_DATASTORE_SCHEMA_VERSION", merge
        )
        self.assertIn('type(loaded.build_orders) ~= "table"', merge)
        self.assertIn("for id, buildOrder in pairs(loaded.build_orders) do", merge)
        self.assertIn(
            "if BuildOrderDatastore_IsValidOrder(id, buildOrder) then", merge
        )
        self.assertIn("BUILD_ORDER_CATALOG[id] = buildOrder", merge)

    def test_order_validation_rejects_key_id_and_required_shape_mutations(self) -> None:
        validate = function_body(
            self.datastore, "BuildOrderDatastore_IsValidOrder"
        )

        self.assertIn('type(id) ~= "string" or id == ""', validate)
        self.assertIn('type(buildOrder) ~= "table"', validate)
        self.assertIn("buildOrder.id ~= id", validate)
        self.assertIn('type(buildOrder.civ) ~= "string" or buildOrder.civ == ""', validate)
        self.assertIn(
            'type(buildOrder.title) ~= "string" or buildOrder.title == ""',
            validate,
        )
        self.assertIn('type(buildOrder.steps) ~= "table"', validate)

    def test_invalid_store_reaches_callback_without_clearing_bundled_catalog(self) -> None:
        finish = function_body(self.datastore, "BuildOrderDatastore_FinishLoad")

        self.assertNotIn("BUILD_ORDER_CATALOG = {}", self.datastore)
        self.assertIn("BuildOrderDatastore_Merge(loaded)", finish)
        self.assertIn("BuildOrderDatastore_Complete()", finish)

    def test_stop_and_complete_guards_prevent_late_or_duplicate_startup(self) -> None:
        complete = function_body(self.datastore, "BuildOrderDatastore_Complete")
        stop = function_body(self.datastore, "BuildOrderDatastore_Stop")

        self.assertIn("local onComplete = BUILD_ORDER_DATASTORE_ON_COMPLETE", complete)
        self.assertIn("BUILD_ORDER_DATASTORE_ON_COMPLETE = nil", complete)
        self.assertIn("BUILD_ORDER_DATASTORE_LOADING = false", complete)
        self.assertIn('if type(onComplete) == "function" then', complete)
        self.assertIn("onComplete()", complete)
        self.assertIn("Rule_Remove(BuildOrderDatastore_FinishLoad)", stop)
        self.assertIn("BUILD_ORDER_DATASTORE_ON_COMPLETE = nil", stop)
        self.assertIn("BUILD_ORDER_DATASTORE_LOADING = false", stop)


if __name__ == "__main__":
    unittest.main()
