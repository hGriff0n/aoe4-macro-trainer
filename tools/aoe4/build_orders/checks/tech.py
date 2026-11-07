from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from aoe4.build_orders import identities
from aoe4.build_orders.types import BuildOrderCheckBase, check_factory, ids_dict, parse_ids, ScarRepr, YamlRepr
from aoe4.constants import UPGRADES


@check_factory
@dataclass
class UpgradeCheck(BuildOrderCheckBase):
    tech_ids: List[str] = field(default_factory=list)
    queued: bool = False

    def yaml_payload(self, civ: str) -> YamlRepr:
        data = {'queued': self.queued}
        if self.optional:
            data['optional'] = self.optional
        return [ids_dict(identities.reverse(civ, UPGRADES, self.tech_ids)) | data]

    def datastore_payload(self) -> List[ScarRepr]:
        return [ids_dict(self.tech_ids) | {'queued': self.queued}]

    @staticmethod
    def key() -> str:
        return "upgrades"

    @staticmethod
    def _instance_from_yaml(data: Dict[str, Any], civ: str) -> UpgradeCheck:
        return UpgradeCheck(
            tech_ids=identities.resolve(civ, UPGRADES, parse_ids(data)),
            optional=data.get('optional', False),
            queued=data.get('queued', False)
        )

    @staticmethod
    def from_yaml(data: YamlRepr, civ: str) -> List[UpgradeCheck]:
        if not isinstance(data, list):
            raise ValueError("upgrades must be a list in yaml")
        return [
            UpgradeCheck._instance_from_yaml(tech, civ)
            for tech in data
        ]

    @staticmethod
    def from_datastore(data: ScarRepr, civ: str) -> UpgradeCheck:
        payload = data.get('payload', {})
        return UpgradeCheck(
            id=data.get('id'),
            optional=data.get('optional',
                payload.get('optional', False)),
            tech_ids=parse_ids(payload),
            queued=payload.get('queued', False)
        )
