import re
import unittest
from pathlib import Path

from tests.scar_runtime import LuaResults, ScarRuntime


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

    def test_load_waits_one_rule_tick_then_retrieves_returned_catalog(self) -> None:
        load = function_body(self.datastore, "BuildOrderDatastore_Load")
        finish = function_body(self.datastore, "BuildOrderDatastore_FinishLoad")

        self.assertIn(
            'Game_LoadTextDataStore(BUILD_ORDER_DATASTORE_ID, "")', load
        )
        self.assertIn("Rule_Add(BuildOrderDatastore_FinishLoad)", load)
        self.assertNotIn("Game_RetrieveTableData", load)
        self.assertIn("Rule_RemoveMe()", finish)
        self.assertIn(
            "local loaded = Game_RetrieveTableData(BUILD_ORDER_DATASTORE_ID, false)",
            finish,
        )

    def test_main_imports_datastore_as_the_only_catalog_before_startup(self) -> None:
        datastore = 'import("build_orders/datastore.scar")'
        startup = 'import("build_orders/startup.scar")'

        self.assertNotIn('import("generated/build_orders.scar")', self.main)
        self.assertEqual(self.main.count(datastore), 1)
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

    def test_only_supported_datastore_records_populate_the_runtime_catalog(self) -> None:
        replace = function_body(self.datastore, "BuildOrderDatastore_Replace")

        self.assertIn(
            "loaded.schema_version ~= BUILD_ORDER_DATASTORE_SCHEMA_VERSION", replace
        )
        self.assertIn('type(loaded.build_orders) ~= "table"', replace)
        self.assertIn("BUILD_ORDER_CATALOG = {}", replace)
        self.assertIn("for id, buildOrder in pairs(loaded.build_orders) do", replace)
        self.assertIn(
            "if BuildOrderDatastore_IsValidOrder(id, buildOrder) then", replace
        )
        self.assertIn("BUILD_ORDER_CATALOG[id] = buildOrder", replace)

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
        self.assertIn("#buildOrder.steps == 0", validate)
        self.assertIn(
            "if not BuildOrderDatastore_IsValidStep(step) then", validate
        )

        step = function_body(self.datastore, "BuildOrderDatastore_IsValidStep")
        self.assertIn('type(step.title) ~= "string" or step.title == ""', step)
        self.assertIn('type(step.checks) ~= "table" or #step.checks == 0', step)
        self.assertIn(
            "if not BuildOrderDatastore_IsValidCheck(check) then", step
        )

        check = function_body(self.datastore, "BuildOrderDatastore_IsValidCheck")
        self.assertIn('type(check.id) ~= "string" or check.id == ""', check)
        self.assertIn('type(check.kind) ~= "string" or check.kind == ""', check)
        self.assertIn('type(check.title) ~= "string" or check.title == ""', check)
        self.assertIn('type(check.optional) ~= "boolean"', check)
        self.assertIn('type(check.payload) ~= "table"', check)

    def test_invalid_store_reaches_callback_with_an_empty_runtime_catalog(self) -> None:
        finish = function_body(self.datastore, "BuildOrderDatastore_FinishLoad")

        self.assertIn("BUILD_ORDER_CATALOG = {}", self.datastore)
        self.assertIn("BuildOrderDatastore_Replace(loaded)", finish)
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

    def test_apply_rejects_invalid_orders_and_other_record_collisions(self) -> None:
        apply = function_body(self.datastore, "BuildOrderDatastore_Apply")

        self.assertIn(
            "if not BuildOrderDatastore_IsValidOrder(newID, buildOrder) then",
            apply,
        )
        self.assertIn('return false, "invalid_build_order"', apply)
        self.assertIn(
            "if BUILD_ORDER_CATALOG[newID] ~= nil and newID ~= originalID then",
            apply,
        )
        self.assertIn('return false, "id_collision"', apply)

    def test_apply_allows_an_existing_record_to_keep_its_id(self) -> None:
        apply = function_body(self.datastore, "BuildOrderDatastore_Apply")

        self.assertIn("newID ~= originalID", apply)
        self.assertNotIn(
            "if BUILD_ORDER_CATALOG[newID] ~= nil then", apply
        )

    def test_apply_replaces_or_renames_the_catalog_entry_then_saves_once(self) -> None:
        apply = function_body(self.datastore, "BuildOrderDatastore_Apply")

        self.assertIn(
            "if originalID ~= nil and originalID ~= newID then", apply
        )
        self.assertIn("BUILD_ORDER_CATALOG[originalID] = nil", apply)
        self.assertIn("BUILD_ORDER_CATALOG[newID] = buildOrder", apply)
        self.assertEqual(apply.count("pcall(BuildOrderDatastore_SaveCatalog)"), 1)
        self.assertIn("BUILD_ORDER_CATALOG[newID] = destinationValue", apply)
        self.assertIn("BUILD_ORDER_CATALOG[originalID] = originalValue", apply)
        self.assertIn('return false, "persistence_error"', apply)
        self.assertIn('return true, ""', apply)

    def test_save_catalog_stores_the_live_catalog_then_saves_the_datastore(self) -> None:
        save = function_body(self.datastore, "BuildOrderDatastore_SaveCatalog")

        self.assertIn("local stored = {", save)
        self.assertIn(
            "schema_version = BUILD_ORDER_DATASTORE_SCHEMA_VERSION,", save
        )
        self.assertIn("build_orders = BUILD_ORDER_CATALOG,", save)
        store = 'Game_StoreTableData(BUILD_ORDER_DATASTORE_ID, stored)'
        persist = 'Game_SaveTextDataStore(BUILD_ORDER_DATASTORE_ID, "")'
        self.assertIn(store, save)
        self.assertIn(persist, save)
        self.assertLess(save.index(store), save.index(persist))


class BuildOrderDatastoreBehaviorTests(unittest.TestCase):
    @staticmethod
    def lua_pcall(function, *arguments):
        try:
            result = function(*arguments)
        except Exception as error:
            return LuaResults((False, str(error)))
        if isinstance(result, LuaResults):
            return LuaResults((True, *result.values))
        return LuaResults((True, result))

    @staticmethod
    def valid_order(identifier: str) -> dict[str, object]:
        return {
            "id": identifier,
            "civ": "english",
            "title": "Persistence",
            "steps": [
                {
                    "title": "Opening",
                    "checks": [
                        {
                            "id": f"{identifier}:1:1",
                            "kind": "hints",
                            "title": "[HINT] Persist",
                            "optional": True,
                            "payload": {"text": "Persist"},
                        }
                    ],
                }
            ],
        }

    def setUp(self) -> None:
        self.runtime = ScarRuntime(DATASTORE_PATH.read_text(encoding="utf-8"))
        self.runtime.globals["pcall"] = self.lua_pcall
        self.failure: str | None = None
        self.store_calls: list[str] = []
        self.save_calls: list[str] = []

        def store(datastore_id, _value) -> None:
            self.store_calls.append(datastore_id)
            if self.failure == "store":
                raise RuntimeError("store failed")

        def save(datastore_id, _path) -> None:
            self.save_calls.append(datastore_id)
            if self.failure == "save":
                raise RuntimeError("save failed")

        self.runtime.globals["Game_StoreTableData"] = store
        self.runtime.globals["Game_SaveTextDataStore"] = save

    def reset_catalog(self):
        original = self.runtime.table(self.valid_order("old"))
        replacement = self.runtime.table(self.valid_order("new"))
        self.runtime.globals["BUILD_ORDER_CATALOG"] = self.runtime.table(
            {"old": original}
        )
        return original, replacement

    def test_load_uses_the_catalog_returned_by_the_named_datastore(self) -> None:
        loaded_order = self.runtime.table(self.valid_order("english-loaded"))
        loaded = self.runtime.table(
            {
                "schema_version": 1,
                "build_orders": {"english-loaded": loaded_order},
            }
        )
        load_calls = []
        retrieve_calls = []
        added_rules = []
        completions = []
        self.runtime.globals["Game_LoadTextDataStore"] = (
            lambda datastore_id, path: load_calls.append((datastore_id, path))
        )
        self.runtime.globals["Game_RetrieveTableData"] = (
            lambda datastore_id, clear: (
                retrieve_calls.append((datastore_id, clear)),
                loaded,
            )[1]
        )
        self.runtime.globals["Rule_Remove"] = lambda _rule: None
        self.runtime.globals["Rule_Add"] = added_rules.append
        self.runtime.globals["Rule_RemoveMe"] = lambda: None
        self.runtime.globals["_G"] = self.runtime.table({})
        self.runtime.globals["print"] = lambda _message: None

        self.runtime.globals["BuildOrderDatastore_Load"](
            lambda: completions.append("complete")
        )
        self.runtime.call("BuildOrderDatastore_FinishLoad")

        self.assertEqual(load_calls, [("macroTrainerBuildOrders", "")])
        self.assertEqual(retrieve_calls, [("macroTrainerBuildOrders", False)])
        self.assertEqual(len(added_rules), 1)
        self.assertIs(
            self.runtime.globals["BUILD_ORDER_CATALOG"]["english-loaded"],
            loaded_order,
        )
        self.assertEqual(completions, ["complete"])

    def test_persistence_exceptions_restore_entry_identity_and_allow_retry(self) -> None:
        for failure in ("store", "save"):
            with self.subTest(failure=failure):
                original, replacement = self.reset_catalog()
                self.failure = failure

                result = self.runtime.call(
                    "BuildOrderDatastore_Apply", "old", "new", replacement
                )

                self.assertEqual(result, (False, "persistence_error"))
                catalog = self.runtime.globals["BUILD_ORDER_CATALOG"]
                self.assertIs(catalog["old"], original)
                self.assertIsNone(catalog["new"])

                self.failure = None
                self.assertEqual(
                    self.runtime.call(
                        "BuildOrderDatastore_Apply", "old", "new", replacement
                    ),
                    (True, ""),
                )
                self.assertIsNone(catalog["old"])
                self.assertIs(catalog["new"], replacement)


if __name__ == "__main__":
    unittest.main()
