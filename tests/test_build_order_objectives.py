import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENGINE_PATH = ROOT / "assets" / "scar" / "build_orders" / "objective_engine.scar"
MAIN_PATH = ROOT / "assets" / "scar" / "winconditions" / "Macro Trainer.scar"
IMPORT_PATTERN = re.compile(r'^\s*import\("([^"]+)"\)', re.MULTILINE)

FAKE_HANDLER_FIXTURE = '''local fakeHandler = {
    activate = function(check, objectiveID, context)
        BuildOrder_NotifyComplete(check.id)
    end,
    deactivate = function(check, objectiveID, context)
    end,
}
BuildOrder_RegisterHandler("fake", fakeHandler)'''


class CheckUpdateBatchModel:
    """Executable model of the engine's same-callback advancement boundary."""

    def __init__(self) -> None:
        self.depth = 0
        self.advance_pending = False
        self.advance_calls = 0
        self.active_step = 3
        self.vils_state = {"step-3-vils": True}
        self.poll_registered = True
        self.observed_during_poll: list[tuple[int, tuple[str, ...]]] = []

    def begin(self) -> None:
        self.depth += 1

    def end(self) -> None:
        if self.depth == 0:
            return
        self.depth -= 1
        if self.depth == 0 and self.advance_pending:
            self.advance_pending = False
            self.try_advance()

    def set_complete(self, completed: bool) -> None:
        if not completed:
            return
        if self.depth > 0:
            self.advance_pending = True
        else:
            self.try_advance()

    def try_advance(self) -> None:
        self.advance_calls += 1
        if self.active_step == 3:
            self.vils_state.pop("step-3-vils")
            self.poll_registered = False
            self.active_step = 4
            self.vils_state["step-4-vils"] = False
            self.poll_registered = True

    def poll_vils(self) -> None:
        self.begin()
        for check_id, completed in self.vils_state.items():
            self.set_complete(completed)
            self.observed_during_poll.append(
                (self.active_step, tuple(self.vils_state))
            )
        self.end()

    def stop(self) -> None:
        self.depth = 0
        self.advance_pending = False
        self.vils_state = {}
        self.poll_registered = False


def function_body(source: str, name: str) -> str:
    match = re.search(
        rf"function {re.escape(name)}\([^)]*\)(.*?)(?=^function |\Z)",
        source,
        re.MULTILINE | re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"missing function {name}")
    return match.group(1)


def imported_scar_edges(entry: str, sources: dict[str, str]) -> list[tuple[str, str]]:
    """Traverse available packaged SCAR sources, retaining all import edges."""
    edges: list[tuple[str, str]] = []
    visited: set[str] = set()

    def walk(path: str) -> None:
        if path in visited:
            return
        visited.add(path)
        for imported in IMPORT_PATTERN.findall(sources[path]):
            edges.append((path, imported))
            if imported in sources:
                walk(imported)

    walk(entry)
    return edges


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

    def test_packaged_import_graph_loads_units_handler_once_after_engine(self) -> None:
        root = "winconditions/Macro Trainer.scar"
        engine = "build_orders/objective_engine.scar"
        units = "build_orders/checks/units.scar"
        startup = "build_orders/startup.scar"
        sources = {
            root: self.main,
            engine: self.engine,
            units: (ROOT / "assets" / "scar" / units).read_text(encoding="utf-8"),
        }

        edges = imported_scar_edges(root, sources)

        self.assertEqual(edges.count((root, units)), 1)
        self.assertLess(edges.index((root, engine)), edges.index((root, units)))
        self.assertLess(edges.index((root, units)), edges.index((root, startup)))

    def test_import_traversal_records_duplicate_edge_from_each_parent_before_visited_guard(self) -> None:
        sources = {
            "root.scar": 'import("left.scar")\nimport("right.scar")',
            "left.scar": 'import("shared.scar")',
            "right.scar": 'import("shared.scar")',
            "shared.scar": "",
        }

        edges = imported_scar_edges("root.scar", sources)

        self.assertIn(("left.scar", "shared.scar"), edges)
        self.assertIn(("right.scar", "shared.scar"), edges)
    def test_main_imports_built_handler_once_after_engine_and_before_startup(self) -> None:
        engine = 'import("build_orders/objective_engine.scar")'
        built = 'import("build_orders/checks/built.scar")'
        startup = 'import("build_orders/startup.scar")'
        self.assertEqual(self.main.count(built), 1)
        self.assertLess(self.main.index(engine), self.main.index(built))
        self.assertLess(self.main.index(built), self.main.index(startup))

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
            "checkUpdateDepth",
            "checkAdvancePending",
        ):
            self.assertRegex(self.engine, rf"\b{field}\s*=")

        for name in (
            "BuildOrder_RegisterHandler",
            "BuildOrder_Start",
            "BuildOrder_ActivateStep",
            "BuildOrder_NotifyComplete",
            "BuildOrder_TryAdvance",
            "BuildOrder_Stop",
            "BuildOrder_BeginCheckUpdates",
            "BuildOrder_EndCheckUpdates",
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
        self.assertIn("BuildOrder_LogMissingHandler(child.check)", activate)
        self.assertIn("elseif handler.activate ~= nil then", activate)
        self.assertIn("if child == nil or child.completed == completed then", setter)
        self.assertIn("child.completed = completed", setter)
        self.assertIn("Obj_SetState(child.objectiveID, OS_Complete)", setter)
        self.assertIn("BuildOrder_TryAdvance()", setter)

    def test_missing_registered_handler_logs_check_kind_and_id_without_completing_it(self) -> None:
        logger = function_body(self.engine, "BuildOrder_LogMissingHandler")
        self.assertIn('print("BuildOrder: no registered handler for " .. tostring(check.kind) .. " (check " .. tostring(check.id) .. ")")', logger)
        self.assertNotIn("BuildOrder_SetCheckComplete", logger)

    def test_state_api_is_idempotent_reversible_and_advances_only_on_completion(self) -> None:
        body = function_body(self.engine, "BuildOrder_SetCheckComplete")
        self.assertIn("if child == nil or child.completed == completed then", body)
        self.assertIn("child.completed = completed", body)
        self.assertIn("OS_Complete", body)
        self.assertIn("OS_Incomplete", body)
        self.assertIn("if completed == true then", body)
        self.assertIn("BuildOrder_TryAdvance()", body)

    def test_state_api_coalesces_advancement_until_outermost_update_batch_ends(self) -> None:
        begin = function_body(self.engine, "BuildOrder_BeginCheckUpdates")
        end = function_body(self.engine, "BuildOrder_EndCheckUpdates")
        setter = function_body(self.engine, "BuildOrder_SetCheckComplete")
        self.assertIn("BUILD_ORDER_STATE.checkUpdateDepth + 1", begin)
        self.assertIn("BUILD_ORDER_STATE.checkUpdateDepth - 1", end)
        self.assertIn("BUILD_ORDER_STATE.checkAdvancePending = false", end)
        self.assertIn("BuildOrder_TryAdvance()", end)
        self.assertIn("BUILD_ORDER_STATE.checkUpdateDepth > 0", setter)
        self.assertIn("BUILD_ORDER_STATE.checkAdvancePending = true", setter)

    def test_consecutive_vils_steps_transition_only_after_poll_traversal(self) -> None:
        model = CheckUpdateBatchModel()

        model.poll_vils()

        self.assertEqual(
            model.observed_during_poll,
            [(3, ("step-3-vils",))],
        )
        self.assertEqual(model.active_step, 4)
        self.assertEqual(model.vils_state, {"step-4-vils": False})
        self.assertTrue(model.poll_registered)
        self.assertEqual(model.advance_calls, 1)

        model.poll_vils()

        self.assertEqual(model.active_step, 4)
        self.assertEqual(model.vils_state, {"step-4-vils": False})
        self.assertEqual(model.advance_calls, 1)

    def test_nested_batches_coalesce_multiple_completions_into_one_advance(self) -> None:
        model = CheckUpdateBatchModel()
        model.begin()
        model.begin()
        model.set_complete(True)
        model.set_complete(True)

        model.end()
        self.assertEqual(model.advance_calls, 0)
        model.end()

        self.assertEqual(model.advance_calls, 1)
        self.assertEqual(model.depth, 0)
        self.assertFalse(model.advance_pending)

    def test_stop_resets_unfinished_update_batch_defensively(self) -> None:
        model = CheckUpdateBatchModel()
        model.begin()
        model.set_complete(True)

        model.stop()
        model.end()

        self.assertEqual(model.depth, 0)
        self.assertFalse(model.advance_pending)
        self.assertEqual(model.advance_calls, 0)

        stop = function_body(self.engine, "BuildOrder_Stop")
        self.assertIn("BUILD_ORDER_STATE.checkUpdateDepth = 0", stop)
        self.assertIn("BUILD_ORDER_STATE.checkAdvancePending = false", stop)

    def test_notify_complete_wraps_explicit_state_api(self) -> None:
        body = function_body(self.engine, "BuildOrder_NotifyComplete")
        self.assertIn("BuildOrder_SetCheckComplete(checkID, true)", body)

    def test_required_children_block_but_optional_children_do_not(self) -> None:
        advance = function_body(self.engine, "BuildOrder_TryAdvance")
        self.assertIn("child.check.optional == false and child.completed == false", advance)
        self.assertIn("if BUILD_ORDER_STATE.advancing == true then", advance)

    def test_optional_missing_handler_descriptors_do_not_wait_for_completion_callbacks(self) -> None:
        """Fails if TryAdvance begins treating an incomplete optional child as blocking."""
        step = {
            "checks": [
                {"kind": "hints", "optional": True, "completed": False, "handler": None},
                {"kind": "hints", "optional": True, "completed": False, "handler": None},
            ]
        }
        blocking_children = [
            check
            for check in step["checks"]
            if check["optional"] is False and check["completed"] is False
        ]

        advance = function_body(self.engine, "BuildOrder_TryAdvance")

        self.assertEqual(blocking_children, [])
        self.assertIn("if child.check.optional == false and child.completed == false", advance)
        self.assertNotIn("child.handler", advance)

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

    def test_engine_exposes_selected_build_civilization_to_handlers(self) -> None:
        self.assertIn("civ = nil", self.engine)
        self.assertIn("BUILD_ORDER_STATE.civ = string.lower(buildOrder.civ)", self.engine)
        activation = self.engine[self.engine.index("function BuildOrder_Start"):]
        self.assertLess(
            activation.index("BUILD_ORDER_STATE.civ = string.lower(buildOrder.civ)"),
            activation.index("BuildOrder_ActivateStep(1)"),
        )

    def test_stop_clears_civilization_context(self) -> None:
        stop = function_body(self.engine, "BuildOrder_Stop")
        self.assertIn("BUILD_ORDER_STATE.civ = nil", stop)

    def test_fake_handler_fixture_exercises_public_lifecycle_without_shipping_one(self) -> None:
        self.assertIn("BuildOrder_RegisterHandler(\"fake\", fakeHandler)", FAKE_HANDLER_FIXTURE)
        self.assertIn("BuildOrder_NotifyComplete(check.id)", FAKE_HANDLER_FIXTURE)
        self.assertNotIn('BuildOrder_RegisterHandler("fake"', self.engine)
        self.assertIn("BuildOrder_RegisterHandler", self.engine)
        self.assertIn("BuildOrder_NotifyComplete", self.engine)


if __name__ == "__main__":
    unittest.main()
