from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from aoe4.build_orders.types import BuildOrderCheckBase, check_factory, ScarRepr, YamlRepr
from aoe4.constants import *


@check_factory
@dataclass
class UpgradeCheck(BuildOrderCheckBase):
    # TODO: Get data
    tech_id: str = ''
    queued: bool = False

    def yaml_payload(self) -> YamlRepr:
        data = {
            'id': self.tech_id,
            'queued': self.queued
        }
        if self.optional:
            data['optional'] = self.optional
        return [data]

    def datastore_payload(self) -> List[ScarRepr]:
        return [{
            'id': self.tech_id,
            'queued': self.queued
        }]

    @staticmethod
    def key() -> str:
        return "upgrades"

    # TODO: Validate ids are valid for civ
    @staticmethod
    def validate_civ_id_access(ids: List[str], civ: str):
        pass

    @staticmethod
    def _instance_from_yaml(data: Dict[str, Any], civ: str) -> UpgradeCheck:
        UpgradeCheck.validate_civ_id_access([data['id']], civ)
        return UpgradeCheck(
            tech_id=data['id'],
            optional=data.get('optional', False),
            queued=data.get('queued', False)
        )

    @staticmethod
    def from_yaml(data: YamlRepr, civ: str) -> List[UpgradeCheck]:
        if not isinstance(data, list):
            raise ValueError('upgrades must be a list in yaml')
        return [
            UpgradeCheck._instance_from_yaml(tech, civ)
            for tech in data
        ]

    @staticmethod
    def from_datastore(data: ScarRepr, civ: str) -> UpgradeCheck:
        payload = data.get('payload', {})
        UpgradeCheck.validate_civ_id_access([payload['id']], civ)
        return UpgradeCheck(
            id=data.get('id'),
            optional=data.get('optional',
                payload.get('optional', False)),
            tech_id=payload['id'],
            queued=payload.get('queued', False)
        )
