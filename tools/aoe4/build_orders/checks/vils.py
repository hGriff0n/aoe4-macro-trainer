from aoe4.build_orders.types import BuildOrderCheckBase, make_factory
from aoe4.constants import *


@check_factory
class VilCheck(BuildOrderCheckBase):
    resources: Dict[str, Any] = {}

    @staticmethod
    def key() -> str:
        return "vils"

    def yaml_payload(self) -> Dict[str, Any]:
        return self.resources

    def datastore_payload(self) -> Dict[str, Any]:
        return self.resource

    @staticmethod
    def validate_resource_keys(payload: Dict[str, Any]):
        _VALID_KEYS = [FOOD_RES, GOLD_RES, WOOD_RES, STONE_RES]
        bad_keys = filter(lambda k: k not in _VALID_KEYS, payload.keys())
        if bad_keys:
            raise ValueError(f'Received unexpected key in VilCheck: {','.join(bad_keys)}')

    @staticmethod
    def from_yaml(data: Dict[str, Any]) -> VilCheck:
        VilCheck.validate_resource_keys(data)
        return VilCheck(resources=data)
    
    @staticmethod
    def from_datastore(data: Dict[str, Any]) -> VilCheck:
        payload = data.get('payload', {})
        VilCheck.validate_resource_keys(payload)
        return VilCheck(
            id=data.get('id'),
            optional=data.get('optional', False),
            resources=payload
        )
