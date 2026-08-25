import argparse
import hashlib
import subprocess
import sys
import time
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
ARCHIVE_WAIT_SECONDS = 120
ARCHIVE_POLL_SECONDS = 0.25


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


def _validate_mod_descriptor(mod_file: Path) -> None:
    try:
        root = ET.parse(mod_file).getroot()
    except ET.ParseError as exc:
        raise BuildOperationError(f"invalid mod descriptor {mod_file}: {exc}") from exc
    element = root.find(".//{*}DataIntermediatePath")
    if element is None or element.text is None or not element.text.strip():
        raise BuildOperationError(
            f"mod descriptor {mod_file} has no DataIntermediatePath"
        )


def _archive_output_path(mod_file: Path) -> Path:
    archive_name = f"{mod_file.stem.replace(' ', '_')}.sga"
    return (mod_file.parent / "archives" / archive_name).resolve()


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_signature(path: Path) -> tuple[int, int, str] | None:
    if not path.exists():
        return None
    if not path.is_file():
        raise BuildOperationError(f"archive output path is not a file: {path}")
    stat = path.stat()
    return stat.st_mtime_ns, stat.st_size, _file_digest(path)


def _wait_for_fresh_archive(
    path: Path,
    before: tuple[int, int, str] | None,
    timeout: float,
) -> bool:
    deadline = time.monotonic() + timeout
    while True:
        after = _file_signature(path)
        if after is not None and before != after:
            return True
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        time.sleep(min(ARCHIVE_POLL_SECONDS, remaining))


def _report_operational_error(exc: Exception) -> int:
    print(f"build failed: {exc}", file=sys.stderr)
    return BUILD_OPERATION_ERROR


def build_mod(
    config: BuildConfig,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    archive_wait_seconds: float = ARCHIVE_WAIT_SECONDS,
) -> int:
    try:
        generate_assets(config)
    except BuildOrderValidationError as exc:
        print(exc, file=sys.stderr)
        return 2
    except (OSError, ValueError) as exc:
        return _report_operational_error(exc)

    try:
        _validate_mod_descriptor(config.mod_file)
        output_path = _archive_output_path(config.mod_file)
        before = _file_signature(output_path)
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
        has_fresh_archive = _wait_for_fresh_archive(
            output_path,
            before,
            archive_wait_seconds,
        )
    except (OSError, BuildOperationError) as exc:
        return _report_operational_error(exc)
    if not has_fresh_archive:
        return _report_operational_error(
            BuildOperationError(
                f"Essence exited successfully but produced no fresh archive at {output_path}"
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
