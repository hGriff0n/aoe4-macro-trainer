import re
import unittest
from pathlib import Path

from test_build_order_import_graph import (
    MAIN_SCRIPT,
    packaged_scar_sources,
    walk_import_edges,
)


ROOT = Path(__file__).resolve().parents[1]
RALLYPOINT = ROOT / "assets" / "scar" / "build_orders" / "checks" / "rallypoint.scar"


def function_body(source: str, name: str) -> str:
    match = re.search(
        rf"(?:local )?function {re.escape(name)}\([^)]*\)(.*?)(?=^(?:local )?function |^BuildOrder_RegisterHandler|\Z)",
        source,
        re.MULTILINE | re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"missing function {name}")
    return match.group(1)


class RallypointBehaviorModel:
    def activate(self, check_id: str, local_player: object | None) -> list[tuple[str, bool]]:
        if local_player is None:
            return []
        return [(check_id, True)]


class BuildOrderRallypointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = RALLYPOINT.read_text(encoding="utf-8")

    def test_activation_requires_bound_player_then_auto_completes(self) -> None:
        activate = function_body(self.source, "Rallypoint_Activate")
        player_guard = "if context.localPlayer == nil then"
        completion = "BuildOrder_SetCheckComplete(check.id, true)"
        self.assertIn(player_guard, activate)
        self.assertIn(completion, activate)
        self.assertLess(activate.index(player_guard), activate.index(completion))
        model = RallypointBehaviorModel()
        self.assertEqual(model.activate("rally", None), [])
        self.assertEqual(model.activate("rally", object()), [("rally", True)])

    def test_temporary_stub_has_no_runtime_observation_state(self) -> None:
        self.assertIn('BuildOrder_RegisterHandler("rallypoint", {', self.source)
        deactivate = function_body(self.source, "Rallypoint_Deactivate")
        self.assertNotIn("BuildOrder_", deactivate)
        for forbidden in ("_STATE", "Game_GetLocalPlayer", "Player_Get", "Entity_", "Rule_", "GE_", "pairs(", "ipairs("):
            self.assertNotIn(forbidden, self.source)

    def test_packaged_root_imports_stub_exactly_once_after_engine_before_startup(self) -> None:
        edges = walk_import_edges(MAIN_SCRIPT, packaged_scar_sources())
        root_edges = [target for source, target in edges if source == MAIN_SCRIPT]
        handler = "build_orders/checks/rallypoint.scar"
        self.assertEqual(root_edges.count(handler), 1)
        self.assertLess(root_edges.index("build_orders/objective_engine.scar"), root_edges.index(handler))
        self.assertLess(root_edges.index(handler), root_edges.index("build_orders/startup.scar"))


if __name__ == "__main__":
    unittest.main()
