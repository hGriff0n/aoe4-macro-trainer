from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from aoe4.build_orders import identities
from aoe4.build_orders.types import BuildOrderCheckBase, check_factory, ScarRepr, YamlRepr
from aoe4.constants import UNITS


@check_factory
@dataclass
class UnitCheck(BuildOrderCheckBase):
    unit_ids: List[str] = field(default_factory=list)
    count: int = 1

    @staticmethod
    def key() -> str:
        return "units"

    def yaml_payload(self, civ: str) -> YamlRepr:
        return [{
            'id': identities.reverse(civ, UNITS, self.unit_ids)[0],
            'count': self.count
        }]

    def datastore_payload(self) -> List[ScarRepr]:
        return [{
            'ids': self.unit_ids,
            'count': self.count,
        }]

    @staticmethod
    def _instance_from_yaml(data: Dict[str, Any], civ: str) -> UnitCheck:
        return UnitCheck(
            unit_ids=identities.resolve(civ, UNITS, [data['id']]),
            count=data.get('count', 1),
        )

    @staticmethod
    def from_yaml(data: YamlRepr, civ: str) -> List[UnitCheck]:
        if not isinstance(data, list):
            raise ValueError("units must be a list in yaml")
        return [
            UnitCheck._instance_from_yaml(unit, civ)
            for unit in data
        ]

    @staticmethod
    def from_datastore(data: ScarRepr, civ: str) -> UnitCheck:
        payload = data.get('payload', {})
        return UnitCheck(
            id=data.get('id'),
            optional=data.get('optional', False),
            unit_ids=payload['ids'],
            count=payload.get('count', 1)
        )


@check_factory
@dataclass
class ProductionCheck(BuildOrderCheckBase):
    unit_ids: List[str] = field(default_factory=list)
    count: int = 1
    constant: bool = False
    queued: bool = False

    @staticmethod
    def key() -> str:
        return "produce"

    def yaml_payload(self, civ: str) -> YamlRepr:
        return [{
            'id': identities.reverse(civ, UNITS, self.unit_ids)[0],
            'count': self.count,
            'constant': self.constant,
            'queued': self.queued
        }]

    def datastore_payload(self) -> List[ScarRepr]:
        return [{
            'ids': self.unit_ids,
            'count': self.count,
            'constant': self.constant,
            'queued': self.queued
        }]

    @staticmethod
    def _instance_from_yaml(data: Dict[str, Any], civ: str) -> ProductionCheck:
        return ProductionCheck(
            unit_ids=identities.resolve(civ, UNITS, [data['id']]),
            count=data.get('count', 1),
            constant=data.get('constant', False),
            queued=data.get('queued', False)
        )

    @staticmethod
    def from_yaml(data: YamlRepr, civ: str) -> List[ProductionCheck]:
        if not isinstance(data, list):
            raise ValueError('produce must be a list in yaml')
        return [
            ProductionCheck._instance_from_yaml(unit, civ)
            for unit in data
        ]

    @staticmethod
    def from_datastore(data: ScarRepr, civ: str) -> ProductionCheck:
        payload = data.get('payload', {})
        return ProductionCheck(
            id=data.get('id'),
            optional=data.get('optional', False),
            unit_ids=payload['ids'],
            count=payload.get('count', 1),
            constant=payload.get('constant', False),
            queued=payload.get('queued', False)
        )
