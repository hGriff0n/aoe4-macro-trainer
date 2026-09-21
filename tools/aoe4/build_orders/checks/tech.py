from aoe4.build_orders.types import BuildOrderCheckBase, make_factory
from aoe4.constants import *


# TODO: Implement
@make_factory
class UpgradeCheck(BuildOrderCheckBase):
    # TODO: Get data

    @staticmethod
    def key() -> str:
        return "upgrades"

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
    def from_yaml(data: Dict[str, Any]) -> UpgradeCheck:
        return UpgradeCheck(
            
        )
    
    # TODO: Implement
    @staticmethod
    def from_datastore(data: Dict[str, Any]) -> UpgradeCheck:
        payload = data.get('payload', {})
        return UpgradeCheck(
            id=data.get('id')
            optional=data.get('optional', False),

        )
