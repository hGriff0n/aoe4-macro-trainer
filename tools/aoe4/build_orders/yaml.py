from pathlib import Path
from typing import Any, Dict

import yaml

from aoe4.build_orders.types import BuildOrder, BuildOrderStep, CheckRegistry


_registered_checks = CheckRegistry()


# TODO: Do I need to add error handling? like with json.py
def read_yaml(yaml_file: Path) -> Dict[str, Any]:
    with yaml_file.open('r', encoding='utf-8') as f:
        return yaml.safe_load(f)


# TODO: add error handling if not expected types?
def build_order_from_yaml_dict(
        yaml_repr: Dict[str, Any], default_id: str | None = None) -> BuildOrder:
    bo = BuildOrder(
        id=yaml_repr.get('id', default_id), civ=yaml_repr['civ'],
        title=yaml_repr['title'], metadata=yaml_repr.get('meta', {}))
    if 'link' in yaml_repr:
        bo.metadata['link'] = yaml_repr['link']

    for raw_step in yaml_repr['steps']:
        step = BuildOrderStep(title=raw_step.pop('title', None))

        for check, check_data in raw_step.items():
            if check in _registered_checks:
                step.checks.extend(
                    _registered_checks[check].from_yaml(
                        check_data, bo.civ))
            else:
                print(f'Unexpected check in yaml: {check}. Ignoring')

        bo.steps.append(step)
    return bo


def load_build_order(bo_yaml: Path) -> BuildOrder:
    data = read_yaml(bo_yaml, default_id=bo_yaml.stem)
    return build_order_from_yaml_dict(data)


def _step_to_yaml_dict(step: BuildOrderStep) -> Dict[str, Any]:
    data = {}
    if step.title:
        data['title'] = step.title
    for check in step.checks:
        payload = _registered_checks[check.key()].to_yaml(check)
        # Datastore splits checks up, so merge them back under one key
        if check.key() not in data:
            data[check.key()] = payload.copy()
        elif isinstance(payload, list):
            data[check.key()].extend(payload)
        else:
            data[check.key()].update(payload)
    return data


def save_build_order(bo: BuildOrder, path: Path):
    data = {
        'id': bo.id,
        'civ': bo.civ,
        'title': bo.title,
        'steps': [],
        'meta': bo.metadata
    }
    for step in bo.steps:
        data['steps'].append(_step_to_yaml_dict(step))

    with path.open('w', encoding='utf-8') as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
