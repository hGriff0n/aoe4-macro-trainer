
import argparse

import aoe4.build_orders.checks.register_all
import aoe4.build_orders.datastore
import aoe4.build_orders.yaml
import aoe4.files


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
    
    for command in (build, listing, delete, extract):
        command.add_argument("--profile", type=str, help="User id in case multipler users are signed in on the same machine")

    return parser


# TODO: Not sure on error handling
def _build_order(f: Path) -> Optional[BuildOrder]:
    return yaml.load_build_order(f)

# TODO: Ideally this would be agnostic to also allow urls
def _comp_build_orders(p: Path) -> List[BuildOrder]:
    if p.is_dir():
        return filter(lambda b: b is not None, [
            _build_order(f) for f in p.listdir()
        ])

    return [_build_order(p)]

# TODO: Handle id collisions
def add_to_datastore(args, d: Datastore):
    for path in args.inputs:
        d.build_orders.extend(_comp_build_orders(path))
    datastore.save_datastore(d)

def list_datastore_build_orders(args, d: Datastore):
    print('Build Orders:')
    print('\n'.join(map(lambda bo: f'- {bo.id}', d.build_orders)))

def remove_from_datastore(args, d: Datastore):
    d.build_orders = filter(
        lambda bo: bo.id not in args.ids, d.build_orders)
    datastore.save_datastore(d)

# TODO: Might need to handle invalid chars
def decomp_datastore(args, ds: Datastore):
    for bo in ds.build_orders:
        yaml.save_build_order(args.inputs() / bo.id, bo)

def _resolve_datastore(args) -> Datastore:
    dir = files.datastore_dir(
        profile_id=(args.profile if args.profile else None))
    rt_file = dir / 'macroBuildTrainer.rt'
    return datastore.load_datastore(rt_file), rt_file

def main():
    args = _parser().parse_args()
    d = _resolve_datastore(args)
    args.func(args, d)