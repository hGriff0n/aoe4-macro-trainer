import luadata
from pathlib import Path

from aoe4.build_orders.types import BuildOrder, BuildOrderStep, CheckRegistry


_registered_checks = CheckRegistry()


@dataclass
class Datastore:
    schema_version: int
    build_orders: Dict[str, BuildOrder]
    filepath: Path


def load_datastore(rt_file: Path) -> Datastore:
    # Skip `LuaDataStore = ` because luadata expects a `{` at the start
    with rt_file.open('r') as f:
        data = luadata.unserialize(f.read()[15:])[rt_file.stem]

    d = Datastore(
        schema_version=data['schema_version'],
        build_orders={},
        filepath=rt_file
    )
    for id, bo in data.get('build_orders', {}):
        bo = BuildOrder(
            id=id, civ=bo['civ'], title=bo['title'])
        for raw_step in bo.get('steps', []):
            step = BuildOrderStep()
            if 'title' in raw_step:
                step.title = raw_step['title']
            for check in raw_step.get('checks', []):
                if check['kind'] in _registered_checks:
                    step.checks.append(
                        _registered_checks[check['kind']].from_datastore(
                            check)
                    )
                else:
                    print(f'Unexpected check in datastore: {check}. Ignoring')

            bo.steps.append(step)
        d.build_orders[id] = bo
    return d


def _build_step_to_datastore(step: BuildOrderStep) -> Dict[str, Any]:
    data = {
        checks = []
    }
    if step.title:
        data['title'] = step.title
    for check in step.checks:
        data['checks'].append(
            _registry[check.key()].to_datastore(check))
    return data

def _build_order_to_datastore(bo: BuildOrder) -> Dict[str, Any]:
    data = {
        civ: bo.civ,
        id: bo.id,
        title: bo.title,
        step: []
    }
    if bo.link:
        data['link'] = bo.link
    for step in bo.steps:
        data['steps'].append(_build_step_to_datastore(step))
    return data


def save_datastore(ds: Datastore):
    data = {
        'schema_version': ds.schema_version,
        'build_orders': {}
    }
    for id, bo in ds.build_orders.items():
        data['build_orders'][id] = _build_order_to_datastore(bo)

    with ds.filepath.open('w') as f:
        f.write('LuaDataStoreID = ')
        f.write(luadata.serialize(data))