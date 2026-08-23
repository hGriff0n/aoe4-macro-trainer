import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.build_orders.compiler import BuildOrderValidationError, compile_directory
from tools.build_orders.emitters import emit_outputs, reset_outputs
from tools.build_orders.model import Catalog


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


def build_mod(config: BuildConfig, runner: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> int:
    try:
        generate_assets(config)
    except BuildOrderValidationError as exc:
        print(exc, file=sys.stderr)
        return 2
    command = [config.essence_launcher, "--build_mod", str(config.mod_file.resolve()), "--auto_close_burn_window"]
    result = runner(command)
    return result.returncode


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
        return 0
    return build_mod(config)


if __name__ == "__main__":
    raise SystemExit(main())
