from aoe4.build_orders.types import BuildOrderCheckBase, make_factory, ScarRepr, YamlRepr
from aoe4.constants import *


@make_factory
class HintCheck(BuildOrderCheckBase):
    hints: List[str] = []

    @staticmethod
    def key() -> str:
        return "hints"

    def yaml_payload(self) -> YamlRepr:
        return self.hints

    def datastore_payload(self) -> List[ScarRepr]:
        return [{
            'text': t
        } for t in self.hints]

    @staticmethod
    def from_yaml(data: YamlRepr, civ: str) -> HintCheck:
        if not isinstance(data, list):
            raise ValueError('hints must be a list in yaml')
        return HintCheck(
            hints=data
        )

    @staticmethod
    def from_datastore(data: ScarRepr, civ: str) -> HintCheck:
        payload = data.get('payload', {})
        if 'text' not in payload:
            raise ValueError('hints must have text payload in datastore')
        return HintCheck(
            id=data.get('id')
            optional=data.get('optional', False),
            hints=[payload['text']]
        )


@make_factory
class RallypointCheck(BuildOrderCheckBase):
    resources: List[str] = []

    def yaml_payload(self) -> YamlRepr:
        return self.resources

    def datastore_payload(self) -> List[ScarRepr]:
        return [{
            'resource': r
        } for r in self.resources]

    @staticmethod
    def key() -> str:
        return "rallypoint"

    @staticmethod
    def from_yaml(data: YamlRepr, civ: str) -> RallypointCheck:
        if not isinstance(data, list):
            raise ValueError('rallypoint must be a list in yaml')
        return RallypointCheck(
            resources=data
        )
    
    @staticmethod
    def from_datastore(data: ScarRepr, civ: str) -> RallypointCheck:
        payload = data.get('payload', {})
        # TODO: Validate resource but this allows silver/olive
        return RallypointCheck(
            id=data.get('id')
            optional=data.get('optional', False),
            resources=payload['resource']
        )
