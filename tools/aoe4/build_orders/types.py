from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TypeVar, Union
import uuid


ScarRepr = Dict[str, Any]
YamlRepr = Union[Dict[str, Any], List[Any]]


def parse_ids(data: Dict[str, Any]) -> List[str]:
    """Read the `id`/`oneof` pair used by yaml and datastore payloads"""
    if 'id' in data:
        return [data['id']]
    return list(data.get('oneof', []))


def ids_dict(ids: List[str]) -> Dict[str, Any]:
    """Inverse of `parse_ids`"""
    if len(ids) == 1:
        return {'id': ids[0]}
    return {'oneof': ids}


@dataclass
class BuildOrderCheckBase(ABC):
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    optional: bool = False

    @staticmethod
    @abstractmethod
    def key() -> str:
        """Return the yaml/datastore `kind` of this check"""
        pass

    @abstractmethod
    def yaml_payload(self) -> YamlRepr:
        """Return the yaml representation"""
        pass

    @abstractmethod
    def datastore_payload(self) -> List[ScarRepr]:
        """Return the datastore 'payload'"""
        pass


BuildOrderCheck = TypeVar("BuildOrderCheck", bound=BuildOrderCheckBase)


@dataclass
class BuildOrderStep:
    title: Optional[str] = None
    checks: List[BuildOrderCheckBase] = field(default_factory=list)


@dataclass
class BuildOrder:
    id: str
    civ: str
    title: str
    steps: List[BuildOrderStep] = field(default_factory=list)
    link: Optional[str] = None


# Every "check" will export this factory
class _CheckFactory(ABC):

    # TODO: Technically, this isn't strict enough
    @abstractmethod
    def from_yaml(self, data: YamlRepr, civ: str) -> List[BuildOrderCheckBase]:
        """Deserialize the check from the yaml representation"""
        pass

    @abstractmethod
    def from_datastore(self, data: ScarRepr, civ: str) -> BuildOrderCheckBase:
        """Deserialize a check from the datastore representation"""
        pass

    @abstractmethod
    def to_yaml(self, check: BuildOrderCheckBase) -> YamlRepr:
        """Serialize the check to the yaml dictionary representation"""
        pass

    @abstractmethod
    def to_datastore(self, check: BuildOrderCheckBase) -> List[ScarRepr]:
        """Serialize the check to the datastore representation"""
        pass


# TODO: Would be nice to set `key` here too (ie. `@check_factory('vils')`)
def check_factory(cls: type[BuildOrderCheck]) -> type[BuildOrderCheck]:
    class BoCheckFactory(_CheckFactory):
        def to_yaml(self, check: BuildOrderCheck) -> YamlRepr:
            return check.yaml_payload()

        def from_yaml(self, data: YamlRepr, civ: str) -> List[BuildOrderCheck]:
            checks = cls.from_yaml(data, civ)
            return checks if isinstance(checks, list) else [checks]

        def to_datastore(self, check: BuildOrderCheck) -> List[ScarRepr]:
            payloads = check.datastore_payload()
            # Every datastore check needs a unique id
            return [{
                'id': check.id if len(payloads) == 1 else f'{check.id}:{i}',
                'kind': check.key(),
                'optional': check.optional,
                'payload': payload
            } for i, payload in enumerate(payloads, 1)]

        def from_datastore(self, data: ScarRepr, civ: str) -> BuildOrderCheck:
            if data.get('kind', '') != cls.key():
                raise ValueError(f'{cls} must have kind={cls.key()}, got {data.get("kind")}')
            return cls.from_datastore(data, civ)

    cls.make_factory = staticmethod(lambda: BoCheckFactory())
    return cls


# TODO: Not sure if this singleton works correctly
class CheckRegistry(object):
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(CheckRegistry, cls).__new__(cls)
            # Initialized here as `__init__` runs on every `CheckRegistry()`
            cls._instance._store: Dict[str, _CheckFactory] = {}
        return cls._instance

    def register(self, check_cls: type[BuildOrderCheck]):
        if check_cls in self:
            raise ValueError(f'{check_cls} is already registered.')
        self._store[check_cls.key()] = check_cls.make_factory()

    def __contains__(self, key: str | type[BuildOrderCheck]) -> bool:
        if isinstance(key, str):
            return key in self._store
        else:
            return self.__contains__(key.key())

    def __getitem__(self, key: str | type[BuildOrderCheck]) -> _CheckFactory | None:
        if isinstance(key, str):
            return self._store.get(key)
        else:
            return self.__getitem__(key.key())
