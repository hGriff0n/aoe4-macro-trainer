from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

import luadata

from aoe4.build_orders.types import BuildOrder, BuildOrderStep, CheckRegistry


SCHEMA_VERSION = 2
_PREFIX = 'LuaDataStore = '

_registered_checks = CheckRegistry()


@dataclass
class Datastore:
    schema_version: int
    build_orders: Dict[str, BuildOrder]
    filepath: Path


def load_datastore(rt_file: Path) -> Datastore:
    d = Datastore(
        schema_version=SCHEMA_VERSION,
        build_orders={},
        filepath=rt_file
    )
    # The first build creates the datastore
    if not rt_file.exists():
        return d

    # Skip `LuaDataStore = ` because luadata expects a `{` at the start
    with rt_file.open('r', encoding='utf-8') as f:
        data = luadata.unserialize(f.read()[len(_PREFIX):])[rt_file.stem]

    d.schema_version = data['schema_version']
    for id, raw_bo in data.get('build_orders', {}).items():
        bo = BuildOrder(
            id=id, civ=raw_bo['civ'], title=raw_bo['title'],
            link=raw_bo.get('link'))
        for raw_step in raw_bo.get('steps', []):
            step = BuildOrderStep(title=raw_step.get('title'))
            for check in raw_step.get('checks', []):
                if check['kind'] in _registered_checks:
                    step.checks.append(
                        _registered_checks[check['kind']].from_datastore(
                            check, bo.civ)
                    )
                else:
                    print(f'Unexpected check in datastore: {check}. Ignoring')

            bo.steps.append(step)
        d.build_orders[id] = bo
    return d


def _build_step_to_datastore(step: BuildOrderStep) -> Dict[str, Any]:
    data = {
        'checks': []
    }
    if step.title:
        data['title'] = step.title
    for check in step.checks:
        data['checks'].extend(
            _registered_checks[check.key()].to_datastore(check))
    return data

def _build_order_to_datastore(bo: BuildOrder) -> Dict[str, Any]:
    data = {
        'civ': bo.civ,
        'id': bo.id,
        'title': bo.title,
        'steps': []
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

    ds.filepath.parent.mkdir(parents=True, exist_ok=True)
    with ds.filepath.open('w', encoding='utf-8') as f:
        f.write(_PREFIX)
        f.write(luadata.serialize({ds.filepath.stem: data}, indent='    '))
