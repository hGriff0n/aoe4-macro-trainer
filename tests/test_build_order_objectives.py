import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENGINE_PATH = ROOT / "assets" / "scar" / "build_orders" / "objective_engine.scar"
MAIN_PATH = ROOT / "assets" / "scar" / "winconditions" / "Macro Trainer.scar"

FAKE_HANDLER_FIXTURE = '''local fakeHandler = {
    activate = function(check, objectiveID, context)
        BuildOrder_NotifyComplete(check.id)
    end,
    deactivate = function(check, objectiveID, context)
    end,
}
BuildOrder_RegisterHandler("fake", fakeHandler)'''


def function_body(source: str, name: str) -> str:
    match = re.search(
        rf"function {re.escape(name)}\([^)]*\)(.*?)(?=^function |\Z)",
        source,
        re.MULTILINE | re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"missing function {name}")
    return match.group(1)


class BuildOrderObjectiveContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = ENGINE_PATH.read_text(encoding="utf-8")
        cls.main = MAIN_PATH.read_text(encoding="utf-8")

    def assert_order(self, body: str, first: str, second: str) -> None:
        self.assertLess(body.index(first), body.index(second))

    def test_main_loads_generated_catalog_before_objective_engine(self) -> None:
        generated = 'import("generated/build_orders.scar")'
        engine = 'import("build_orders/objective_engine.scar")'
        self.assertIn(generated, self.main)
        self.assertIn(engine, self.main)
        self.assertLess(self.main.index(generated), self.main.index(engine))

    def test_engine_tracks_active_hierarchy_handlers_and_advancement(self) -> None:
        for field in (
            "localPlayer",
            "selectedBuild",
            "activeStepIndex",
            "primaryObjectiveID",
            "childByCheckID",
            "childRecords",
            "handlerMap",
            "advancing",
        ):
            self.assertRegex(self.engine, rf"\b{field}\s*=")

        for name in (
            "BuildOrder_RegisterHandler",
            "BuildOrder_Start",
            "BuildOrder_ActivateStep",
            "BuildOrder_NotifyComplete",
            "BuildOrder_TryAdvance",
            "BuildOrder_Stop",
        ):
            function_body(self.engine, name)

    def test_activation_creates_normal_primary_and_secondary_objectives(self) -> None:
        activate = function_body(self.engine, "BuildOrder_ActivateStep")
        self.assertIn("local faction = Player_GetRaceName(player)", activate)
        self.assertRegex(
            activate,
            r"Obj_Create\(\s*player,\s*step\.title,\s*Loc_Empty\(\),\s*\"\",\s*DT_PRIMARY_DEFAULT,\s*faction,\s*OT_Primary,\s*0,\s*\"buildOrderStep\"\s*\)",
        )
        self.assertRegex(
            activate,
            r"Obj_Create\(\s*player,\s*check\.title,\s*Loc_Empty\(\),\s*\"\",\s*DT_SECONDARY_DEFAULT,\s*faction,\s*OT_Secondary,\s*primaryID,\s*\"buildOrderCheck\"\s*\)",
        )
        self.assertNotIn("Player_GetID", activate)
        self.assertNotIn("player.id", activate)
        self.assertNotIn("player.raceName", activate)
        self.assertIn("Obj_SetState(primaryID, OS_Incomplete)", activate)
        self.assertIn("Obj_SetState(childID, OS_Incomplete)", activate)
        self.assertIn("Obj_SetVisible(primaryID, true)", activate)
        self.assertIn("Obj_SetVisible(childID, true)", activate)
        self.assert_order(
            activate,
            "Obj_SetState(primaryID, OS_Incomplete)",
            "Obj_SetVisible(primaryID, true)",
        )
        self.assert_order(
            activate,
            "Obj_SetState(childID, OS_Incomplete)",
            "Obj_SetVisible(childID, true)",
        )
        self.assertNotIn("DT_PRIMARY_WARNING", self.engine)
        self.assertNotIn("DT_SECONDARY_WARNING", self.engine)
        self.assertNotIn("OT_Warning", self.engine)

    def test_handlers_receive_stable_ids_after_all_child_objectives_exist(self) -> None:
        activate = function_body(self.engine, "BuildOrder_ActivateStep")
        self.assertIn("childByCheckID[checkID] = child", activate)
        self.assertIn("handler.activate(child.check, child.objectiveID, BUILD_ORDER_STATE)", activate)
        self.assertLess(
            activate.index("childByCheckID[checkID] = child"),
            activate.index("handler.activate(child.check, child.objectiveID, BUILD_ORDER_STATE)"),
        )
        self.assertIn('tostring(stepIndex) .. ":" .. tostring(checkIndex)', activate)
        self.assertRegex(
            activate,
            r"check\s*=\s*\{\s*id\s*=\s*checkID,\s*kind\s*=\s*check\.kind,\s*title\s*=\s*check\.title,\s*optional\s*=\s*check\.optional,\s*payload\s*=\s*check\.payload,\s*\}",
        )
        self.assertNotIn("check.id = checkID", activate)

    def test_missing_handler_leaves_child_pending_and_completion_latches(self) -> None:
        activate = function_body(self.engine, "BuildOrder_ActivateStep")
        setter = function_body(self.engine, "BuildOrder_SetCheckComplete")
        self.assertIn("Obj_SetState(childID, OS_Incomplete)", activate)
        self.assertIn("if handler ~= nil and handler.activate ~= nil then", activate)
        self.assertIn("if child == nil or child.completed == completed then", setter)
        self.assertIn("child.completed = completed", setter)
        self.assertIn("Obj_SetState(child.objectiveID, OS_Complete)", setter)
        self.assertIn("BuildOrder_TryAdvance()", setter)

    def test_state_api_is_idempotent_reversible_and_advances_only_on_completion(self) -> None:
        body = function_body(self.engine, "BuildOrder_SetCheckComplete")
        self.assertIn("if child == nil or child.completed == completed then", body)
        self.assertIn("child.completed = completed", body)
        self.assertIn("OS_Complete", body)
        self.assertIn("OS_Incomplete", body)
        self.assertIn("if completed == true then", body)
        self.assertIn("BuildOrder_TryAdvance()", body)

    def test_notify_complete_wraps_explicit_state_api(self) -> None:
        body = function_body(self.engine, "BuildOrder_NotifyComplete")
        self.assertIn("BuildOrder_SetCheckComplete(checkID, true)", body)

    def test_required_children_block_but_optional_children_do_not(self) -> None:
        advance = function_body(self.engine, "BuildOrder_TryAdvance")
        self.assertIn("child.check.optional == false and child.completed == false", advance)
        self.assertIn("if BUILD_ORDER_STATE.advancing == true then", advance)

    def test_cleanup_deactivates_then_deletes_children_before_primary(self) -> None:
        cleanup = function_body(self.engine, "BuildOrder_ClearActiveHierarchy")
        self.assertIn("handler.deactivate(child.check, child.objectiveID, BUILD_ORDER_STATE)", cleanup)
        self.assertIn("Obj_Delete(child.objectiveID)", cleanup)
        self.assertIn("Obj_Delete(BUILD_ORDER_STATE.primaryObjectiveID)", cleanup)
        self.assert_order(cleanup, "handler.deactivate", "Obj_Delete(child.objectiveID)")
        self.assert_order(cleanup, "Obj_Delete(child.objectiveID)", "Obj_Delete(BUILD_ORDER_STATE.primaryObjectiveID)")

    def test_last_step_stops_without_indexing_beyond_catalog(self) -> None:
        advance = function_body(self.engine, "BuildOrder_TryAdvance")
        self.assertIn("if nextStepIndex > #BUILD_ORDER_STATE.selectedBuild.steps then", advance)
        self.assertIn("BuildOrder_Stop()", advance)
        self.assert_order(advance, "Obj_SetState(BUILD_ORDER_STATE.primaryObjectiveID, OS_Complete)", "BuildOrder_ClearActiveHierarchy()")

    def test_public_lifecycle_starts_after_cleanup_and_advances_after_completion(self) -> None:
        start = function_body(self.engine, "BuildOrder_Start")
        advance = function_body(self.engine, "BuildOrder_TryAdvance")
        self.assert_order(start, "BuildOrder_Stop()", "BuildOrder_ActivateStep(1)")
        self.assert_order(advance, "BuildOrder_ClearActiveHierarchy()", "BuildOrder_ActivateStep(nextStepIndex)")

    def test_fake_handler_fixture_exercises_public_lifecycle_without_shipping_one(self) -> None:
        self.assertIn("BuildOrder_RegisterHandler(\"fake\", fakeHandler)", FAKE_HANDLER_FIXTURE)
        self.assertIn("BuildOrder_NotifyComplete(check.id)", FAKE_HANDLER_FIXTURE)
        self.assertNotIn('BuildOrder_RegisterHandler("fake"', self.engine)
        self.assertIn("BuildOrder_RegisterHandler", self.engine)
        self.assertIn("BuildOrder_NotifyComplete", self.engine)


if __name__ == "__main__":
    unittest.main()
