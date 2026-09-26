from pathlib import Path
from typing import Any, Dict

import yaml

from aoe4.build_orders.types import BuildOrder, BuildOrderStep, CheckRegistry


_registered_checks = CheckRegistry()


# TODO: add error handling if not expected types?
def load_build_order(bo_yaml: Path) -> BuildOrder:
    with bo_yaml.open('r', encoding='utf-8') as f:
        data = yaml.safe_load(f)

    bo = BuildOrder(
        id=data.get('id', bo_yaml.stem), civ=data['civ'],
        title=data['title'], link=data.get('link'))

    for raw_step in data['steps']:
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
        'steps': []
    }
    if bo.link:
        data['link'] = bo.link
    for step in bo.steps:
        data['steps'].append(_step_to_yaml_dict(step))

    with path.open('w', encoding='utf-8') as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
