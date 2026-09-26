from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from aoe4.build_orders.types import BuildOrderCheckBase, check_factory, ids_dict, parse_ids, ScarRepr, YamlRepr


@check_factory
@dataclass
class BuiltCheck(BuildOrderCheckBase):
    count: int = 1
    building_ids: List[str] = field(default_factory=list)
    vils: Optional[int] = None
    location: Optional[str] = None

    def _payload(self) -> Dict[str, Any]:
        data = {'count': self.count}
        if self.vils:
            data['vils'] = self.vils
        if self.location:
            data['location'] = self.location
        return data | ids_dict(self.building_ids)

    def yaml_payload(self) -> YamlRepr:
        return [self._payload()]

    def datastore_payload(self) -> List[ScarRepr]:
        return [self._payload()]

    @staticmethod
    def key() -> str:
        return "built"

    # TODO: Validate ids are valid for civ
    @staticmethod
    def validate_civ_id_access(ids: List[str], civ: str):
        pass

    @staticmethod
    def _instance_from_yaml(data: Dict[str, Any], civ: str) -> BuiltCheck:
        ids = parse_ids(data)
        BuiltCheck.validate_civ_id_access(ids, civ)
        return BuiltCheck(
            building_ids=ids,
            count=data.get('count', 1),
            vils=data.get('vils'),
            location=data.get('location')
        )

    @staticmethod
    def from_yaml(data: YamlRepr, civ: str) -> List[BuiltCheck]:
        if not isinstance(data, list):
            raise ValueError('built must be a list in yaml')
        return [
            BuiltCheck._instance_from_yaml(building, civ)
            for building in data
        ]

    @staticmethod
    def from_datastore(data: ScarRepr, civ: str) -> BuiltCheck:
        payload = data.get('payload', {})
        ids = parse_ids(payload)
        BuiltCheck.validate_civ_id_access(ids, civ)
        return BuiltCheck(
            id=data.get('id'),
            optional=data.get('optional', False),
            count=payload.get('count', 1),
            building_ids=ids,
            vils=payload.get('vils'),
            location=payload.get('location')
        )
