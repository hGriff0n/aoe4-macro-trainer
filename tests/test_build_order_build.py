import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.build_mod import BuildConfig, BuildPaths, build_mod
from tools.build_orders.compiler import compile_directory
from tools.build_orders.emitters import emit_outputs, reset_outputs


VALID = "civ: english\ntitle: Framework Test\nsteps:\n  - title: Opening Economy\n    vils:\n      food: 7\n    hints:\n      - Keep producing villagers\n  - resources:\n      wood: 400\n"


class BuildOrderBuildTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.rdo_template = self.root / "templates" / "Macro Trainer.rdo"
        self.locdb_template = self.root / "templates" / "Macro Trainer_en.csv"
        self.rdo_template.parent.mkdir(parents=True)
        self.rdo_template.write_text("<!-- GENERATED_BUILD_ORDER_ENUM_ITEMS -->\n", encoding="utf-8")
        self.locdb_template.write_text("ID,Text\n1,BASELINE\n", encoding="utf-8")
        self.paths = BuildPaths(self.root, self.rdo_template, self.locdb_template, self.root / "assets" / "Macro Trainer.rdo", self.root / "assets" / "Macro Trainer_en.csv", self.root / "assets" / "generated" / "build_orders.scar")
        self.orders = self.root / "orders"
        self.orders.mkdir()
        self.mod = self.root / "Macro Trainer.aoe4mod"
        self.mod.write_text("mod", encoding="utf-8")
        self.config = BuildConfig(self.paths, self.orders, self.mod, Path(r"F:\Program Files (x86)\Steam\steamapps\common\Age of Empires IV Content Editor\EssenceLauncher.exe"))

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_reset_replaces_all_stale_generated_outputs_with_baseline(self) -> None:
        for output in (self.paths.rdo_output, self.paths.locdb_output, self.paths.scar_output):
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text("STALE", encoding="utf-8")
        reset_outputs(self.paths)
        self.assertEqual(self.paths.rdo_output.read_text(encoding="utf-8"), "<!-- GENERATED_BUILD_ORDER_ENUM_ITEMS -->\n")
        self.assertEqual(self.paths.locdb_output.read_text(encoding="utf-8"), "ID,Text\n1,BASELINE\n")
        self.assertEqual(self.paths.scar_output.read_text(encoding="utf-8"), "BUILD_ORDER_CATALOG = {}\n")

    def test_emits_ordered_catalog_and_localized_titles_without_tmp_files(self) -> None:
        (self.orders / "framework.yaml").write_text(VALID, encoding="utf-8")
        reset_outputs(self.paths)
        emit_outputs(compile_directory(self.orders), self.paths)
        scar = self.paths.scar_output.read_text(encoding="utf-8")
        locdb = self.paths.locdb_output.read_text(encoding="utf-8")
        self.assertIn('BUILD_ORDER_CATALOG["english-framework-test"]', scar)
        self.assertIn('$dfb5645698a84afb91cf7a2dfb0f4a4e:1001', scar)
        self.assertLess(scar.index('kind = "vils"'), scar.index('kind = "hints"'))
        self.assertIn("1000,,,Generated build-order option.,,,[English] Framework Test", locdb)
        self.assertIn("1001,,,Generated build-order title.,,,Framework Test", locdb)
        self.assertIn("1002,,,Generated step title.,,,Opening Economy", locdb)
        self.assertFalse(list(self.root.rglob("*.tmp")))

    def test_malformed_yaml_leaves_baseline_and_never_calls_essence(self) -> None:
        (self.orders / "bad.yaml").write_text("civ: english\ntitle: Bad\nsteps: [not-a-mapping]\n", encoding="utf-8")
        calls = []
        result = build_mod(self.config, lambda *args, **kwargs: calls.append((args, kwargs)))
        self.assertEqual(result, 2)
        self.assertEqual(calls, [])
        self.assertEqual(self.paths.scar_output.read_text(encoding="utf-8"), "BUILD_ORDER_CATALOG = {}\n")
        self.assertEqual(self.paths.rdo_output.read_text(encoding="utf-8"), "<!-- GENERATED_BUILD_ORDER_ENUM_ITEMS -->\n")

    def test_successful_build_calls_exact_essence_command(self) -> None:
        (self.orders / "valid.yaml").write_text(VALID, encoding="utf-8")
        calls = []
        def runner(command, **kwargs):
            calls.append((command, kwargs))
            return subprocess.CompletedProcess(command, 0)
        self.assertEqual(build_mod(self.config, runner), 0)
        self.assertEqual(calls[0][0], [self.config.essence_launcher, "--build_mod", str(self.mod.resolve()), "--auto_close_burn_window"])

    def test_nonzero_essence_result_is_returned(self) -> None:
        (self.orders / "valid.yaml").write_text(VALID, encoding="utf-8")
        result = build_mod(self.config, lambda command, **kwargs: subprocess.CompletedProcess(command, 23))
        self.assertEqual(result, 23)

    def test_generate_only_cli_runs_directly_from_repository_root(self) -> None:
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, "tools/build_mod.py", "--build-orders", "tests/fixtures/build_orders/valid", "--generate-only"],
            cwd=root,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
