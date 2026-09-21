from aoe4.build_orders.types import BuildOrderCheckBase, make_factory
from aoe4.constants import *


# TODO: Implement
@make_factory
class AgeUpCheck(BuildOrderCheckBase):
    ids: List[str] = []
    vils: Optional[int] = None
    is_upgrade: bool = False

    @staticmethod
    def key() -> str:
        return "age_up"

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
    def from_yaml(data: Dict[str, Any]) -> AgeUpCheck:
        return AgeUpCheck(
            ids=[],
            vils=[],
            is_upgrade=False
        )
    
    # TODO: Implement
    @staticmethod
    def from_datastore(data: Dict[str, Any]) -> AgeUpCheck:
        payload = data.get('payload', {})
        return AgeUpCheck(
            id=data.get('id')
            optional=data.get('optional', False),
            ids=[],
            vils=[],
            is_upgrade=False
        )
