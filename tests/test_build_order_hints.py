import tempfile
import unittest
from pathlib import Path

from tools.build_orders.compiler import compile_directory
from tools.build_orders.model import CheckDescriptor


class BuildOrderHintsTests(unittest.TestCase):
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
