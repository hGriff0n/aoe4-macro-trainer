from pathlib import Path
from typing import Any

import yaml

from .identities import (
    DEFAULT_IDENTITY_CATALOG,
    IdentityCatalog,
    IdentityCatalogError,
    normalize_identity_id,
)
from .model import BuildOrder, Catalog, CheckDescriptor, Step, normalize_id

RESOURCE_ORDER = ("food", "gold", "wood", "stone")
RESOURCES = set(RESOURCE_ORDER)
CHECK_FIELDS = {"vils", "rallypoint", "built", "age_up", "upgrades", "produce", "resources", "buildings", "units", "hints"}
CHECK_ID_CATEGORIES = {
    "built": "entity",
    "buildings": "entity",
    "produce": "squad",
    "units": "squad",
    "upgrades": "upgrade",
}
UPGRADE_AGE_UP_CIVS = frozenset({"abbasid", "ayyubids", "templar", "golden_horde"})


class BuildOrderValidationError(ValueError):
    pass


def _error(file: Path | str, path: str, message: str) -> None:
    raise BuildOrderValidationError(f"{file}: {path}: {message}")


def _mapping(value: Any, file: Path, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _error(file, path, "must be a mapping")
    return value


def _list(value: Any, file: Path, path: str) -> list[Any]:
    if not isinstance(value, list):
        _error(file, path, "must be a list")
    return value


def _string(value: Any, file: Path, path: str) -> str:
    if not isinstance(value, str) or not value:
        _error(file, path, "must be a non-empty string")
    return value


def _positive(value: Any, file: Path, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        _error(file, path, "must be a positive integer")
    return value


def _id_or_oneof(value: Any, file: Path, path: str, allowed: set[str]) -> dict[str, object]:
    mapping = _mapping(value, file, path)
    unknown = set(mapping) - allowed
    if unknown:
        _error(file, f"{path}.{next(iter(unknown))}", "unknown field")
    has_id, has_oneof = "id" in mapping, "oneof" in mapping
    if has_id == has_oneof:
        _error(file, path, "requires exactly one of id or oneof")
    if has_id:
        return {"id": _string(mapping["id"], file, f"{path}.id")}
    choices = _list(mapping["oneof"], file, f"{path}.oneof")
    if not choices:
        _error(file, f"{path}.oneof", "must not be empty")
    return {"oneof": [_string(item, file, f"{path}.oneof[{index}]") for index, item in enumerate(choices)]}


def _identity_category(kind: str, civ: str) -> str:
    if kind == "age_up":
        return "upgrade" if normalize_identity_id(civ) in UPGRADE_AGE_UP_CIVS else "entity"
    return CHECK_ID_CATEGORIES[kind]


def _humanize_identity_id(identifier: str) -> str:
    return identifier.replace("_", " ")


_PRODUCED_UNIT_SINGULAR_SUFFIX_PLURALS = {
    "archer": "archers",
    "spearman": "spearmen",
    "man at arms": "men at arms",
}
_PRODUCED_UNIT_EXACT_PLURALS = {
    "janissary": "janissaries",
    "shaman": "shamans",
}
_PRODUCED_UNIT_ALREADY_PLURAL_SUFFIXES = (
    "footmen",
    "raiders",
    "mercenaries",
    "nest of bees",
    "samurai",
    "streltsy",
)


def _pluralize_unit(unit: str) -> str:
    """Use only vetted official-catalog display inflections; unknown labels stay unchanged."""
    exact = _PRODUCED_UNIT_EXACT_PLURALS.get(unit)
    if exact is not None:
        return exact
    if any(unit == suffix or unit.endswith(f" {suffix}") for suffix in _PRODUCED_UNIT_ALREADY_PLURAL_SUFFIXES):
        return unit
    for singular, plural in _PRODUCED_UNIT_SINGULAR_SUFFIX_PLURALS.items():
        if unit == singular:
            return plural
        if unit.endswith(f" {singular}"):
            return f"{unit[: -len(singular)]}{plural}"
    return unit


def _resolve_identity_payload(
    payload: dict[str, object],
    *,
    kind: str,
    civ: str,
    identities: IdentityCatalog,
    file: Path,
    path: str,
) -> None:
    category = _identity_category(kind, civ)
    key = "id" if "id" in payload else "oneof"
    human_ids = [payload[key]] if key == "id" else payload[key]
    canonical = []
    for index, item in enumerate(human_ids):
        try:
            canonical.append(identities.resolve(civ, category, item))
        except IdentityCatalogError as exc:
            identity_path = f"{path}.id" if key == "id" else f"{path}.oneof[{index}]"
            _error(
                file,
                identity_path,
                f"civilization '{normalize_identity_id(civ)}', {kind} check, "
                f"expected {category} ID '{item}': {exc}",
            )
    payload[key] = canonical[0] if key == "id" else canonical


def _resolve_squad_family_payload(
    payload: dict[str, object],
    *,
    civ: str,
    identities: IdentityCatalog,
    file: Path,
    path: str,
) -> str:
    author_id = payload.pop("id")
    family = identities.resolve_squad_family(civ, author_id)
    payload["ids"] = list(family.canonical_ids)
    return family.family_id


def _resource_checks(kind: str, value: Any, file: Path, path: str, no_collect: bool = False) -> list[CheckDescriptor]:
    mapping = _mapping(value, file, path)
    checks: list[CheckDescriptor] = []
    for resource, count in mapping.items():
        item_path = f"{path}.{resource}"
        if resource == "no_collect" and kind == "vils":
            for index, item in enumerate(_list(count, file, item_path)):
                resource_name = _string(item, file, f"{item_path}[{index}]")
                if resource_name not in RESOURCES:
                    _error(file, f"{item_path}[{index}]", "unsupported resource")
                checks.append(CheckDescriptor(kind, f"No {resource_name} villagers", False, {"resource": resource_name, "no_collect": True}))
            continue
        if resource not in RESOURCES:
            _error(file, item_path, "unsupported resource")
        number = _positive(count, file, item_path)
        if kind == "vils":
            title = f"{number} {resource} villagers"
        elif kind == "resources":
            title = f"Collect at least {number} {resource}"
        else:
            title = f"{number} {resource}"
        checks.append(CheckDescriptor(kind, title, False, {"resource": resource, "count": number}))
    if not checks:
        _error(file, path, "must not be empty")
    return checks


def _vils_check(value: Any, file: Path, path: str) -> list[CheckDescriptor]:
    mapping = _mapping(value, file, path)
    thresholds: dict[str, int] = {}
    no_collect_checks: list[CheckDescriptor] = []
    for resource in RESOURCE_ORDER:
        if resource in mapping:
            thresholds[resource] = _positive(mapping[resource], file, f"{path}.{resource}")
    if "no_collect" in mapping:
        for index, item in enumerate(_list(mapping["no_collect"], file, f"{path}.no_collect")):
            resource = _string(item, file, f"{path}.no_collect[{index}]")
            if resource not in RESOURCES:
                _error(file, f"{path}.no_collect[{index}]", "unsupported resource")
            no_collect_checks.append(
                CheckDescriptor("vils", f"No {resource} villagers", False, {"resource": resource, "no_collect": True})
            )
    for resource in mapping:
        if resource not in RESOURCES and resource != "no_collect":
            _error(file, f"{path}.{resource}", "unsupported resource")
    checks: list[CheckDescriptor] = []
    if thresholds:
        title = "Assign " + " | ".join(f"{count} {resource}" for resource, count in thresholds.items())
        checks.append(CheckDescriptor("vils", title, False, thresholds))
    checks.extend(no_collect_checks)
    if not checks:
        _error(file, path, "must not be empty")
    return checks


def _check_descriptors(
    kind: str,
    value: Any,
    file: Path,
    path: str,
    civ: str,
    identities: IdentityCatalog,
) -> list[CheckDescriptor]:
    if kind == "vils":
        return _vils_check(value, file, path)
    if kind == "resources":
        return _resource_checks(kind, value, file, path)
    if kind == "rallypoint":
        checks = []
        for index, item in enumerate(_list(value, file, path)):
            item_path = f"{path}[{index}]"
            resource = _string(item, file, item_path)
            if resource not in RESOURCES:
                _error(file, item_path, "unsupported resource")
            checks.append(CheckDescriptor(kind, f"Rally to {resource}", False, {"resource": resource}))
        return checks
    if kind in {"built", "age_up"}:
        entries = [value] if kind == "age_up" else _list(value, file, path)
        result = []
        for index, entry in enumerate(entries):
            item_path = path if kind == "age_up" else f"{path}[{index}]"
            permitted = {"id", "oneof", "vils", "location"}
            if kind == "built":
                permitted.add("count")
            payload = _id_or_oneof(entry, file, item_path, permitted)
            mapping = _mapping(entry, file, item_path)
            if kind == "built":
                payload["count"] = _positive(mapping.get("count", 1), file, f"{item_path}.count")
            if "vils" in mapping:
                payload["vils"] = _positive(mapping["vils"], file, f"{item_path}.vils")
            if "location" in mapping:
                payload["location"] = _string(mapping["location"], file, f"{item_path}.location")
            label = (
                _humanize_identity_id(payload["id"])
                if "id" in payload
                else " or ".join(_humanize_identity_id(item) for item in payload["oneof"])
            )
            _resolve_identity_payload(
                payload,
                kind=kind,
                civ=civ,
                identities=identities,
                file=file,
                path=item_path,
            )
            if kind == "built":
                count_label = "" if payload["count"] == 1 else f'{payload["count"]} '
                title = f"Build {count_label}{label}"
            else:
                title = f"{kind.replace('_', ' ').title()}: {label}"
            result.append(CheckDescriptor(kind, title, False, dict(payload)))
        return result
    if kind in {"upgrades", "produce", "buildings", "units"}:
        result = []
        for index, entry in enumerate(_list(value, file, path)):
            item_path = f"{path}[{index}]"
            mapping = _mapping(entry, file, item_path)
            permitted = {"id", "optional", "queued"} if kind == "upgrades" else ({"id", "count", "constant", "queued"} if kind == "produce" else {"id", "count"})
            unknown = set(mapping) - permitted
            if unknown:
                _error(file, f"{item_path}.{next(iter(unknown))}", "unknown field")
            identifier = _string(mapping.get("id"), file, f"{item_path}.id")
            payload: dict[str, object] = {"id": identifier}
            optional = False
            if kind == "upgrades":
                optional = mapping.get("optional", False)
                if not isinstance(optional, bool): _error(file, f"{item_path}.optional", "must be boolean")
                queued = mapping.get("queued", False)
                if not isinstance(queued, bool): _error(file, f"{item_path}.queued", "must be boolean")
                payload["queued"] = queued
                _resolve_identity_payload(
                    payload,
                    kind=kind,
                    civ=civ,
                    identities=identities,
                    file=file,
                    path=item_path,
                )
                label = _humanize_identity_id(identifier)
                title = f"Queue {label} for research" if queued else f"Research {label}"
                if optional:
                    title = f"[Optional] {title}"
            else:
                payload["count"] = _positive(mapping.get("count", 1), file, f"{item_path}.count")
                for flag in ("constant", "queued"):
                    if flag in mapping:
                        if not isinstance(mapping[flag], bool): _error(file, f"{item_path}.{flag}", "must be boolean")
                        payload[flag] = mapping[flag]
            if kind in {"produce", "units"}:
                try:
                    family_id = _resolve_squad_family_payload(
                        payload,
                        civ=civ,
                        identities=identities,
                        file=file,
                        path=item_path,
                    )
                except IdentityCatalogError as exc:
                    _error(
                        file,
                        f"{item_path}.id",
                        f"civilization '{normalize_identity_id(civ)}', {kind} check, "
                        f"expected squad ID '{identifier}': {exc}",
                    )
                if kind == "produce":
                    unit = _humanize_identity_id(family_id)
                    counted_unit = unit if payload["count"] == 1 else _pluralize_unit(unit)
                    if payload.get("constant", False):
                        title = f"Constantly produce {unit}"
                        optional = True
                    elif payload.get("queued", False):
                        title = f"Queue {payload['count']} {counted_unit}"
                    else:
                        title = f"Produce {payload['count']} {counted_unit}"
                else:
                    title = f"Have {payload['count']} active {_humanize_identity_id(family_id)}"
            elif kind != "upgrades":
                _resolve_identity_payload(
                    payload,
                    kind=kind,
                    civ=civ,
                    identities=identities,
                    file=file,
                    path=item_path,
                )
                title = _humanize_identity_id(identifier)
            result.append(CheckDescriptor(kind, title, optional, payload))
        return result
    if kind == "hints":
        checks = []
        for index, item in enumerate(_list(value, file, path)):
            text = _string(item, file, f"{path}[{index}]")
            checks.append(CheckDescriptor(kind, f"[HINT] {text}", True, {"text": text}))
        return checks
    _error(file, path, "unknown check")


def _compile_order(document: Any, file: Path, index: int | None, identities: IdentityCatalog) -> BuildOrder:
    base = "" if index is None else f"[{index}]."
    order = _mapping(document, file, base.rstrip("."))
    unknown = set(order) - {"civ", "title", "steps"}
    if unknown:
        _error(file, f"{base}{next(iter(unknown))}", "unknown field")
    civ = _string(order.get("civ"), file, f"{base}civ")
    title = _string(order.get("title"), file, f"{base}title")
    steps = _list(order.get("steps"), file, f"{base}steps")
    compiled_steps = []
    for step_index, raw_step in enumerate(steps):
        step_path = f"{base}steps[{step_index}]"
        step = _mapping(raw_step, file, step_path)
        unknown = set(step) - CHECK_FIELDS - {"title"}
        if unknown:
            _error(file, f"{step_path}.{next(iter(unknown))}", "unknown field")
        step_title = step.get("title")
        if step_title is not None:
            step_title = _string(step_title, file, f"{step_path}.title")
        checks: list[CheckDescriptor] = []
        for key, entry in step.items():
            if key != "title":
                checks.extend(
                    _check_descriptors(
                        key,
                        entry,
                        file,
                        f"{step_path}.{key}",
                        civ,
                        identities,
                    )
                )
        if not checks:
            _error(file, step_path, "must contain at least one check")
        compiled_steps.append(Step(step_title, tuple(checks)))
    if not compiled_steps:
        _error(file, f"{base}steps", "must not be empty")
    return BuildOrder(normalize_id(civ, title), civ, title, tuple(compiled_steps))


def compile_directory(input_dir: Path, identities: IdentityCatalog | None = None) -> Catalog:
    if identities is None:
        identities = IdentityCatalog.load(DEFAULT_IDENTITY_CATALOG)
    orders: list[BuildOrder] = []
    for file in sorted((path for path in input_dir.rglob("*") if path.suffix.lower() in {".yaml", ".yml"}), key=lambda path: path.relative_to(input_dir).as_posix()):
        source = file.relative_to(input_dir).as_posix()
        try:
            document = yaml.safe_load(file.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise BuildOrderValidationError(f"{source}: invalid YAML: {exc}") from exc
        documents = document if isinstance(document, list) else [document]
        if not isinstance(document, (dict, list)):
            _error(source, "", "root must be a mapping or list of mappings")
        for index, item in enumerate(documents):
            orders.append(
                _compile_order(
                    item,
                    source,
                    index if isinstance(document, list) else None,
                    identities,
                )
            )
    seen: set[str] = set()
    for order in orders:
        if order.id in seen:
            raise BuildOrderValidationError(f"duplicate generated id '{order.id}'")
        seen.add(order.id)
    return Catalog(tuple(orders))
