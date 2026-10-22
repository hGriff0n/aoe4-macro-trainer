from pathlib import Path
from typing import Any, Dict

import yaml

from aoe4.build_orders.types import BuildOrder, BuildOrderStep, CheckRegistry


_registered_checks = CheckRegistry()


# TODO: Do I need to add error handling?
def read_yaml(yaml_file: Path) -> Dict[str, Any]:
    with yaml_file.open('r', encoding='utf-8') as f:
        return yaml.safe_load(f)


# TODO: ai used `identities` in `_compile_order`
# - units -> _resolve_counted_squad
# - buildings -> _resolve_identity_payload
# - produce -> _resolve_counted_squad -> _resolve_squad_family_payload -> IdentityCatalog:resolve_squad_family
# - upgrades -> _resolve_identity_payload
# - age_up -> _structure_checks -> _resolve_identity_payload -> IdentityCatalog:resolve
# - built -> _structure_checks -> _resolve_identity_payload
#
# Identities just looks to be a mapping from human ids to game ids
# I'm not sure how it goes from `spearman2` to `spearman though`
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


# TODO: ai used `identities` in `order_to_yaml`
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
