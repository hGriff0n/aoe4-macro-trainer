from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from aoe4.build_orders.types import BuildOrderCheckBase, check_factory, ScarRepr, YamlRepr
from aoe4.constants import *


@check_factory
@dataclass
class VilCheck(BuildOrderCheckBase):
    resources: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def key() -> str:
        return "vils"

    def yaml_payload(self) -> YamlRepr:
        return self.resources

    def datastore_payload(self) -> List[ScarRepr]:
        return [self.resources]

    @staticmethod
    def validate_resource_keys(payload: Dict[str, Any]):
        _VALID_KEYS = [FOOD_RES, GOLD_RES, WOOD_RES, STONE_RES]
        bad_keys = [k for k in payload.keys() if k not in _VALID_KEYS]
        if bad_keys:
            raise ValueError(f'Received unexpected key in VilCheck: {",".join(bad_keys)}')

    @staticmethod
    def from_yaml(data: YamlRepr, civ: str) -> VilCheck:
        if not isinstance(data, dict):
            raise ValueError('Vils must be a dict in yaml')
        VilCheck.validate_resource_keys(data)
        return VilCheck(resources=data)

    @staticmethod
    def from_datastore(data: ScarRepr, civ: str) -> VilCheck:
        payload = data.get('payload', {})
        VilCheck.validate_resource_keys(payload)
        return VilCheck(
            id=data.get('id'),
            optional=data.get('optional', False),
            resources=payload
        )
