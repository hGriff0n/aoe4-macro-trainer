import argparse
from pathlib import Path
from typing import List, Optional

import aoe4.build_orders.checks.register_all as _  # checks registered to singleton
from aoe4.build_orders import datastore, importer, json, yaml
from aoe4.build_orders.datastore import Datastore
from aoe4.build_orders.types import BuildOrder
from aoe4 import files


_DATASTORE_FILE = 'macroTrainerBuildOrders.rlt'
_ALLOWED_SUFFIXES = (".yaml", ".yml", ".json")


def _file_ext(p: Path) -> str:
    return p.suffix.lower()


def _build_order(f: Path) -> Optional[BuildOrder]:
    try:
        ext = _file_ext(f)
        if ext in (".yaml", ".yml"):
            return yaml.load_build_order(f)
        if ext in (".json"):
            data = json.read_json(f)
            # TODO: ai used `identities` in `_compile_order`
            return yaml.build_order_from_yaml_dict(data, default_id=f.stem)
        return None
    except Exception as e:
        print(f'Error compiling build order at {f}: {e!r}')
        return None


def _comp_build_orders(p: Path) -> List[BuildOrder]:
    paths = []
    if p.is_dir():
        paths = sorted(f for f in p.rglob('*') if _file_ext(f) in _ALLOWED_SUFFIXES)
    elif _file_ext(p) in _ALLOWED_SUFFIXES:
        paths = [p]
    return [bo for bo in map(_build_order, paths) if bo is not None]


def _add_bo_respecting_dry_run(ds: Datastore, bo: BuildOrder, dry_run: bool):
    if not dry_run:
        ds.build_orders[bo.id] = bo

    elif bo.id in ds.build_orders:
        print(f"(*) Overwritting/updating build order `{bo.id}`")
        # TODO: Report what the diffs are???

    else:
        print(f"(+) Added new build order `{bo.id}`")


# TODO: This currently overwrites the datastore on collisions. Do I want this?
# The previous code instead raised an error, which seems excessive
# Maybe record any overwritten orders to a temp file?
def add_to_datastore(args, ds: Datastore):
    for path in args.inputs:
        for bo in _comp_build_orders(path):
            _add_bo_respecting_dry_run(ds, bo, args.dry_run)

    if not args.dry_run:
        datastore.save_datastore(ds)


def list_datastore_build_orders(args, ds: Datastore):
    print('Build Orders:')
    print('\n'.join(f'- {id}' for id in ds.build_orders))


def remove_from_datastore(args, ds: Datastore):
    if args.dry_run:
        for id in args.ids:
            if id in ds.build_orders:
                print(f'(-) Deleted build order `{id}`')
            else:
                print(f'(?) No build order found with id={id}')
        return

    for id in args.ids:
        ds.build_orders.pop(id, None)

    datastore.save_datastore(ds)


# TODO: Might need to handle invalid chars
def decomp_datastore(args, ds: Datastore):
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for id in args.ids:
        if id in ds.build_orders:
            # TODO: ai used `identities` in `order_to_yaml`
            yaml.save_build_order(ds.build_orders[id], args.output_dir / f'{id}.yaml')
        else:
            print(f'No build order found with id={id}')


def import_build_order(args, ds: Datastore):
    if not (args.files or args.urls):
        print(f'Must specify either `--files` or `--urls` when importing')
        return

    if args.save_yaml:
        args.output_dir.mkdir(parents=True, exist_ok=True)

    for bo in importer.import_build_orders(args.files, args.urls):
        if args.save_yaml:
            yaml.save_build_order(bo, args.output_dir / f'{bo.id}.yaml')
        _add_bo_respecting_dry_run(ds, bo, args.dry_run)

    if not args.dry_run:
        datastore.save_datastore(ds)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage Macro Trainer build orders")

    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="compile YAML into the datastore")
    build.set_defaults(func=add_to_datastore)
    build.add_argument("inputs", nargs="*", type=Path, default=[Path("build_orders")])
    build.add_argument("--dry_run", action="store_true")

    listbo = commands.add_parser("list", help="list compiled build orders")
    listbo.set_defaults(func=list_datastore_build_orders)

    delete = commands.add_parser("delete", help="delete compiled build orders")
    delete.set_defaults(func=remove_from_datastore)
    delete.add_argument("ids", nargs="+")
    delete.add_argument("--dry_run", action="store_true")

    extract = commands.add_parser("extract", help="extract normalized YAML")
    extract.set_defaults(func=decomp_datastore)
    extract.add_argument("ids", nargs="+")
    extract.add_argument("--output-dir", type=Path, default=Path.cwd())

    importbo = commands.add_parser("import", help="import build order from RtsOverlay/aoe4guides/etc")
    importbo.set_defaults(func=import_build_order)
    importbo.add_argument("--files", nargs="*", type=Path)
    importbo.add_argument("--urls", nargs="*", type=importer.AoE4Url.parse_arg)
    importbo.add_argument("--save_yaml", action="store_true")
    importbo.add_argument("--dry_run", action="store_true")
    importbo.add_argument("--output-dir", type=Path, default=Path.cwd())

    for command in (build, listbo, delete, extract, importbo):
        command.add_argument("--profile", type=str, help="User id in case multipler users are signed in on the same machine")

    return parser


def main():
    args = _parser().parse_args()
    datastore_dir = files.datastore_dir(profile_id=args.profile)
    bo_datastore = datastore.load_datastore(datastore_dir / _DATASTORE_FILE)
    args.func(args, bo_datastore)


if __name__ == '__main__':
    main()
