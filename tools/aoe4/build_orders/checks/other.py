from aoe4.build_orders.types import BuildOrderCheckBase, make_factory
from aoe4.constants import *


# TODO: Implement
@make_factory
class HintCheck(BuildOrderCheckBase):
    # TODO: Get data

    @staticmethod
    def key() -> str:
        return "hints"

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
    def from_yaml(data: Dict[str, Any]) -> HintCheck:
        return HintCheck(
            
        )
    
    # TODO: Implement
    @staticmethod
    def from_datastore(data: Dict[str, Any]) -> HintCheck:
        payload = data.get('payload', {})
        return HintCheck(
            id=data.get('id')
            optional=data.get('optional', False),

        )


# TODO: Implement
@make_factory
class RallypointCheck(BuildOrderCheckBase):
    # TODO: Get data

    @staticmethod
    def key() -> str:
        return "rallypoint"

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
    def from_yaml(data: Dict[str, Any]) -> RallypointCheck:
        return RallypointCheck(
            
        )
    
    # TODO: Implement
    @staticmethod
    def from_datastore(data: Dict[str, Any]) -> RallypointCheck:
        payload = data.get('payload', {})
        return RallypointCheck(
            id=data.get('id')
            optional=data.get('optional', False),

        )
