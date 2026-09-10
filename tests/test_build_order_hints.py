import tempfile
import unittest
from pathlib import Path

from tools.build_orders.compiler import compile_directory
from tools.build_orders.model import CheckDescriptor
from tests.scar_runtime import ScarRuntime


ROOT = Path(__file__).resolve().parents[1]
LOCALIZATION_PATH = ROOT / "assets" / "scar" / "build_orders" / "localization.scar"
ENGINE_PATH = ROOT / "assets" / "scar" / "build_orders" / "objective_engine.scar"
HINTS_PATH = ROOT / "assets" / "scar" / "build_orders" / "checks" / "hints.scar"


class BuildOrderHintsTests(unittest.TestCase):
    def test_hint_handler_is_presentation_only_and_formats_without_optional_wrapper(self) -> None:
        localization = LOCALIZATION_PATH.read_text(encoding="utf-8")
        engine = ENGINE_PATH.read_text(encoding="utf-8")
        hints = HINTS_PATH.read_text(encoding="utf-8")
        runtime = ScarRuntime(localization + "\n" + engine + "\n" + hints)
        messages = []
        runtime.globals["Loc_FormatText"] = lambda key, *values: (key, *values)
        runtime.globals["print"] = messages.append
        handler = runtime.globals["BUILD_ORDER_STATE"]["handlerMap"]["hints"]

        title = runtime.call(
            "BuildOrder_CheckTitle",
            {"id": "test:1:1", "kind": "hints", "optional": True, "payload": {"text": "Scout"}},
            handler,
        )

        self.assertEqual(title, ("$dfb5645698a84afb91cf7a2dfb0f4a4e:145", "Scout"))
        self.assertEqual(messages, [])
        self.assertIsNone(handler["activate"])
        self.assertIsNone(handler["deactivate"])
        self.assertNotIn("BUILD_ORDER_LOC_KEYS.optional", hints)

    def test_compiles_hints_as_ordered_optional_semantic_descriptors(self) -> None:
        """Fails if hint payloads, ordering, or optionality regress."""
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            (directory / "order.yaml").write_text(
                """civ: English
title: Hint order
steps:
  - hints:
      - Keep producing villagers
      - Scout the opponent
""",
                encoding="utf-8",
            )

            catalog = compile_directory(directory)

        self.assertEqual(
            catalog.build_orders[0].steps[0].checks,
            (
                CheckDescriptor(
                    "hints",
                    True,
                    {"text": "Keep producing villagers"},
                ),
                CheckDescriptor(
                    "hints",
                    True,
                    {"text": "Scout the opponent"},
                ),
            ),
        )
        self.assertFalse(hasattr(catalog.build_orders[0].steps[0].checks[0], "title"))


if __name__ == "__main__":
    unittest.main()
