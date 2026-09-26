from aoe4.build_orders.types import BuildOrderCheckBase, make_factory, ScarRepr, YamlRepr
from aoe4.constants import *


@make_factory
class AgeUpCheck(BuildOrderCheckBase):
    age_ids: List[str] = []
    vils: Optional[int] = None
    is_upgrade: bool = False

    def _get_id_dict(self) -> Dict[str, Any]:
        if len(self.age_ids) == 1:
            return {'id': self.age_ids[0]}
        return {'oneof': self.age_ids}

    @staticmethod
    def key() -> str:
        return "age_up"

    def yaml_payload(self) -> YamlRepr:
        data = {}
        if self.vils is not None:
            data['vils'] = self.vils
        return data | self._get_id_dict()

    def datastore_payload(self) -> List[ScarRepr]:
        data = {
            trigger: self.is_upgrade and 'upgrade' or 'construction'
        }
        if self.vils is not None:
            data['vils'] = self.vils
        return [data | self._get_id_dict()]

    # TODO: Validate ids are valid for civ
    @staticmethod
    def validate_civ_id_access(ids: List[str], civ: str):
        pass

    @staticmethod
    def from_yaml(data: YamlRepr, civ: str) -> AgeUpCheck:
        if not isinstance(data, dict):
            raise ValueError('age_up must be dict in yaml')
        ids = data.get('id', data.get('oneof', []))
        AgeUpCheck.validate_civ_id_access(ids, civ)
        return AgeUpCheck(
            age_ids=ids,
            vils=data.get('vils')
            is_upgrade=civ in UPGRADE_CIVS
        )

    @staticmethod
    def from_datastore(data: ScarRepr, civ: str) -> AgeUpCheck:
        payload = data.get('payload', {})
        ids = payload.get('id', payload.get('oneof', []))
        AgeUpCheck.validate_civ_id_access(ids, civ)
        return AgeUpCheck(
            id=data.get('id')
            optional=data.get('optional', False),
            age_ids=ids,
            vils=payload.get('vils'),
            is_upgrade=civ in UPGRADE_CIVS
        )
