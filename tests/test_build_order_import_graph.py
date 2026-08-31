import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCAR_ROOT = ROOT / "assets" / "scar"
MAIN_SCRIPT = "winconditions/Macro Trainer.scar"
IMPORT_PATTERN = re.compile(r'^\s*import\("([^"]+)"\)', re.MULTILINE)


def packaged_scar_sources() -> dict[str, str]:
    return {
        path.relative_to(SCAR_ROOT).as_posix(): path.read_text(encoding="utf-8")
        for path in SCAR_ROOT.rglob("*.scar")
    }


def walk_import_edges(root: str, sources: dict[str, str]) -> list[tuple[str, str]]:
    """Return every packaged import edge, including shared children."""
    edges: list[tuple[str, str]] = []
    visited: set[str] = set()

    def visit(source: str) -> None:
        if source in visited:
            return
        visited.add(source)
        for target in IMPORT_PATTERN.findall(sources[source]):
            edges.append((source, target))
            if target in sources:
                visit(target)

    visit(root)
    return edges


class BuildOrderImportGraphTests(unittest.TestCase):
    def test_packaged_root_imports_resources_handler_after_engine_before_startup(self) -> None:
        edges = walk_import_edges(MAIN_SCRIPT, packaged_scar_sources())
        root_edges = [target for source, target in edges if source == MAIN_SCRIPT]

        self.assertEqual(root_edges.count("build_orders/checks/resources.scar"), 1)
        self.assertLess(
            root_edges.index("build_orders/objective_engine.scar"),
            root_edges.index("build_orders/checks/resources.scar"),
        )
        self.assertLess(
            root_edges.index("build_orders/checks/resources.scar"),
            root_edges.index("build_orders/startup.scar"),
        )

    def test_packaged_root_imports_upgrades_handler_after_engine_before_startup(self) -> None:
        edges = walk_import_edges(MAIN_SCRIPT, packaged_scar_sources())
        root_edges = [target for source, target in edges if source == MAIN_SCRIPT]

        self.assertEqual(root_edges.count("build_orders/checks/upgrades.scar"), 1)
        self.assertLess(
            root_edges.index("build_orders/objective_engine.scar"),
            root_edges.index("build_orders/checks/upgrades.scar"),
        )
        self.assertLess(
            root_edges.index("build_orders/checks/upgrades.scar"),
            root_edges.index("build_orders/startup.scar"),
        )

    def test_packaged_root_imports_produce_handler_after_engine_before_startup(self) -> None:
        edges = walk_import_edges(MAIN_SCRIPT, packaged_scar_sources())
        root_edges = [target for source, target in edges if source == MAIN_SCRIPT]

        self.assertEqual(root_edges.count("build_orders/checks/produce.scar"), 1)
        self.assertLess(
            root_edges.index("build_orders/objective_engine.scar"),
            root_edges.index("build_orders/checks/produce.scar"),
        )
        self.assertLess(
            root_edges.index("build_orders/checks/produce.scar"),
            root_edges.index("build_orders/startup.scar"),
        )

    def test_walk_records_shared_import_from_each_parent_before_visited_guard(self) -> None:
        sources = {
            "root.scar": 'import("left.scar")\nimport("right.scar")\n',
            "left.scar": 'import("shared.scar")\n',
            "right.scar": 'import("shared.scar")\n',
            "shared.scar": "",
        }

        self.assertEqual(
            walk_import_edges("root.scar", sources),
            [
                ("root.scar", "left.scar"),
                ("left.scar", "shared.scar"),
                ("root.scar", "right.scar"),
                ("right.scar", "shared.scar"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
