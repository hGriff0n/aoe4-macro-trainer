import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCAR_ROOT = ROOT / "assets" / "scar"
SUPPORT = SCAR_ROOT / "build_orders" / "check_support.scar"
MAIN_WINCONDITION = SCAR_ROOT / "winconditions" / "Macro Trainer.scar"
HANDLERS = {
    "age_up": SCAR_ROOT / "build_orders" / "checks" / "age_up.scar",
    "built": SCAR_ROOT / "build_orders" / "checks" / "built.scar",
    "produce": SCAR_ROOT / "build_orders" / "checks" / "produce.scar",
    "units": SCAR_ROOT / "build_orders" / "checks" / "units.scar",
    "upgrades": SCAR_ROOT / "build_orders" / "checks" / "upgrades.scar",
}


def function_body(source: str, name: str) -> str:
    match = re.search(
        rf"function {re.escape(name)}\([^)]*\)(.*?)(?=^function |\Z)",
        source,
        re.MULTILINE | re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"missing function {name}")
    return match.group(1)


class BuildOrderCheckSupportTests(unittest.TestCase):
    def test_packaged_root_imports_support_once_after_engine_before_handlers(self) -> None:
        source = MAIN_WINCONDITION.read_text(encoding="utf-8")
        support_import = 'import("build_orders/check_support.scar")'
        engine_import = 'import("build_orders/objective_engine.scar")'

        self.assertEqual(source.count(support_import), 1)
        self.assertLess(source.index(engine_import), source.index(support_import))
        for handler in HANDLERS:
            handler_import = f'import("build_orders/checks/{handler}.scar")'
            self.assertLess(source.index(support_import), source.index(handler_import))

    def test_support_module_exposes_nil_safe_blueprint_contracts(self) -> None:
        self.assertTrue(SUPPORT.exists())
        source = SUPPORT.read_text(encoding="utf-8")

        equal = function_body(source, "BuildOrder_BlueprintsEqual")
        self.assertIn("left ~= nil and right ~= nil", equal)
        for field in (
            "PropertyBagGroupID",
            "PropertyBagGroupModPackID",
            "PropertyBagGroupType",
        ):
            self.assertIn(f"left.{field} == right.{field}", equal)

        matcher = function_body(source, "BuildOrder_MatchesAnyBlueprint")
        self.assertIn("ipairs(pbgs)", matcher)
        self.assertIn("BuildOrder_BlueprintsEqual(candidate, pbg)", matcher)

    def test_support_module_resolves_lists_and_payload_shapes(self) -> None:
        self.assertTrue(SUPPORT.exists())
        source = SUPPORT.read_text(encoding="utf-8")

        resolve = function_body(source, "BuildOrder_ResolveBlueprints")
        self.assertIn("ipairs(ids)", resolve)
        self.assertIn("resolver(id)", resolve)

        payload = function_body(source, "BuildOrder_ResolvePayloadBlueprints")
        self.assertIn("payload.id ~= nil", payload)
        self.assertIn("BuildOrder_ResolveBlueprints({payload.id}, resolver)", payload)
        self.assertIn("BuildOrder_ResolveBlueprints(payload.oneof, resolver)", payload)

    def test_support_module_resolves_direct_player_and_entity_executers(self) -> None:
        self.assertTrue(SUPPORT.exists())
        source = SUPPORT.read_text(encoding="utf-8")
        resolver = function_body(source, "BuildOrder_GetExecuterOwner")

        self.assertIn("context.executer.PlayerID ~= nil", resolver)
        self.assertIn("return context.executer", resolver)
        self.assertIn("context.executer.EntityID ~= nil", resolver)
        self.assertIn("return Entity_GetPlayerOwner(context.executer)", resolver)

    def test_handlers_use_shared_interfaces_without_private_blueprint_helpers(self) -> None:
        old_helpers = re.compile(
            r"(?:local )?function (?:AgeUp|Built|Produce|Units|Upgrades)_(?:PBGsEqual|BlueprintsEqual|MatchesPBG|ResolvePBGs|GetExecuterOwner)"
        )
        required_calls = {
            "age_up": (
                "BuildOrder_MatchesAnyBlueprint",
                "BuildOrder_ResolvePayloadBlueprints",
                "BuildOrder_GetExecuterOwner",
            ),
            "built": (
                "BuildOrder_MatchesAnyBlueprint",
                "BuildOrder_ResolvePayloadBlueprints",
            ),
            "produce": (
                "BuildOrder_MatchesAnyBlueprint",
                "BuildOrder_ResolveBlueprints",
            ),
            "units": (
                "BuildOrder_MatchesAnyBlueprint",
                "BuildOrder_ResolveBlueprints",
            ),
            "upgrades": (
                "BuildOrder_BlueprintsEqual",
                "BuildOrder_GetExecuterOwner",
            ),
        }

        for handler, path in HANDLERS.items():
            with self.subTest(handler=handler):
                source = path.read_text(encoding="utf-8")
                self.assertIsNone(old_helpers.search(source))
                for call in required_calls[handler]:
                    self.assertIn(call, source)


if __name__ == "__main__":
    unittest.main()
