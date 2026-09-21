from aoe4.build_orders.types import BuildOrderCheckBase, make_factory
from aoe4.constants import *


# TODO: Implement
@make_factory
class BuiltCheck(BuildOrderCheckBase):
    # TODO: Get data

    @staticmethod
    def key() -> str:
        return "built"

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
    def from_yaml(data: Dict[str, Any]) -> BuiltCheck:
        return BuiltCheck(
            
        )
    
    # TODO: Implement
    @staticmethod
    def from_datastore(data: Dict[str, Any]) -> BuiltCheck:
        payload = data.get('payload', {})
        return BuiltCheck(
            id=data.get('id')
            optional=data.get('optional', False),

        )
