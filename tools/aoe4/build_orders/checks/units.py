from aoe4.build_orders.types import BuildOrderCheckBase, make_factory
from aoe4.constants import *


# TODO: Implement
@make_factory
class UnitCheck(BuildOrderCheckBase):
    # TODO: Get data

    @staticmethod
    def key() -> str:
        return "units"

    def yaml_payload(self) -> Dict[str, Any]:
        return {
            # TODO: Implement
        }

    def datastore_payload(self) -> Dict[str, Any]:
        return {
            # TODO: Implement
        }

    # TODO: Implement
    @staticmethod
    def from_yaml(data: Dict[str, Any]) -> UnitCheck:
        return UnitCheck(
            
        )
    
    # TODO: Implement
    @staticmethod
    def from_datastore(data: Dict[str, Any]) -> UnitCheck:
        payload = data.get('payload', {})
        return UnitCheck(
            id=data.get('id')
            optional=data.get('optional', False),

        )


# TODO: Implement
@make_factory
class ProductionCheck(BuildOrderCheckBase):
    # TODO: Get data

    @staticmethod
    def key() -> str:
        return "produce"

    def yaml_payload(self) -> Dict[str, Any]:
        return {
            # TODO: Implement
        }

    def datastore_payload(self) -> Dict[str, Any]:
        return {
            # TODO: Implement
        }

    # TODO: Implement
    @staticmethod
    def from_yaml(data: Dict[str, Any]) -> ProductionCheck:
        return ProductionCheck(
            
        )
    
    # TODO: Implement
    @staticmethod
    def from_datastore(data: Dict[str, Any]) -> ProductionCheck:
        payload = data.get('payload', {})
        return ProductionCheck(
            id=data.get('id')
            optional=data.get('optional', False),

        )
