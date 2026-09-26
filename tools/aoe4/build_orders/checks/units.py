from aoe4.build_orders.types import BuildOrderCheckBase, make_factory, ScarRepr, YamlRepr
from aoe4.constants import *


@make_factory
class UnitCheck(BuildOrderCheckBase):
    unit_ids: List[str] = []
    count: int = 1

    @staticmethod
    def key() -> str:
        return "units"

    def yaml_payload(self) -> YamlRepr:
        return [{
            id: self.unit_ids[0],
            count: self.count
        }]

    def datastore_payload(self) -> List[ScarRepr]:
        return [{
            ids: self.unit_ids,
            count: self.count,
        }]

    # TODO: Validate ids are valid for civ
    @staticmethod
    def validate_civ_id_access(ids: List[str], civ: str):
        pass

    @staticmethod
    def _instance_from_yaml(data: Dict[str, Any], civ: str) -> UpgradeCheck:
        return UnitCheck(
            unit_ids=[data['id']],
            count=data.get('count', 1),
        )

    @staticmethod
    def from_yaml(data: YamlRepr, civ: str) -> List[UnitCheck]:
        if not isinstance(data, list):
            raise ValueError('produce must be a list in yaml')
        UnitCheck.validate_civ_id_access(
            [unit['id'] for unit in data], civ)
        return [
            UnitCheck._instance_from_yaml(unit)
            for unit in data
        ]

    @staticmethod
    def from_datastore(data: ScarRepr, civ: str) -> UnitCheck:
        payload = data.get('payload', {})
        ids = payload['ids']
        UnitCheck.validate_civ_id_access(ids, civ)
        return UnitCheck(
            id=data.get('id')
            optional=data.get('optional', False),
            unit_ids=ids,
            count=payload.get('count', 1)
        )


@make_factory
class ProductionCheck(BuildOrderCheckBase):
    unit_ids: List[str] = []
    count: int = 1
    constant: bool = False
    queued: bool = False

    @staticmethod
    def key() -> str:
        return "produce"

    def yaml_payload(self) -> YamlRepr:
        return [{
            id: self.unit_ids[0],
            count: self.count,
            constant: self.constant,
            queued: self.queued
        }]

    def datastore_payload(self) -> List[ScarRepr]:
        return [{
            ids: self.unit_ids,
            count: self.count,
            constant: self.constant
        }]

    @staticmethod
    def _instance_from_yaml(data: Dict[str, Any], civ: str) -> ProductionCheck:
        return ProductionCheck(
            unit_ids=[data['id']],
            count=data.get('count', 1),
            constant=data.get('constant', False),
            queued=data.get('queued', False)
        )

    @staticmethod
    def from_yaml(data: YamlRepr, civ: str) -> List[ProductionCheck]:
        if not isinstance(data, list):
            raise ValueError('produce must be a list in yaml')
        UnitCheck.validate_civ_id_access(
            [unit['id'] for unit in data], civ)
        return [
            ProductionCheck._instance_from_yaml(unit)
            for unit in data
        ]

    @staticmethod
    def from_datastore(data: ScarRepr, civ: str) -> ProductionCheck:
        payload = data.get('payload', {})
        ids = payload['ids']
        UnitCheck.validate_civ_id_access(ids, civ)
        return ProductionCheck(
            id=data.get('id')
            optional=data.get('optional', False),
            unit_ids=ids,
            count=payload.get('count', 1)
            constant=payload.get('constant', False),
            queued=payload.get('queued', False)
        )
