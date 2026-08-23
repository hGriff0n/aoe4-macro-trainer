import tempfile
import unittest
from pathlib import Path

from tools.build_orders.compiler import BuildOrderValidationError, compile_directory
from tools.build_orders.model import BuildOrder, Catalog, CheckDescriptor, Step, normalize_id


class BuildOrderCompilerTests(unittest.TestCase):
    def write(self, directory: Path, name: str, content: str) -> None:
        (directory / name).write_text(content, encoding="utf-8")

    def compile(self, files: dict[str, str]) -> Catalog:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            for name, content in files.items():
                self.write(directory, name, content)
            return compile_directory(directory)

    def test_compiles_single_mapping_with_canonical_immutable_model(self) -> None:
        catalog = self.compile({"opening.yaml": """civ: English\ntitle: 2 TC\nsteps:\n  - title: Opening\n    vils:\n      food: 7\n"""})
        self.assertEqual(catalog, Catalog((BuildOrder("english-2-tc", "English", "2 TC", (Step("Opening", (CheckDescriptor("vils", "7 food villagers", False, {"resource": "food", "count": 7}),)),)),)))
        with self.assertRaises(Exception):
            catalog.build_orders[0].title = "changed"

    def test_compiles_list_documents_yaml_and_yml_in_sorted_file_order(self) -> None:
        catalog = self.compile({
            "zeta.yml": "- civ: French\n  title: Second\n  steps:\n    - hints: [last]\n",
            "alpha.yaml": "- civ: English\n  title: First\n  steps:\n    - hints: [first]\n- civ: Rus\n  title: Third\n  steps:\n    - hints: [third]\n",
        })
        self.assertEqual([item.id for item in catalog.build_orders], ["english-first", "rus-third", "french-second"])

    def test_preserves_step_check_and_list_order_and_expands_mapping_checks(self) -> None:
        catalog = self.compile({"order.yaml": """civ: English\ntitle: Order\nsteps:\n  - resources:\n      wood: 400\n      food: 200\n    hints: [first, second]\n"""})
        checks = catalog.build_orders[0].steps[0].checks
        self.assertEqual([(check.kind, check.payload) for check in checks], [("resources", {"resource": "wood", "count": 400}), ("resources", {"resource": "food", "count": 200}), ("hints", {"text": "first"}), ("hints", {"text": "second"})])

    def test_supports_all_documented_check_shapes(self) -> None:
        catalog = self.compile({"all.yaml": """civ: English\ntitle: All\nsteps:\n  - vils: {food: 7, no_collect: [gold]}\n    rallypoint: [food, wood]\n    built: [{id: barracks}, {oneof: [archery_range, stable]}]\n    age_up: {oneof: [age2_a, age2_b], vils: 4, location: home}\n    upgrades: [{id: wheelbarrow, optional: true}]\n    produce: [{id: villager, count: 2, constant: true, queued: true}]\n    resources: {wood: 400}\n    buildings: [{id: barracks, count: 2}]\n    units: [{id: spearman, count: 3}]\n    hints: [Keep producing]\n"""})
        checks = catalog.build_orders[0].steps[0].checks
        self.assertEqual([check.kind for check in checks], ["vils", "vils", "rallypoint", "rallypoint", "built", "built", "age_up", "upgrades", "produce", "resources", "buildings", "units", "hints"])
        self.assertEqual(checks[1].payload, {"resource": "gold", "no_collect": True})
        self.assertEqual(checks[5].payload, {"oneof": ["archery_range", "stable"]})
        self.assertEqual(checks[7].optional, True)

    def test_normalizes_unicode_ids(self) -> None:
        self.assertEqual(normalize_id("Énglish", "2 TC!"), "english-2-tc")

    def assert_invalid(self, yaml: str, fragment: str) -> None:
        with self.assertRaises(BuildOrderValidationError) as caught:
            self.compile({"file.yaml": yaml})
        self.assertIn(fragment, str(caught.exception))

    def test_rejects_invalid_schema_with_precise_paths(self) -> None:
        self.assert_invalid("civ: english\ntitle: x\nsteps:\n  - title: only\n", "file.yaml: steps[0]")
        self.assert_invalid("civ: english\ntitle: x\nsteps:\n  - resources: {iron: 2}\n", "file.yaml: steps[0].resources.iron")
        self.assert_invalid("civ: english\ntitle: x\nsteps:\n  - built: [{id: a, oneof: [b]}]\n", "file.yaml: steps[0].built[0]")
        self.assert_invalid("civ: english\ntitle: x\nsteps:\n  - built: [{id: a}, {id: 1}]\n", "file.yaml: steps[0].built[1].id")
        self.assert_invalid("civ: english\ntitle: x\nsteps:\n  - units: [{id: a, count: 0}]\n", "file.yaml: steps[0].units[0].count")
        self.assert_invalid("civ: english\ntitle: x\nunknown: true\nsteps:\n  - hints: [x]\n", "file.yaml: unknown")

    def test_rejects_duplicate_generated_slugs(self) -> None:
        self.assert_invalid("- civ: English\n  title: 2 TC\n  steps: [{hints: [a]}]\n- civ: english\n  title: 2-tc\n  steps: [{hints: [b]}]\n", "duplicate generated id 'english-2-tc'")


if __name__ == "__main__":
    unittest.main()
