import json
import re
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping


SCHEMA_VERSION = 1
DEFAULT_IDENTITY_CATALOG = Path(__file__).with_name("data") / "game_identities.json"
IDENTITY_ID = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
IDENTITY_CATEGORIES = frozenset({"entity", "squad", "upgrade"})


class IdentityCatalogError(ValueError):
    pass


def normalize_identity_id(value: str) -> str:
    return value.casefold().replace(" ", "_").replace("-", "_")


def _error(path: Path, message: str) -> None:
    raise IdentityCatalogError(f"{path}: {message}")


def _freeze_and_validate(value: Any, path: Path) -> Mapping[str, Mapping[str, Mapping[str, str]]]:
    if not isinstance(value, dict):
        _error(path, "civilizations must be a mapping")

    civilizations: dict[str, Mapping[str, Mapping[str, str]]] = {}
    for civilization, categories in value.items():
        if not isinstance(categories, dict):
            _error(path, f"civilizations.{civilization} must be a mapping")
        unknown_categories = set(categories) - IDENTITY_CATEGORIES
        if unknown_categories:
            _error(path, f"civilizations.{civilization}.{next(iter(unknown_categories))}: unknown category")

        frozen_categories: dict[str, Mapping[str, str]] = {}
        for category, identities in categories.items():
            if not isinstance(identities, dict):
                _error(path, f"civilizations.{civilization}.{category} must be a mapping")
            frozen_identities: dict[str, str] = {}
            for identifier, canonical_id in identities.items():
                if not isinstance(canonical_id, str) or not canonical_id:
                    _error(path, f"civilizations.{civilization}.{category}.{identifier} must be a non-empty string")
                frozen_identities[identifier] = canonical_id
            frozen_categories[category] = MappingProxyType(frozen_identities)
        civilizations[civilization] = MappingProxyType(frozen_categories)
    return MappingProxyType(civilizations)


@dataclass(frozen=True)
class IdentityCatalog:
    civilizations: Mapping[str, Mapping[str, Mapping[str, str]]]

    @classmethod
    def load(cls, path: Path) -> "IdentityCatalog":
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise IdentityCatalogError(f"{path}: unable to read identity catalog: {exc}") from exc
        if not isinstance(document, dict) or document.get("schema_version") != SCHEMA_VERSION:
            raise IdentityCatalogError(f"{path}: unsupported identity catalog schema version")
        return cls(_freeze_and_validate(document.get("civilizations"), path))

    def resolve(self, civ: str, category: str, identifier: str) -> str:
        normalized_civ = normalize_identity_id(civ)
        if not IDENTITY_ID.fullmatch(identifier):
            raise IdentityCatalogError(f"'{identifier}' is not a normalized official ID")
        if normalized_civ not in self.civilizations:
            raise IdentityCatalogError(f"unknown civilization '{normalized_civ}'")
        categories = self.civilizations[normalized_civ]
        if category not in categories:
            raise IdentityCatalogError(f"unknown category '{category}' for civilization '{normalized_civ}'")
        identities = categories[category]
        if identifier not in identities:
            raise IdentityCatalogError(f"unknown {category} ID '{identifier}' for civilization '{normalized_civ}'")
        return identities[identifier]
