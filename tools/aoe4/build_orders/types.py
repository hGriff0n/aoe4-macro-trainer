from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any, Dict, List, Optional, TypeVar
import uuid


@dataclass
class BuildOrderCheckBase(ABC):
    id: Optional[str] = str(uuid.uuid4())
    optional: bool = False

    @abstractmethod
    def yaml_payload(self) -> Dict[str, Any]:
        """Return the yaml representation"""
        pass

    @abstractmethod
    def datastore_payload(self) -> Dict[str, Any]:
        """Return the datastore 'payload'"""
        pass


@dataclass
class BuildOrderStep:
    title: Optional[str]
    checks: List[BuildOrderCheckBase]


@dataclass
class BuildOrder:
    id: str
    civ: str
    title: str
    steps: List[BuildOrderStep]
    link: Optional[str]


# Every "check" will export this factory
class _CheckFactory(ABC):

    # TODO: Technically, this isn't strict enough
    @abstractmethod
    def from_yaml(self, data: Dict[str, Any]) -> BuildOrderCheckBase:
        """Deserialize the check from the yaml representation"""
        pass

    @abstractmethod
    def from_datastore(self, data: Dict[str, Any]) -> BuildOrderCheckBase:
        """Deserialize a check from the datastore representation"""
        pass

    @abstractmethod
    def to_yaml(self, check: BuildOrderCheckBase) -> Dict[str, Any]:
        """Serialize the check to the yaml dictionary representation"""
        pass

    @abstractmethod
    def to_datastore(self, check: BuildOrderCheckBase) -> Dict[str, Any]:
        """Serialize the check to the datastore representation"""
        pass


# TODO: Would be nice to set `key` here too (ie. `@check_factory('vils')`)
def check_factory(cls: type[BuildOrderCheck]) -> BuildOrderCheckBase:
    class BoCheckFactory(_CheckFactory):
        def to_yaml(self, check: cls) -> Dict[str, Any]:
            return check.yaml_payload()

        def from_yaml(self, data: Dict[str, Any]) -> cls:
            return cls.from_yaml(data)
        
        def to_datastore(self, check: cls) -> Dict[str, Any]:
            return {
                'id': check.id,
                'kind': check.key,
                'optional': check.optional,
                'payload': check.datastore_payload()
            }
        
        def from_datastore(self, data: Dict[str, Any]) -> cls:
            if data.get('kind', '') != cls.key():
                raise ValueError(f'{cls} must have kind={cls.key()}, got {data.get('kind')}')
            return cls.from_datastore(data)
        
    cls.make_factory = lambda: return BoCheckFactory()
    return cls


BuildOrderCheck = TypeVar("BuildOrderCheck", bound=BuildOrderCheckBase)


# TODO: Not sure if this singleton works correctly
class CheckRegistry(object):
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(CheckRegistry, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        self._store: Dict[str, _CheckFactory] = {}

    def register(self, check_cls: type[BuildOrderCheck]):
        if check_cls in self._store:
            raise ValueError(f'{check_cls} is already registered.')
        self._store[check_cls.key()] = check_cls.make_factory()

    def __contains__(self, key: str | type[BuildOrderCheck]) -> bool:
        if isinstance(key, str):
            return key in self._store
        else:
            return self.__contains__(key.key())

    def __getitem__(self, key: str | type[BuildOrderCheck])
            -> CheckFactory | None:
        if isinstance(key, str):
            return self._store.get(key)
        else:
            return self.__getitem__(key.key())
