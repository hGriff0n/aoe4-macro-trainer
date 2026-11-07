from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from aoe4.build_orders import identities
from aoe4.build_orders.types import BuildOrderCheckBase, check_factory, ids_dict, parse_ids, ScarRepr, YamlRepr
from aoe4.constants import BUILDINGS, TECHNOLOGIES, UPGRADE_CIVS


def _category(civ: str) -> str:
    return TECHNOLOGIES if civ in UPGRADE_CIVS else BUILDINGS


@check_factory
@dataclass
class AgeUpCheck(BuildOrderCheckBase):
    age_ids: List[str] = field(default_factory=list)
    vils: Optional[int] = None
    is_upgrade: bool = False

    @staticmethod
    def key() -> str:
        return "age_up"

    def yaml_payload(self, civ: str) -> YamlRepr:
        data = {}
        if self.vils is not None:
            data['vils'] = self.vils
        return data | ids_dict(identities.reverse(civ, _category(civ), self.age_ids))

    def datastore_payload(self) -> List[ScarRepr]:
        data = {
            'trigger': self.is_upgrade and "upgrade" or "construction"
        }
        if self.vils is not None:
            data['vils'] = self.vils
        return [data | ids_dict(self.age_ids)]

    @staticmethod
    def from_yaml(data: YamlRepr, civ: str) -> AgeUpCheck:
        if not isinstance(data, dict):
            raise ValueError('age_up must be dict in yaml')
        return AgeUpCheck(
            age_ids=identities.resolve(civ, _category(civ), parse_ids(data)),
            vils=data.get('vils'),
            is_upgrade=civ in UPGRADE_CIVS
        )

    @staticmethod
    def from_datastore(data: ScarRepr, civ: str) -> AgeUpCheck:
        payload = data.get('payload', {})
        return AgeUpCheck(
            id=data.get('id'),
            optional=data.get('optional', False),
            age_ids=parse_ids(payload),
            vils=payload.get('vils'),
            is_upgrade=civ in UPGRADE_CIVS
        )
