from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from aoe4.build_orders.types import BuildOrderCheckBase, check_factory, ids_dict, parse_ids, ScarRepr, YamlRepr
from aoe4.constants import *


@check_factory
@dataclass
class AgeUpCheck(BuildOrderCheckBase):
    age_ids: List[str] = field(default_factory=list)
    vils: Optional[int] = None
    is_upgrade: bool = False

    @staticmethod
    def key() -> str:
        return "age_up"

    def yaml_payload(self) -> YamlRepr:
        data = {}
        if self.vils is not None:
            data['vils'] = self.vils
        return data | ids_dict(self.age_ids)

    def datastore_payload(self) -> List[ScarRepr]:
        data = {
            'trigger': self.is_upgrade and 'upgrade' or 'construction'
        }
        if self.vils is not None:
            data['vils'] = self.vils
        return [data | ids_dict(self.age_ids)]

    # TODO: Validate ids are valid for civ
    @staticmethod
    def validate_civ_id_access(ids: List[str], civ: str):
        pass

    @staticmethod
    def from_yaml(data: YamlRepr, civ: str) -> AgeUpCheck:
        if not isinstance(data, dict):
            raise ValueError('age_up must be dict in yaml')
        ids = parse_ids(data)
        AgeUpCheck.validate_civ_id_access(ids, civ)
        return AgeUpCheck(
            age_ids=ids,
            vils=data.get('vils'),
            is_upgrade=civ in UPGRADE_CIVS
        )

    @staticmethod
    def from_datastore(data: ScarRepr, civ: str) -> AgeUpCheck:
        payload = data.get('payload', {})
        ids = parse_ids(payload)
        AgeUpCheck.validate_civ_id_access(ids, civ)
        return AgeUpCheck(
            id=data.get('id'),
            optional=data.get('optional', False),
            age_ids=ids,
            vils=payload.get('vils'),
            is_upgrade=civ in UPGRADE_CIVS
        )
