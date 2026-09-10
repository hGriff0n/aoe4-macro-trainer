import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from tools.build_orders.compiler import (
    BuildOrderValidationError,
    compile_inputs,
    main,
    merge_catalog,
)
from tools.build_orders.datastore import load_datastore, write_datastore
from tools.build_orders.model import BuildOrder, Catalog, CheckDescriptor, Step


def yaml_order(civ: str, title: str, hint: str = "Scout") -> str:
    return (
        f"civ: {civ}\n"
        f"title: {title}\n"
        "steps:\n"
        "  - hints:\n"
        f"      - {hint}\n"
    )


def compiled_order(identifier: str, civ: str, title: str, hint: str) -> BuildOrder:
    return BuildOrder(
        identifier,
        civ,
        title,
        (Step("Step 1", (CheckDescriptor("hints", f"[HINT] {hint}", True, {"text": hint}),)),),
    )


class CompileInputTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_single_yaml_file_compiles(self) -> None:
        source = self.root / "single.yaml"
        source.write_text(yaml_order("english", "Single"), encoding="utf-8")

        catalog = compile_inputs([source])

        self.assertEqual([order.id for order in catalog.build_orders], ["english-single"])

    def test_mixed_files_and_directories_preserve_input_and_relative_order(self) -> None:
        first = self.root / "first.yaml"
        first.write_text(yaml_order("english", "First"), encoding="utf-8")
        directory = self.root / "orders"
        (directory / "nested").mkdir(parents=True)
        (directory / "z.yaml").write_text(yaml_order("english", "Zulu"), encoding="utf-8")
        (directory / "nested" / "a.yml").write_text(yaml_order("english", "Alpha"), encoding="utf-8")

        catalog = compile_inputs([first, directory])

        self.assertEqual(
            [order.id for order in catalog.build_orders],
            ["english-first", "english-alpha", "english-zulu"],
        )

    def test_duplicate_ids_across_input_batch_are_rejected(self) -> None:
        first = self.root / "first.yaml"
        second = self.root / "second.yaml"
        first.write_text(yaml_order("english", "Same"), encoding="utf-8")
        second.write_text(yaml_order("english", "Same"), encoding="utf-8")

        with self.assertRaisesRegex(
            BuildOrderValidationError, "duplicate generated id 'english-same'"
        ):
            compile_inputs([first, second])

    def test_missing_and_non_yaml_inputs_are_rejected(self) -> None:
        text = self.root / "order.txt"
        text.write_text("not yaml", encoding="utf-8")
        for path in (self.root / "missing.yaml", text):
            with self.subTest(path=path.name):
                with self.assertRaises(BuildOrderValidationError):
                    compile_inputs([path])

    def test_merge_replaces_matches_appends_new_and_sorts_by_id(self) -> None:
        old = compiled_order("english-old", "english", "Old", "old")
        stale = compiled_order("english-same", "english", "Stale", "stale")
        replacement = compiled_order("english-same", "english", "Fresh", "fresh")
        added = compiled_order("abbasid-added", "abbasid", "Added", "added")

        merged = merge_catalog(Catalog((old, stale)), Catalog((replacement, added)))

        self.assertEqual(
            [order.id for order in merged.build_orders],
            ["abbasid-added", "english-old", "english-same"],
        )
        self.assertEqual(merged.build_orders[-1].title, "Fresh")


class CompilerCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.datastore = self.root / "profile" / "datastore" / "macroTrainerBuildOrders.rlt"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_command(self, arguments: list[str]) -> tuple[int, str, str]:
        stdout = StringIO()
        stderr = StringIO()
        with patch(
            "tools.build_orders.compiler.resolve_datastore_path",
            return_value=self.datastore,
        ), redirect_stdout(stdout), redirect_stderr(stderr):
            result = main(arguments)
        return result, stdout.getvalue(), stderr.getvalue()

    def test_build_and_default_forwarding_create_same_datastore(self) -> None:
        source = self.root / "order.yaml"
        source.write_text(yaml_order("english", "Opening"), encoding="utf-8")

        result, _, error = self.run_command(["build", str(source), "--profile", "123"])
        explicit = self.datastore.read_bytes()
        self.datastore.unlink()
        forwarded_result, _, forwarded_error = self.run_command(
            [str(source), "--profile", "123"]
        )

        self.assertEqual((result, error), (0, ""))
        self.assertEqual((forwarded_result, forwarded_error), (0, ""))
        self.assertEqual(self.datastore.read_bytes(), explicit)

    def test_list_has_stable_columns_and_id_sorted_rows(self) -> None:
        write_datastore(
            self.datastore,
            Catalog(
                (
                    compiled_order("zulu-last", "zulu", "Last", "z"),
                    BuildOrder(
                        "english-first",
                        "english",
                        "First",
                        compiled_order("unused", "english", "Unused", "e").steps,
                        "https://example.com/first",
                    ),
                )
            ),
        )

        result, output, error = self.run_command(["list", "--profile", "123"])

        self.assertEqual((result, error), (0, ""))
        lines = output.splitlines()
        self.assertEqual(lines[0].split(), ["ID", "CIV", "TITLE", "SOURCE"])
        self.assertIn("english-first", lines[2])
        self.assertIn("zulu-last", lines[3])

    def test_list_absent_datastore_prints_header_only(self) -> None:
        result, output, error = self.run_command(["list", "--profile", "123"])

        self.assertEqual((result, error), (0, ""))
        self.assertEqual(len(output.splitlines()), 2)
        self.assertEqual(output.splitlines()[0].split(), ["ID", "CIV", "TITLE", "SOURCE"])

    def test_delete_is_all_or_nothing(self) -> None:
        catalog = Catalog(
            (
                compiled_order("english-one", "english", "One", "one"),
                compiled_order("english-two", "english", "Two", "two"),
            )
        )
        write_datastore(self.datastore, catalog)
        before = self.datastore.read_bytes()

        failed, _, error = self.run_command(
            ["delete", "english-one", "missing", "--profile", "123"]
        )
        self.assertEqual(failed, 2)
        self.assertIn("unknown build order ID", error)
        self.assertEqual(self.datastore.read_bytes(), before)

        result, _, error = self.run_command(
            ["delete", "english-one", "english-two", "--profile", "123"]
        )
        self.assertEqual((result, error), (0, ""))
        self.assertEqual(load_datastore(self.datastore), Catalog(()))

    def test_extract_writes_recompilable_normalized_yaml(self) -> None:
        source = self.root / "order.yaml"
        source.write_text(
            "civ: english\n"
            "title: Complete\n"
            "link: https://example.com/order\n"
            "steps:\n"
            "  - title: Opening\n"
            "    vils: {food: 7, no_collect: [stone]}\n"
            "    rallypoint: [wood]\n"
            "    built: [{id: house, count: 2, vils: 3, location: home}]\n"
            "    age_up: {id: council_hall, vils: 4}\n"
            "    upgrades: [{id: wheelbarrow, queued: true, optional: true}]\n"
            "    produce: [{id: villager, count: 2, queued: true}]\n"
            "    resources: {gold: 200}\n"
            "    buildings: [{id: barracks, count: 1}]\n"
            "    units: [{id: spearman, count: 3}]\n"
            "    hints: [Scout early]\n",
            encoding="utf-8",
        )
        expected = compile_inputs([source])
        write_datastore(self.datastore, expected)
        output = self.root / "out"

        result, _, error = self.run_command(
            ["extract", "english-complete", "--output-dir", str(output), "--profile", "123"]
        )

        self.assertEqual((result, error), (0, ""))
        extracted = output / "english-complete.yaml"
        self.assertTrue(extracted.is_file())
        self.assertEqual(compile_inputs([extracted]), expected)

    def test_extract_unknown_id_writes_nothing(self) -> None:
        write_datastore(
            self.datastore,
            Catalog((compiled_order("english-one", "english", "One", "one"),)),
        )
        output = self.root / "out"

        result, _, error = self.run_command(
            ["extract", "missing", "--output-dir", str(output), "--profile", "123"]
        )

        self.assertEqual(result, 2)
        self.assertIn("unknown build order ID", error)
        self.assertFalse(output.exists())

    def test_extract_refuses_existing_output_before_writing_any_file(self) -> None:
        write_datastore(
            self.datastore,
            Catalog(
                (
                    compiled_order("english-one", "english", "One", "one"),
                    compiled_order("english-two", "english", "Two", "two"),
                )
            ),
        )
        output = self.root / "out"
        output.mkdir()
        existing = output / "english-two.yaml"
        existing.write_text("keep me", encoding="utf-8")

        result, _, error = self.run_command(
            [
                "extract",
                "english-one",
                "english-two",
                "--output-dir",
                str(output),
                "--profile",
                "123",
            ]
        )

        self.assertEqual(result, 2)
        self.assertIn("already exists", error)
        self.assertFalse((output / "english-one.yaml").exists())
        self.assertEqual(existing.read_text(encoding="utf-8"), "keep me")

    def test_validation_error_has_no_traceback(self) -> None:
        source = self.root / "bad.yaml"
        source.write_text("not: an order\n", encoding="utf-8")

        result, _, error = self.run_command(["build", str(source), "--profile", "123"])

        self.assertEqual(result, 2)
        self.assertNotIn("Traceback", error)


if __name__ == "__main__":
    unittest.main()
