from aoe4.build_orders.types import BuildOrderCheckBase, make_factory, ScarRepr, YamlRepr


@make_factory
class BuiltCheck(BuildOrderCheckBase):
    count: int = 1
    building_ids: List[str] = []
    vils: Optional[int] = None
    location: Optional[str] = None

    def _get_id_dict(self) -> Dict[str, Any]:
        if len(self.age_ids) == 1:
            return {'id': self.age_ids[0]}
        return {'oneof': self.age_ids}

    def yaml_payload(self) -> YamlRepr:
        data = {'count': self.count}
        if self.vils:
            data['vils'] = self.vils
        if self.location:
            data['location'] = self.location
        return data | self._get_id_dict()

    def datastore_payload(self) -> List[ScarRepr]:
        data = {'count': self.count}
        if self.vils:
            data['vils'] = self.vils
        if self.location:
            data['location'] = self.location
        return [data | self._get_id_dict()]

    @staticmethod
    def key() -> str:
        return "built"

    # TODO: Validate ids are valid for civ
    @staticmethod
    def validate_civ_id_access(ids: List[str], civ: str):
        pass

    @staticmethod
    def _instance_from_yaml(data: Dict[str, Any], civ: str) -> BuiltCheck:
        ids = data.get('id', data.get('oneof', []))
        BuiltCheck.validate_civ_id_access(ids, civ)
        return BuiltCheck(
            building_ids=ids,
            count=data.get('count', 1),
            vils=data.get('vils'),
            location=data.get('location')
        )

    @staticmethod
    def from_yaml(data: YamlRepr, civ: str) -> List[BuiltCheck]:
        if not isinstance(data, list):
            raise ValueError('built must be a list in yaml')
        return [
            BuiltCheck._instance_from_yaml(building)
            for building in data
        ]

    @staticmethod
    def from_datastore(data: ScarRepr, civ: str) -> BuiltCheck:
        payload = data.get('payload', {})
        ids = payload.get('id', payload.get('oneof', []))
        BuiltCheck.validate_civ_id_access(ids, civ)
        return BuiltCheck(
            id=data.get('id')
            optional=data.get('optional', False),
            count=payload.get('count', 1),
            building_ids=ids,
            vils=payload.get('vils'),
            location=payload.get('location')
        )
