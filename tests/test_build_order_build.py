import io
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from tools.build_mod import BuildConfig, BuildPaths, _wait_for_fresh_archive, build_mod
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
        self.mod.write_text(
            "<?xml version='1.0' encoding='utf-8'?>\n"
            "<Mod xmlns='http://schemas.datacontract.org/2004/07/Essence.Editor.Modding'>"
            "<DataIntermediatePath>cache</DataIntermediatePath></Mod>\n",
            encoding="utf-8",
        )
        self.archive = self.root / "archives" / "Macro_Trainer.sga"
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
        self.assertIn("1003,,,Generated check title.,,,7 food villagers", locdb)
        self.assertIn("1004,,,Generated check title.,,,[HINT] Keep producing villagers", locdb)
        self.assertIn("1005,,,Generated step title.,,,Step 2", locdb)
        self.assertIn("1006,,,Generated check title.,,,Collect at least 400 wood", locdb)
        self.assertIn(
            'id = "english-framework-test:1:1", kind = "vils", '
            'title = "$dfb5645698a84afb91cf7a2dfb0f4a4e:1003"',
            scar,
        )
        self.assertIn('id = "english-framework-test:2:1"', scar)
        self.assertNotIn('title = "7 food villagers"', scar)
        self.assertFalse(list(self.root.rglob("*.tmp")))

    def test_emits_extended_built_and_upgrade_payload_fields(self) -> None:
        (self.orders / "extended.yaml").write_text(
            """civ: english
title: Extended
steps:
  - built:
      - id: barracks
        count: 2
        vils: 3
        location: forward
      - oneof: [stable, archery_range]
    upgrades:
      - id: wheelbarrow
        queued: true
      - id: horticulture
""",
            encoding="utf-8",
        )
        reset_outputs(self.paths)
        emit_outputs(compile_directory(self.orders), self.paths)

        scar = self.paths.scar_output.read_text(encoding="utf-8")
        self.assertIn(
            'payload = {id = "building_unit_infantry_control_eng", count = 2, vils = 3, location = "forward"}',
            scar,
        )
        self.assertIn(
            'payload = {oneof = {"building_unit_cavalry_control_eng", "building_unit_ranged_control_eng"}, count = 1}',
            scar,
        )
        self.assertIn(
            'payload = {id = "upgrade_unit_town_center_wheelbarrow_1", queued = true}',
            scar,
        )
        self.assertIn(
            'payload = {id = "upgrade_econ_resource_food_harvest_rate_2", queued = false}',
            scar,
        )

    def test_malformed_yaml_leaves_baseline_and_never_calls_essence(self) -> None:
        (self.orders / "bad.yaml").write_text("civ: english\ntitle: Bad\nsteps: [not-a-mapping]\n", encoding="utf-8")
        calls = []
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = build_mod(self.config, lambda *args, **kwargs: calls.append((args, kwargs)))
        self.assertEqual(result, 2)
        self.assertIn("bad.yaml: steps[0]: must be a mapping", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())
        self.assertEqual(calls, [])
        self.assertEqual(self.paths.scar_output.read_text(encoding="utf-8"), "BUILD_ORDER_CATALOG = {}\n")
        self.assertEqual(self.paths.rdo_output.read_text(encoding="utf-8"), "<!-- GENERATED_BUILD_ORDER_ENUM_ITEMS -->\n")

    def test_successful_build_calls_exact_essence_command(self) -> None:
        (self.orders / "valid.yaml").write_text(VALID, encoding="utf-8")
        calls = []
        def runner(command, **kwargs):
            calls.append((command, kwargs))
            self.archive.parent.mkdir()
            self.archive.write_bytes(b"fresh")
            return subprocess.CompletedProcess(command, 0)
        self.assertEqual(build_mod(self.config, runner), 0)
        self.assertEqual(calls[0][0], [self.config.essence_launcher, "--build_mod", str(self.mod.resolve()), "--auto_close_burn_window"])

    def test_successful_build_accepts_fresh_final_archive_without_cache_changes(self) -> None:
        (self.orders / "valid.yaml").write_text(VALID, encoding="utf-8")

        def runner(command, **kwargs):
            self.archive.parent.mkdir()
            self.archive.write_bytes(b"fresh archive")
            return subprocess.CompletedProcess(command, 0)

        self.assertEqual(build_mod(self.config, runner), 0)

    def test_successful_build_waits_for_delayed_final_archive(self) -> None:
        (self.orders / "valid.yaml").write_text(VALID, encoding="utf-8")
        worker = None

        def runner(command, **kwargs):
            nonlocal worker

            def emit_archive() -> None:
                time.sleep(0.05)
                self.archive.parent.mkdir()
                self.archive.write_bytes(b"delayed archive")

            worker = threading.Thread(target=emit_archive)
            worker.start()
            return subprocess.CompletedProcess(command, 0)

        result = build_mod(self.config, runner)
        if worker is not None:
            worker.join()
        self.assertEqual(result, 0)

    def test_archive_wait_retries_transient_permission_error(self) -> None:
        before = (1, 10, "stale")
        fresh = (2, 20, "fresh")

        with (
            patch(
                "tools.build_mod._file_signature",
                side_effect=[PermissionError("archive is still locked"), fresh],
            ),
            patch("tools.build_mod.time.sleep"),
        ):
            self.assertTrue(_wait_for_fresh_archive(self.archive, before, timeout=1))

    def test_nonzero_essence_result_is_returned(self) -> None:
        (self.orders / "valid.yaml").write_text(VALID, encoding="utf-8")
        result = build_mod(self.config, lambda command, **kwargs: subprocess.CompletedProcess(command, 23))
        self.assertEqual(result, 23)

    def test_zero_exit_without_created_output_is_a_controlled_failure(self) -> None:
        (self.orders / "valid.yaml").write_text(VALID, encoding="utf-8")
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = build_mod(
                self.config,
                lambda command, **kwargs: subprocess.CompletedProcess(command, 0),
                archive_wait_seconds=0,
            )
        self.assertEqual(result, 3)
        self.assertIn("no fresh archive", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_zero_exit_with_unchanged_output_is_a_controlled_failure(self) -> None:
        (self.orders / "valid.yaml").write_text(VALID, encoding="utf-8")
        self.archive.parent.mkdir()
        self.archive.write_bytes(b"stale")
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = build_mod(
                self.config,
                lambda command, **kwargs: subprocess.CompletedProcess(command, 0),
                archive_wait_seconds=0,
            )
        self.assertEqual(result, 3)
        self.assertIn("no fresh archive", stderr.getvalue())

    def test_zero_exit_that_only_deletes_output_is_a_controlled_failure(self) -> None:
        (self.orders / "valid.yaml").write_text(VALID, encoding="utf-8")
        self.archive.parent.mkdir()
        self.archive.write_bytes(b"stale")

        def runner(command, **kwargs):
            self.archive.unlink()
            return subprocess.CompletedProcess(command, 0)

        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = build_mod(self.config, runner, archive_wait_seconds=0)
        self.assertEqual(result, 3)
        self.assertIn("no fresh archive", stderr.getvalue())

    def test_cache_only_changes_do_not_count_as_success(self) -> None:
        (self.orders / "valid.yaml").write_text(VALID, encoding="utf-8")

        def runner(command, **kwargs):
            output = self.root / "cache" / "built.package"
            output.parent.mkdir()
            output.write_bytes(b"fresh cache")
            return subprocess.CompletedProcess(command, 0)

        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = build_mod(self.config, runner, archive_wait_seconds=0)
        self.assertEqual(result, 3)
        self.assertIn("no fresh archive", stderr.getvalue())

    def test_same_size_rewrite_with_preserved_timestamp_is_fresh(self) -> None:
        (self.orders / "valid.yaml").write_text(VALID, encoding="utf-8")
        self.archive.parent.mkdir()
        self.archive.write_bytes(b"before")
        original = self.archive.stat()

        def runner(command, **kwargs):
            self.archive.write_bytes(b"after!")
            os.utime(
                self.archive,
                ns=(original.st_atime_ns, original.st_mtime_ns),
            )
            return subprocess.CompletedProcess(command, 0)

        self.assertEqual(build_mod(self.config, runner), 0)

    def test_malformed_descriptor_is_a_controlled_failure(self) -> None:
        (self.orders / "valid.yaml").write_text(VALID, encoding="utf-8")
        self.mod.write_text("not xml", encoding="utf-8")
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = build_mod(
                self.config,
                lambda command, **kwargs: subprocess.CompletedProcess(command, 0),
            )
        self.assertEqual(result, 3)
        self.assertIn("mod descriptor", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_missing_template_is_a_controlled_failure_before_essence(self) -> None:
        (self.orders / "valid.yaml").write_text(VALID, encoding="utf-8")
        self.rdo_template.unlink()
        calls = []
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            try:
                result = build_mod(
                    self.config,
                    lambda *args, **kwargs: calls.append((args, kwargs)),
                )
            except Exception as exc:
                self.fail(f"expected controlled failure, got {type(exc).__name__}: {exc}")
        self.assertEqual(result, 3)
        self.assertEqual(calls, [])
        self.assertIn("Macro Trainer.rdo", stderr.getvalue())

    def test_missing_rdo_marker_is_a_controlled_failure_before_essence(self) -> None:
        (self.orders / "valid.yaml").write_text(VALID, encoding="utf-8")
        self.rdo_template.write_text("<DataWarehouse/>", encoding="utf-8")
        calls = []
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            try:
                result = build_mod(
                    self.config,
                    lambda *args, **kwargs: calls.append((args, kwargs)),
                )
            except Exception as exc:
                self.fail(f"expected controlled failure, got {type(exc).__name__}: {exc}")
        self.assertEqual(result, 3)
        self.assertEqual(calls, [])
        self.assertIn("generated build-order enum marker", stderr.getvalue())

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
