from aoe4.build_orders.types import BuildOrderCheckBase, make_factory, ScarRepr, YamlRepr
from aoe4.constants import *


@check_factory
class VilCheck(BuildOrderCheckBase):
    resources: Dict[str, Any] = {}

    @staticmethod
    def key() -> str:
        return "vils"

    def yaml_payload(self) -> YamlRepr:
        return self.resources

    def datastore_payload(self) -> List[ScarRepr]:
        return [self.resource]

    @staticmethod
    def validate_resource_keys(payload: Dict[str, Any]):
        _VALID_KEYS = [FOOD_RES, GOLD_RES, WOOD_RES, STONE_RES]
        bad_keys = filter(lambda k: k not in _VALID_KEYS, payload.keys())
        if bad_keys:
            raise ValueError(f'Received unexpected key in VilCheck: {','.join(bad_keys)}')

    @staticmethod
    def from_yaml(data: YamlRepr, civ: str) -> VilCheck:
        if not isinstance(data, dict):
            raise ValueError('Vils must be a dict in yaml')
        VilCheck.validate_resource_keys(data)
        return VilCheck(resources=data)
    
    @staticmethod
    def from_datastore(data: ScarRepr, civ: str) -> VilCheck:
        payload = data.get('payload', {})
        VilCheck.validate_resource_keys(payload)
        return VilCheck(
            id=data.get('id'),
            optional=data.get('optional', False),
            resources=payload
        )
