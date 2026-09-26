import argparse
from pathlib import Path
from typing import List, Optional

import aoe4.build_orders.checks.register_all
from aoe4.build_orders import datastore, yaml
from aoe4.build_orders.datastore import Datastore
from aoe4.build_orders.types import BuildOrder
from aoe4 import files


_DATASTORE_FILE = 'macroTrainerBuildOrders.rlt'


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage Macro Trainer build orders")

    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="compile YAML into the datastore")
    build.set_defaults(func=add_to_datastore)
    build.add_argument("inputs", nargs="*", type=Path, default=[Path("build_orders")])

    listbo = commands.add_parser("list", help="list compiled build orders")
    listbo.set_defaults(func=list_datastore_build_orders)

    delete = commands.add_parser("delete", help="delete compiled build orders")
    delete.set_defaults(func=remove_from_datastore)
    delete.add_argument("ids", nargs="+")

    extract = commands.add_parser("extract", help="extract normalized YAML")
    extract.set_defaults(func=decomp_datastore)
    extract.add_argument("ids", nargs="+")
    extract.add_argument("--output-dir", type=Path, default=Path.cwd())

    for command in (build, listbo, delete, extract):
        command.add_argument("--profile", type=str, help="User id in case multipler users are signed in on the same machine")

    return parser


# TODO: Not sure on error handling
def _build_order(f: Path) -> Optional[BuildOrder]:
    try:
        return yaml.load_build_order(f)
    except Exception as e:
        print(f'Skipping {f}: {e!r}')
        return None

# TODO: Ideally this would be agnostic to also allow urls
def _comp_build_orders(p: Path) -> List[BuildOrder]:
    if p.is_dir():
        paths = sorted(f for f in p.rglob('*') if f.suffix in ('.yaml', '.yml'))
    else:
        paths = [p]
    return [bo for bo in map(_build_order, paths) if bo is not None]

# TODO: Handle id collisions
def add_to_datastore(args, d: Datastore):
    for path in args.inputs:
        for bo in _comp_build_orders(path):
            d.build_orders[bo.id] = bo
    datastore.save_datastore(d)
    print(f'Saved {len(d.build_orders)} build orders to {d.filepath}')

def list_datastore_build_orders(args, d: Datastore):
    print('Build Orders:')
    print('\n'.join(f'- {id}' for id in d.build_orders))

def remove_from_datastore(args, d: Datastore):
    for id in args.ids:
        d.build_orders.pop(id, None)
    datastore.save_datastore(d)

# TODO: Might need to handle invalid chars
def decomp_datastore(args, ds: Datastore):
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for id in args.ids:
        yaml.save_build_order(ds.build_orders[id], args.output_dir / f'{id}.yaml')

def _resolve_datastore(args) -> Datastore:
    dir = files.datastore_dir(profile_id=args.profile)
    return datastore.load_datastore(dir / _DATASTORE_FILE)

def main():
    args = _parser().parse_args()
    d = _resolve_datastore(args)
    args.func(args, d)


if __name__ == '__main__':
    main()
