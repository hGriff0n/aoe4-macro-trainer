import argparse
import hashlib
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.build_orders.compiler import BuildOrderValidationError, compile_directory
from tools.build_orders.emitters import emit_outputs, reset_outputs
from tools.build_orders.model import Catalog


BUILD_OPERATION_ERROR = 3


class BuildOperationError(RuntimeError):
    pass


@dataclass(frozen=True)
class BuildPaths:
    project_root: Path
    rdo_template: Path
    locdb_template: Path
    rdo_output: Path
    locdb_output: Path
    scar_output: Path


@dataclass(frozen=True)
class BuildConfig:
    paths: BuildPaths
    build_order_dir: Path
    mod_file: Path
    essence_launcher: Path


def generate_assets(config: BuildConfig) -> Catalog:
    reset_outputs(config.paths)
    catalog = compile_directory(config.build_order_dir)
    emit_outputs(catalog, config.paths)
    return catalog


def _intermediate_output_path(mod_file: Path) -> Path:
    try:
        root = ET.parse(mod_file).getroot()
    except ET.ParseError as exc:
        raise BuildOperationError(f"invalid mod descriptor {mod_file}: {exc}") from exc
    element = root.find(".//{*}DataIntermediatePath")
    if element is None or element.text is None or not element.text.strip():
        raise BuildOperationError(
            f"mod descriptor {mod_file} has no DataIntermediatePath"
        )
    configured = Path(element.text.strip())
    if not configured.is_absolute():
        configured = mod_file.parent / configured
    return configured.resolve()


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _snapshot_files(root: Path) -> dict[str, tuple[int, int, str]]:
    if not root.exists():
        return {}
    if not root.is_dir():
        raise BuildOperationError(f"intermediate output path is not a directory: {root}")
    snapshot: dict[str, tuple[int, int, str]] = {}
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        stat = path.stat()
        snapshot[path.relative_to(root).as_posix()] = (
            stat.st_mtime_ns,
            stat.st_size,
            _file_digest(path),
        )
    return snapshot


def _report_operational_error(exc: Exception) -> int:
    print(f"build failed: {exc}", file=sys.stderr)
    return BUILD_OPERATION_ERROR


def build_mod(config: BuildConfig, runner: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> int:
    try:
        generate_assets(config)
    except BuildOrderValidationError as exc:
        print(exc, file=sys.stderr)
        return 2
    except (OSError, ValueError) as exc:
        return _report_operational_error(exc)

    try:
        output_path = _intermediate_output_path(config.mod_file)
        before = _snapshot_files(output_path)
    except (OSError, BuildOperationError) as exc:
        return _report_operational_error(exc)

    command = [config.essence_launcher, "--build_mod", str(config.mod_file.resolve()), "--auto_close_burn_window"]
    try:
        result = runner(command)
    except (OSError, subprocess.SubprocessError) as exc:
        return _report_operational_error(exc)
    if result.returncode != 0:
        return result.returncode

    try:
        after = _snapshot_files(output_path)
    except (OSError, BuildOperationError) as exc:
        return _report_operational_error(exc)
    has_fresh_file = any(before.get(path) != signature for path, signature in after.items())
    if not has_fresh_file:
        return _report_operational_error(
            BuildOperationError(
                f"Essence exited successfully but produced no fresh files in {output_path}"
            )
        )
    return 0


def default_config(project_root: Path, build_orders: Path) -> BuildConfig:
    assets = project_root / "assets"
    return BuildConfig(
        BuildPaths(project_root, project_root / "build" / "templates" / "assets" / "scar" / "winconditions" / "Macro Trainer.rdo", project_root / "build" / "templates" / "assets" / "locdb" / "Macro Trainer_en.csv", assets / "scar" / "winconditions" / "Macro Trainer.rdo", assets / "locdb" / "Macro Trainer_en.csv", assets / "scar" / "generated" / "build_orders.scar"),
        build_orders, project_root / "Macro Trainer.aoe4mod", Path(r"F:\Program Files (x86)\Steam\steamapps\common\Age of Empires IV Content Editor\EssenceLauncher.exe"),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-orders", type=Path, default=Path("build_orders"))
    parser.add_argument("--generate-only", action="store_true")
    args = parser.parse_args(argv)
    root = PROJECT_ROOT
    config = default_config(root, (root / args.build_orders).resolve() if not args.build_orders.is_absolute() else args.build_orders)
    if args.generate_only:
        try:
            generate_assets(config)
        except BuildOrderValidationError as exc:
            print(exc, file=sys.stderr)
            return 2
        except (OSError, ValueError) as exc:
            return _report_operational_error(exc)
        return 0
    return build_mod(config)


if __name__ == "__main__":
    raise SystemExit(main())
