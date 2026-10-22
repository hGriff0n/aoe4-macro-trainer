from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from aoe4.build_orders.types import BuildOrderCheckBase, check_factory, ScarRepr, YamlRepr
from aoe4.constants import *


@check_factory
@dataclass
class ResourceCheck(BuildOrderCheckBase):
    resources: Dict[str, int] = field(default_factory=dict)

    def yaml_payload(self) -> YamlRepr:
        return self.resources

    def datastore_payload(self) -> List[ScarRepr]:
        return [{
            'count': c,
            'resource': r
        } for r, c in self.resources.items()]

    @staticmethod
    def key() -> str:
        return "resources"

    @staticmethod
    def from_yaml(data: YamlRepr, civ: str) -> ResourceCheck:
        if not isinstance(data, dict):
            raise ValueError('resources must be a dict in yaml')
        return ResourceCheck(
            resources={
                res: data[res] for res in [
                    FOOD_RES, GOLD_RES, STONE_RES, WOOD_RES]
                if res in data
            }
        )

    @staticmethod
    def from_datastore(data: ScarRepr, civ: str) -> ResourceCheck:
        payload = data.get('payload', {})
        return ResourceCheck(
            id=data.get('id'),
            optional=data.get('optional', False),
            resources={
                payload['resource']: payload['count']
            }
        )
