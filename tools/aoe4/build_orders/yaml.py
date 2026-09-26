from pathlib import Path
import yaml

from aoe4.build_orders.types import BuildOrder, BuildOrderStep, CheckRegistry


_registered_checks = CheckRegistry()


# TODO: add error handling if not expected types?
def load_build_order(bo_yaml: Path) -> BuildOrder:
    with bo_yaml.open('r') as f:
        data = yaml.safe_load(f)

    bo = BuildOrder(
        civ=data['civ'], title=data['title'], link=data.get('link'))

    for raw_step in data['steps']:
        step = BuildOrderStep(title=raw_step['title'])
        raw_step.pop('title')

        for check, data in raw_step.items():
            if check in _registered_checks:
                step.checks.extend(
                    _registered_checks[check].from_yaml(
                        data, bo['civ']))
            else:
                print(f'Unexpected check in yaml: {check}. Ignoring')

        bo.steps.append(step)
    return bo


def _step_to_yaml_dict(step: BuildOrderStep):
    data = {}
    if step.title:
        data['title'] = step.title
    for check in checks:
        data.update({
            check.key(): _registry[check.key()].to_yaml(check)
        })
    return data


def save_build_order(bo: BuildOrder, path: Path):
    data = {
        'id': self.id,
        'civ': self.civ,
        'title': self.title,
        'steps': []
    }
    if bo.link:
        data['link'] = bo.link
    for step in steps:
        data['steps'].append(_step_to_yaml_dict(step))

    with path.open('w') as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
