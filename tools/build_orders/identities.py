import json
import re
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping


SCHEMA_VERSION = 2
DEFAULT_IDENTITY_CATALOG = Path(__file__).with_name("data") / "game_identities.json"
IDENTITY_ID = re.compile(r"^(?=.*[a-z])[a-z0-9]+(?:_[a-z0-9]+)*$")
IDENTITY_CATEGORIES = frozenset({"entity", "squad", "upgrade"})
SCALAR_IDENTITY_CATEGORIES = IDENTITY_CATEGORIES - {"squad"}


class IdentityCatalogError(ValueError):
    pass


@dataclass(frozen=True)
class SquadFamilyIdentity:
    family_id: str
    canonical_ids: tuple[str, ...]


def normalize_identity_id(value: str) -> str:
    return value.casefold().replace(" ", "_").replace("-", "_")


def _error(path: Path, message: str) -> None:
    raise IdentityCatalogError(f"{path}: {message}")


def _validate_squad_list(value: Any, path: Path, field: str, *, normalized_ids: bool) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        _error(path, f"{field} must be a non-empty list")
    if not all(isinstance(item, str) for item in value):
        _error(path, f"{field} must contain strings")
    if normalized_ids and not all(IDENTITY_ID.fullmatch(item) for item in value):
        _error(path, f"{field} must contain normalized official IDs")
    if value != sorted(value):
        _error(path, f"{field} must be sorted")
    if len(value) != len(set(value)):
        _error(path, f"{field} must be unique")
    return tuple(value)


def _freeze_and_validate(
    value: Any, path: Path
) -> tuple[
    Mapping[str, Mapping[str, Mapping[str, str]]],
    Mapping[str, Mapping[str, SquadFamilyIdentity]],
]:
    if not isinstance(value, dict):
        _error(path, "civilizations must be a mapping")

    civilizations: dict[str, Mapping[str, Mapping[str, str]]] = {}
    squad_aliases: dict[str, Mapping[str, SquadFamilyIdentity]] = {}
    for civilization, categories in value.items():
        if not isinstance(categories, dict):
            _error(path, f"civilizations.{civilization} must be a mapping")
        unknown_categories = set(categories) - IDENTITY_CATEGORIES
        if unknown_categories:
            _error(path, f"civilizations.{civilization}.{next(iter(unknown_categories))}: unknown category")

        frozen_categories: dict[str, Mapping[str, str]] = {}
        for category in SCALAR_IDENTITY_CATEGORIES:
            identities = categories.get(category, {})
            if not isinstance(identities, dict):
                _error(path, f"civilizations.{civilization}.{category} must be a mapping")
            frozen_identities: dict[str, str] = {}
            for identifier, canonical_id in identities.items():
                if not isinstance(identifier, str) or not IDENTITY_ID.fullmatch(identifier):
                    _error(path, f"civilizations.{civilization}.{category}.{identifier}: not a normalized official ID")
                if not isinstance(canonical_id, str) or not canonical_id:
                    _error(path, f"civilizations.{civilization}.{category}.{identifier} must be a non-empty string")
                frozen_identities[identifier] = canonical_id
            frozen_categories[category] = MappingProxyType(frozen_identities)

        aliases: dict[str, SquadFamilyIdentity] = {}
        squads = categories.get("squad", {})
        if not isinstance(squads, dict):
            _error(path, f"civilizations.{civilization}.squad must be a mapping")
        for family_id, family in squads.items():
            family_path = f"civilizations.{civilization}.squad.{family_id}"
            if not isinstance(family_id, str) or not IDENTITY_ID.fullmatch(family_id):
                _error(path, f"{family_path}: not a normalized official ID")
            if not isinstance(family, dict):
                _error(path, f"{family_path} must be a mapping")
            family_aliases = _validate_squad_list(
                family.get("aliases"), path, f"{family_path}.aliases", normalized_ids=True
            )
            canonical_ids = _validate_squad_list(
                family.get("canonical_ids"), path, f"{family_path}.canonical_ids", normalized_ids=False
            )
            if family_id not in family_aliases:
                _error(path, f"{family_path}.aliases must include family ID '{family_id}'")
            identity = SquadFamilyIdentity(family_id=family_id, canonical_ids=canonical_ids)
            for alias in family_aliases:
                if alias in aliases:
                    _error(path, f"{family_path}.aliases.{alias}: alias belongs to multiple squad families")
                aliases[alias] = identity
        civilizations[civilization] = MappingProxyType(frozen_categories)
        squad_aliases[civilization] = MappingProxyType(aliases)
    return MappingProxyType(civilizations), MappingProxyType(squad_aliases)


@dataclass(frozen=True)
class IdentityCatalog:
    civilizations: Mapping[str, Mapping[str, Mapping[str, str]]]
    squad_aliases: Mapping[str, Mapping[str, SquadFamilyIdentity]]

    @classmethod
    def load(cls, path: Path) -> "IdentityCatalog":
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise IdentityCatalogError(f"{path}: unable to read identity catalog: {exc}") from exc
        if not isinstance(document, dict) or document.get("schema_version") != SCHEMA_VERSION:
            raise IdentityCatalogError(f"{path}: unsupported identity catalog schema version")
        if document.get("source") != "official_base_data":
            raise IdentityCatalogError(f"{path}: identity catalog source must be official_base_data")
        civilizations, squad_aliases = _freeze_and_validate(document.get("civilizations"), path)
        return cls(civilizations, squad_aliases)

    def resolve(self, civ: str, category: str, identifier: str) -> str:
        normalized_civ = normalize_identity_id(civ)
        if not IDENTITY_ID.fullmatch(identifier):
            raise IdentityCatalogError(f"'{identifier}' is not a normalized official ID")
        if normalized_civ not in self.civilizations:
            raise IdentityCatalogError(f"unknown civilization '{normalized_civ}'")
        if category == "squad":
            raise IdentityCatalogError("squad identities must be resolved with resolve_squad_family")
        categories = self.civilizations[normalized_civ]
        if category not in categories:
            raise IdentityCatalogError(f"unknown category '{category}' for civilization '{normalized_civ}'")
        identities = categories[category]
        if identifier not in identities:
            raise IdentityCatalogError(f"unknown {category} ID '{identifier}' for civilization '{normalized_civ}'")
        return identities[identifier]

    def resolve_squad_family(self, civ: str, identifier: str) -> SquadFamilyIdentity:
        normalized_civ = normalize_identity_id(civ)
        if not IDENTITY_ID.fullmatch(identifier):
            raise IdentityCatalogError(f"'{identifier}' is not a normalized official ID")
        if normalized_civ not in self.civilizations:
            raise IdentityCatalogError(f"unknown civilization '{normalized_civ}'")
        aliases = self.squad_aliases[normalized_civ]
        if identifier not in aliases:
            raise IdentityCatalogError(f"unknown squad ID '{identifier}' for civilization '{normalized_civ}'")
        return aliases[identifier]
