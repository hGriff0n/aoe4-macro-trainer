from aoe4.build_orders.types import BuildOrderCheckBase, make_factory, ScarRepr, YamlRepr
from aoe4.constants import *


@make_factory
class ResourceCheck(BuildOrderCheckBase):
    resources: Dict[str, int] = {}

    def yaml_payload(self) -> YamlRepr:
        return self.resources

    def datastore_payload(self) -> List[ScarRepr]:
        return [{
            count: c,
            resource: r
        } for r, c in self.resources]

    @staticmethod
    def key() -> str:
        return "resources"

    @staticmethod
    def from_yaml(data: YamlRepr, civ: str) -> ResourceCheck:
        if not isinstance(data, dict):
            raise ValueError('resources must be a dict in yaml')
        return ResourceCheck(
            resources={
                data.get(res) for res in [
                    'food', 'gold', 'stone', 'wood']
            }
        )

    @staticmethod
    def from_datastore(data: ScarRepr, civ: str) -> ResourceCheck:
        payload = data.get('payload', {})
        return ResourceCheck(
            id=data.get('id')
            optional=data.get('optional', False),
            resources={
                payload['resource']: payload['count']
            }
        )
