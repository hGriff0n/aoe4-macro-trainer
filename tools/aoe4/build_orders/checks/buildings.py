from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from aoe4.build_orders import identities
from aoe4.build_orders.types import BuildOrderCheckBase, check_factory, ids_dict, parse_ids, ScarRepr, YamlRepr
from aoe4.constants import BUILDINGS


@check_factory
@dataclass
class BuiltCheck(BuildOrderCheckBase):
    count: int = 1
    building_ids: List[str] = field(default_factory=list)
    vils: Optional[int] = None
    location: Optional[str] = None

    def _payload(self, ids: List[str]) -> Dict[str, Any]:
        data = {'count': self.count}
        if self.vils:
            data['vils'] = self.vils
        if self.location:
            data['location'] = self.location
        return data | ids_dict(ids)

    def yaml_payload(self, civ: str) -> YamlRepr:
        return [self._payload(identities.reverse(civ, BUILDINGS, self.building_ids))]

    def datastore_payload(self) -> List[ScarRepr]:
        return [self._payload(self.building_ids)]

    @staticmethod
    def key() -> str:
        return "built"

    @staticmethod
    def _instance_from_yaml(data: Dict[str, Any], civ: str) -> BuiltCheck:
        return BuiltCheck(
            building_ids=identities.resolve(civ, BUILDINGS, parse_ids(data)),
            count=data.get('count', 1),
            vils=data.get('vils'),
            location=data.get('location')
        )

    @staticmethod
    def from_yaml(data: YamlRepr, civ: str) -> List[BuiltCheck]:
        if not isinstance(data, list):
            raise ValueError("built must be a list in yaml")
        return [
            BuiltCheck._instance_from_yaml(building, civ)
            for building in data
        ]

    @staticmethod
    def from_datastore(data: ScarRepr, civ: str) -> BuiltCheck:
        payload = data.get('payload', {})
        return BuiltCheck(
            id=data.get('id'),
            optional=data.get('optional', False),
            count=payload.get('count', 1),
            building_ids=parse_ids(payload),
            vils=payload.get('vils'),
            location=payload.get('location')
        )
