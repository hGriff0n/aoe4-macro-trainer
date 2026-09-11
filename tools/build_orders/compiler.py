from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Callable
import sys
from urllib.parse import urlsplit

import yaml

from .datastore import DatastoreError, load_datastore, write_datastore
from .identities import (
    DEFAULT_IDENTITY_CATALOG,
    IdentityCatalog,
    IdentityCatalogError,
    normalize_identity_id,
)
from .importer import (
    ImportValidationError,
    fetch_overlay_document,
    read_overlay_file,
    translate_overlay_document,
)
from .model import BuildOrder, Catalog, CheckDescriptor, Step, normalize_id
from .profiles import ProfileResolutionError, resolve_datastore_path

RESOURCE_ORDER = ("food", "gold", "wood", "stone")
RESOURCES = set(RESOURCE_ORDER)
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


def _mapping(value: Any, file: Path | str, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _error(file, path, "must be a mapping")
    return value


def _list(value: Any, file: Path | str, path: str) -> list[Any]:
    if not isinstance(value, list):
        _error(file, path, "must be a list")
    return value


def _string(value: Any, file: Path | str, path: str) -> str:
    if not isinstance(value, str) or not value:
        _error(file, path, "must be a non-empty string")
    return value


def _source_link(value: Any, file: Path | str, path: str) -> str:
    if not isinstance(value, str) or not value or any(character.isspace() for character in value):
        _error(file, path, "must be an absolute HTTP(S) URL")
    try:
        parsed = urlsplit(value)
    except ValueError:
        _error(file, path, "must be an absolute HTTP(S) URL")
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        _error(file, path, "must be an absolute HTTP(S) URL")
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


def _age_up_trigger(civ: str) -> str:
    return "upgrade" if normalize_identity_id(civ) in UPGRADE_AGE_UP_CIVS else "construction"


def _identity_category(kind: str, civ: str) -> str:
    if kind == "age_up":
        return "upgrade" if _age_up_trigger(civ) == "upgrade" else "entity"
    return CHECK_ID_CATEGORIES[kind]


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
) -> None:
    author_id = payload.pop("id")
    family = identities.resolve_squad_family(civ, author_id)
    payload["ids"] = list(family.canonical_ids)


def _resource_checks(value: Any, file: Path, path: str) -> list[CheckDescriptor]:
    mapping = _mapping(value, file, path)
    checks: list[CheckDescriptor] = []
    for resource, count in mapping.items():
        item_path = f"{path}.{resource}"
        if resource not in RESOURCES:
            _error(file, item_path, "unsupported resource")
        number = _positive(count, file, item_path)
        checks.append(CheckDescriptor("resources", False, {"resource": resource, "count": number}))
    if not checks:
        _error(file, path, "must not be empty")
    return checks


def _compile_vils(
    value: Any,
    file: Path,
    path: str,
    civ: str,
    identities: IdentityCatalog,
) -> list[CheckDescriptor]:
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
                CheckDescriptor("vils", False, {"resource": resource, "no_collect": True})
            )
    for resource in mapping:
        if resource not in RESOURCES and resource != "no_collect":
            _error(file, f"{path}.{resource}", "unsupported resource")
    checks: list[CheckDescriptor] = []
    if thresholds:
        checks.append(CheckDescriptor("vils", False, thresholds))
    checks.extend(no_collect_checks)
    if not checks:
        _error(file, path, "must not be empty")
    return checks


def _compile_resources(
    value: Any,
    file: Path,
    path: str,
    civ: str,
    identities: IdentityCatalog,
) -> list[CheckDescriptor]:
    return _resource_checks(value, file, path)


def _compile_rallypoint(
    value: Any,
    file: Path,
    path: str,
    civ: str,
    identities: IdentityCatalog,
) -> list[CheckDescriptor]:
    checks = []
    for index, item in enumerate(_list(value, file, path)):
        item_path = f"{path}[{index}]"
        resource = _string(item, file, item_path)
        if resource not in RESOURCES:
            _error(file, item_path, "unsupported resource")
        checks.append(CheckDescriptor("rallypoint", False, {"resource": resource}))
    return checks


def _structure_checks(
    kind: str,
    entries: list[Any],
    file: Path,
    path: str,
    civ: str,
    identities: IdentityCatalog,
) -> list[CheckDescriptor]:
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
        _resolve_identity_payload(
            payload,
            kind=kind,
            civ=civ,
            identities=identities,
            file=file,
            path=item_path,
        )
        if kind == "age_up":
            payload["trigger"] = _age_up_trigger(civ)
        result.append(CheckDescriptor(kind, False, dict(payload)))
    return result


def _compile_built(
    value: Any,
    file: Path,
    path: str,
    civ: str,
    identities: IdentityCatalog,
) -> list[CheckDescriptor]:
    return _structure_checks("built", _list(value, file, path), file, path, civ, identities)


def _compile_age_up(
    value: Any,
    file: Path,
    path: str,
    civ: str,
    identities: IdentityCatalog,
) -> list[CheckDescriptor]:
    return _structure_checks("age_up", [value], file, path, civ, identities)


def _compile_upgrades(
    value: Any,
    file: Path,
    path: str,
    civ: str,
    identities: IdentityCatalog,
) -> list[CheckDescriptor]:
    result = []
    for index, entry in enumerate(_list(value, file, path)):
        item_path = f"{path}[{index}]"
        mapping = _mapping(entry, file, item_path)
        unknown = set(mapping) - {"id", "optional", "queued"}
        if unknown:
            _error(file, f"{item_path}.{next(iter(unknown))}", "unknown field")
        identifier = _string(mapping.get("id"), file, f"{item_path}.id")
        optional = mapping.get("optional", False)
        if not isinstance(optional, bool):
            _error(file, f"{item_path}.optional", "must be boolean")
        queued = mapping.get("queued", False)
        if not isinstance(queued, bool):
            _error(file, f"{item_path}.queued", "must be boolean")
        payload: dict[str, object] = {"id": identifier, "queued": queued}
        _resolve_identity_payload(
            payload,
            kind="upgrades",
            civ=civ,
            identities=identities,
            file=file,
            path=item_path,
        )
        result.append(CheckDescriptor("upgrades", optional, payload))
    return result


def _counted_identity_entries(
    value: Any,
    file: Path,
    path: str,
    flags: tuple[str, ...] = (),
) -> list[tuple[str, str, dict[str, object]]]:
    result = []
    permitted = {"id", "count", *flags}
    for index, entry in enumerate(_list(value, file, path)):
        item_path = f"{path}[{index}]"
        mapping = _mapping(entry, file, item_path)
        unknown = set(mapping) - permitted
        if unknown:
            _error(file, f"{item_path}.{next(iter(unknown))}", "unknown field")
        identifier = _string(mapping.get("id"), file, f"{item_path}.id")
        payload: dict[str, object] = {
            "id": identifier,
            "count": _positive(mapping.get("count", 1), file, f"{item_path}.count"),
        }
        for flag in flags:
            if flag in mapping:
                if not isinstance(mapping[flag], bool):
                    _error(file, f"{item_path}.{flag}", "must be boolean")
                payload[flag] = mapping[flag]
        result.append((item_path, identifier, payload))
    return result


def _resolve_counted_squad(
    payload: dict[str, object],
    *,
    kind: str,
    identifier: str,
    civ: str,
    identities: IdentityCatalog,
    file: Path,
    path: str,
) -> None:
    try:
        _resolve_squad_family_payload(
            payload,
            civ=civ,
            identities=identities,
            file=file,
            path=path,
        )
    except IdentityCatalogError as exc:
        _error(
            file,
            f"{path}.id",
            f"civilization '{normalize_identity_id(civ)}', {kind} check, "
            f"expected squad ID '{identifier}': {exc}",
        )


def _compile_produce(
    value: Any,
    file: Path,
    path: str,
    civ: str,
    identities: IdentityCatalog,
) -> list[CheckDescriptor]:
    result = []
    for item_path, identifier, payload in _counted_identity_entries(
        value, file, path, ("constant", "queued")
    ):
        _resolve_counted_squad(
            payload,
            kind="produce",
            identifier=identifier,
            civ=civ,
            identities=identities,
            file=file,
            path=item_path,
        )
        optional = payload.get("constant", False) is True
        result.append(CheckDescriptor("produce", optional, payload))
    return result


def _compile_buildings(
    value: Any,
    file: Path,
    path: str,
    civ: str,
    identities: IdentityCatalog,
) -> list[CheckDescriptor]:
    result = []
    for item_path, identifier, payload in _counted_identity_entries(value, file, path):
        _resolve_identity_payload(
            payload,
            kind="buildings",
            civ=civ,
            identities=identities,
            file=file,
            path=item_path,
        )
        result.append(CheckDescriptor("buildings", False, payload))
    return result


def _compile_units(
    value: Any,
    file: Path,
    path: str,
    civ: str,
    identities: IdentityCatalog,
) -> list[CheckDescriptor]:
    result = []
    for item_path, identifier, payload in _counted_identity_entries(value, file, path):
        _resolve_counted_squad(
            payload,
            kind="units",
            identifier=identifier,
            civ=civ,
            identities=identities,
            file=file,
            path=item_path,
        )
        result.append(CheckDescriptor("units", False, payload))
    return result


def _compile_hints(
    value: Any,
    file: Path,
    path: str,
    civ: str,
    identities: IdentityCatalog,
) -> list[CheckDescriptor]:
    checks = []
    for index, item in enumerate(_list(value, file, path)):
        text = _string(item, file, f"{path}[{index}]")
        checks.append(CheckDescriptor("hints", True, {"text": text}))
    return checks


CheckCompiler = Callable[[Any, Path, str, str, IdentityCatalog], list[CheckDescriptor]]

CHECK_COMPILERS: dict[str, CheckCompiler] = {
    "vils": _compile_vils,
    "resources": _compile_resources,
    "rallypoint": _compile_rallypoint,
    "built": _compile_built,
    "age_up": _compile_age_up,
    "upgrades": _compile_upgrades,
    "produce": _compile_produce,
    "buildings": _compile_buildings,
    "units": _compile_units,
    "hints": _compile_hints,
}
CHECK_FIELDS = set(CHECK_COMPILERS)


def _check_descriptors(
    kind: str,
    value: Any,
    file: Path,
    path: str,
    civ: str,
    identities: IdentityCatalog,
) -> list[CheckDescriptor]:
    compiler = CHECK_COMPILERS.get(kind)
    if compiler is None:
        _error(file, path, "unknown check")
    return compiler(value, file, path, civ, identities)


def _compile_order(document: Any, file: Path | str, index: int | None, identities: IdentityCatalog) -> BuildOrder:
    base = "" if index is None else f"[{index}]."
    order = _mapping(document, file, base.rstrip("."))
    unknown = set(order) - {"civ", "title", "link", "steps"}
    if unknown:
        _error(file, f"{base}{next(iter(unknown))}", "unknown field")
    civ = _string(order.get("civ"), file, f"{base}civ")
    title = _string(order.get("title"), file, f"{base}title")
    link = _source_link(order["link"], file, f"{base}link") if "link" in order else None
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
    return BuildOrder(normalize_id(civ, title), civ, title, tuple(compiled_steps), link)


def compile_document(
    document: Any,
    source: Path | str,
    identities: IdentityCatalog | None = None,
) -> BuildOrder:
    if identities is None:
        identities = IdentityCatalog.load(DEFAULT_IDENTITY_CATALOG)
    return _compile_order(document, source, None, identities)


def _compile_files(
    files: list[tuple[Path, str]],
    identities: IdentityCatalog,
) -> Catalog:
    orders: list[BuildOrder] = []
    for file, source in files:
        try:
            document = yaml.safe_load(file.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise BuildOrderValidationError(f"{source}: invalid YAML: {exc}") from exc
        except OSError as exc:
            raise BuildOrderValidationError(f"{source}: could not read YAML: {exc}") from exc
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


def compile_inputs(
    inputs: list[Path],
    identities: IdentityCatalog | None = None,
) -> Catalog:
    if identities is None:
        identities = IdentityCatalog.load(DEFAULT_IDENTITY_CATALOG)
    if not inputs:
        raise BuildOrderValidationError("at least one YAML file or directory is required")
    files: list[tuple[Path, str]] = []
    for input_path in inputs:
        if input_path.is_file():
            if input_path.suffix.lower() not in {".yaml", ".yml"}:
                raise BuildOrderValidationError(
                    f"{input_path}: input file must have a .yaml or .yml extension"
                )
            files.append((input_path, input_path.name))
        elif input_path.is_dir():
            files.extend(
                (path, path.relative_to(input_path).as_posix())
                for path in sorted(
                    (
                        path
                        for path in input_path.rglob("*")
                        if path.suffix.lower() in {".yaml", ".yml"}
                    ),
                    key=lambda path: path.relative_to(input_path).as_posix(),
                )
            )
        else:
            raise BuildOrderValidationError(f"{input_path}: input path does not exist")
    return _compile_files(files, identities)


def compile_directory(
    input_dir: Path,
    identities: IdentityCatalog | None = None,
) -> Catalog:
    return compile_inputs([input_dir], identities=identities)


def merge_catalog(existing: Catalog, incoming: Catalog) -> Catalog:
    merged: dict[str, BuildOrder] = {}
    for order in existing.build_orders:
        if order.id in merged:
            raise BuildOrderValidationError(
                f"duplicate existing datastore id '{order.id}'"
            )
        merged[order.id] = order
    incoming_ids: set[str] = set()
    for order in incoming.build_orders:
        if order.id in incoming_ids:
            raise BuildOrderValidationError(
                f"duplicate generated id '{order.id}'"
            )
        incoming_ids.add(order.id)
        merged[order.id] = order
    return Catalog(tuple(merged[identifier] for identifier in sorted(merged)))


def _reverse_identity(
    identities: IdentityCatalog, civ: str, category: str, canonical: str
) -> str:
    normalized_civ = normalize_identity_id(civ)
    aliases = identities.civilizations.get(normalized_civ, {}).get(category, {})
    matches = [alias for alias, value in aliases.items() if value == canonical]
    if not matches:
        raise BuildOrderValidationError(
            f"cannot extract unknown canonical {category} ID {canonical!r} for {normalized_civ}"
        )
    return min(matches, key=lambda item: (len(item), item))


def _reverse_squad_family(
    identities: IdentityCatalog, civ: str, canonical_ids: object
) -> str:
    if not isinstance(canonical_ids, list) or not all(
        isinstance(item, str) for item in canonical_ids
    ):
        raise BuildOrderValidationError("cannot extract malformed squad family payload")
    expected = tuple(canonical_ids)
    aliases = identities.squad_aliases.get(normalize_identity_id(civ), {})
    families = {
        family.family_id
        for family in aliases.values()
        if family.canonical_ids == expected
    }
    if not families:
        raise BuildOrderValidationError(
            f"cannot extract unknown canonical squad family for {normalize_identity_id(civ)}"
        )
    return min(families)


def _identity_payload(
    payload: dict[str, object], *, kind: str, civ: str, identities: IdentityCatalog
) -> dict[str, object]:
    category = _identity_category(kind, civ)
    result: dict[str, object] = {}
    if "id" in payload:
        result["id"] = _reverse_identity(
            identities, civ, category, str(payload["id"])
        )
    elif "oneof" in payload and isinstance(payload["oneof"], list):
        result["oneof"] = [
            _reverse_identity(identities, civ, category, str(item))
            for item in payload["oneof"]
        ]
    else:
        raise BuildOrderValidationError(
            f"cannot extract malformed {kind} identity payload"
        )
    return result


def _step_to_yaml(
    step: Step, civ: str, identities: IdentityCatalog
) -> dict[str, object]:
    document: dict[str, object] = {}
    if step.title is not None:
        document["title"] = step.title
    grouped: dict[str, list[CheckDescriptor]] = {}
    order: list[str] = []
    for check in step.checks:
        if check.kind not in CHECK_FIELDS:
            raise BuildOrderValidationError(
                f"cannot extract unsupported check kind {check.kind!r}"
            )
        if check.kind not in grouped:
            grouped[check.kind] = []
            order.append(check.kind)
        grouped[check.kind].append(check)

    for kind in order:
        checks = grouped[kind]
        if kind == "vils":
            value: dict[str, object] = {}
            no_collect: list[str] = []
            for check in checks:
                if check.payload.get("no_collect") is True:
                    no_collect.append(str(check.payload.get("resource")))
                else:
                    for resource in RESOURCE_ORDER:
                        if resource in check.payload:
                            value[resource] = check.payload[resource]
            if no_collect:
                value["no_collect"] = no_collect
            document[kind] = value
        elif kind == "resources":
            document[kind] = {
                str(check.payload["resource"]): check.payload["count"]
                for check in checks
            }
        elif kind == "rallypoint":
            document[kind] = [str(check.payload["resource"]) for check in checks]
        elif kind in {"built", "age_up"}:
            entries: list[dict[str, object]] = []
            for check in checks:
                entry = _identity_payload(
                    check.payload, kind=kind, civ=civ, identities=identities
                )
                for field in ("count", "vils", "location"):
                    if field in check.payload:
                        entry[field] = check.payload[field]
                entries.append(entry)
            if kind == "age_up":
                if len(entries) != 1:
                    raise BuildOrderValidationError(
                        "cannot extract a step with multiple age_up checks"
                    )
                document[kind] = entries[0]
            else:
                document[kind] = entries
        elif kind == "upgrades":
            entries = []
            for check in checks:
                entry = _identity_payload(
                    check.payload, kind=kind, civ=civ, identities=identities
                )
                if check.payload.get("queued") is True:
                    entry["queued"] = True
                if check.optional:
                    entry["optional"] = True
                entries.append(entry)
            document[kind] = entries
        elif kind in {"produce", "units"}:
            entries = []
            for check in checks:
                entry = {
                    "id": _reverse_squad_family(
                        identities, civ, check.payload.get("ids")
                    ),
                    "count": check.payload["count"],
                }
                for flag in ("constant", "queued"):
                    if check.payload.get(flag) is True:
                        entry[flag] = True
                entries.append(entry)
            document[kind] = entries
        elif kind == "buildings":
            document[kind] = [
                {
                    "id": _reverse_identity(
                        identities, civ, "entity", str(check.payload["id"])
                    ),
                    "count": check.payload["count"],
                }
                for check in checks
            ]
        elif kind == "hints":
            document[kind] = [str(check.payload["text"]) for check in checks]
    return document


def order_to_yaml(order: BuildOrder, identities: IdentityCatalog) -> str:
    document: dict[str, object] = {"civ": order.civ, "title": order.title}
    if order.link is not None:
        document["link"] = order.link
    document["steps"] = [
        _step_to_yaml(step, order.civ, identities) for step in order.steps
    ]
    return yaml.safe_dump(document, sort_keys=False, allow_unicode=True)


def _print_catalog(catalog: Catalog) -> None:
    headers = ("ID", "CIV", "TITLE", "SOURCE")
    rows = [
        (order.id, order.civ, order.title, order.link or "")
        for order in sorted(catalog.build_orders, key=lambda item: item.id)
    ]
    widths = [
        max([len(headers[index]), *(len(row[index]) for row in rows)])
        for index in range(len(headers))
    ]
    print("  ".join(value.ljust(widths[index]) for index, value in enumerate(headers)))
    print("  ".join("-" * width for width in widths))
    for row in rows:
        print("  ".join(value.ljust(widths[index]) for index, value in enumerate(row)))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage Macro Trainer build orders")
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="compile YAML into the datastore")
    build.add_argument("inputs", nargs="*", type=Path, default=[Path("build_orders")])
    listing = commands.add_parser("list", help="list compiled build orders")
    delete = commands.add_parser("delete", help="delete compiled build orders")
    delete.add_argument("ids", nargs="+")
    extract = commands.add_parser("extract", help="extract normalized YAML")
    extract.add_argument("ids", nargs="+")
    extract.add_argument("--output-dir", type=Path, default=Path.cwd())
    import_command = commands.add_parser(
        "import", help="import an RTS Overlay build order into the datastore"
    )
    source = import_command.add_mutually_exclusive_group(required=True)
    source.add_argument("--file", type=Path, dest="import_file")
    source.add_argument("--url", dest="import_url")
    import_command.add_argument("--save_yaml", type=Path)
    for command in (build, listing, delete, extract, import_command):
        command.add_argument("--profile")
    return parser


def _forward_default_build(arguments: list[str]) -> list[str]:
    if not arguments:
        return ["build"]
    if arguments[0] in {"-h", "--help", "build", "list", "delete", "extract", "import"}:
        return arguments
    return ["build", *arguments]


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    try:
        options = _parser().parse_args(_forward_default_build(arguments))
        datastore_path = resolve_datastore_path(options.profile)
        existing = load_datastore(datastore_path)
        if options.command == "build":
            incoming = compile_inputs(options.inputs)
            merged = merge_catalog(existing, incoming)
            write_datastore(datastore_path, merged)
            print(f"Stored {len(incoming.build_orders)} build order(s) in {datastore_path}")
        elif options.command == "import":
            if options.import_file is not None:
                source: Path | str = options.import_file
                raw = read_overlay_file(options.import_file)
            else:
                source = options.import_url
                raw = fetch_overlay_document(options.import_url)
            translated = translate_overlay_document(raw, source)
            incoming_order = compile_document(translated, source)
            merged = merge_catalog(existing, Catalog((incoming_order,)))
            write_datastore(datastore_path, merged)
            print(f"Stored imported build order {incoming_order.id} in {datastore_path}")
        elif options.command == "list":
            _print_catalog(existing)
        elif options.command == "delete":
            if len(options.ids) != len(set(options.ids)):
                raise BuildOrderValidationError("duplicate build order IDs requested")
            by_id = {order.id: order for order in existing.build_orders}
            unknown = [identifier for identifier in options.ids if identifier not in by_id]
            if unknown:
                raise BuildOrderValidationError(
                    f"unknown build order ID(s): {', '.join(unknown)}"
                )
            write_datastore(
                datastore_path,
                Catalog(tuple(by_id[key] for key in sorted(set(by_id) - set(options.ids)))),
            )
            print(f"Deleted {len(options.ids)} build order(s)")
        elif options.command == "extract":
            if len(options.ids) != len(set(options.ids)):
                raise BuildOrderValidationError("duplicate build order IDs requested")
            by_id = {order.id: order for order in existing.build_orders}
            unknown = [identifier for identifier in options.ids if identifier not in by_id]
            if unknown:
                raise BuildOrderValidationError(
                    f"unknown build order ID(s): {', '.join(unknown)}"
                )
            identities = IdentityCatalog.load(DEFAULT_IDENTITY_CATALOG)
            outputs: list[tuple[Path, str]] = []
            for identifier in options.ids:
                normalized_filename = normalize_id("", identifier)
                if not normalized_filename:
                    raise BuildOrderValidationError(
                        f"build order ID {identifier!r} cannot form a safe filename"
                    )
                filename = f"{normalized_filename}.yaml"
                outputs.append(
                    (options.output_dir / filename, order_to_yaml(by_id[identifier], identities))
                )
            paths = [path for path, _ in outputs]
            if len(paths) != len(set(paths)):
                raise BuildOrderValidationError("extracted build order filename collision")
            existing_outputs = [path for path in paths if path.exists()]
            if existing_outputs:
                raise BuildOrderValidationError(
                    f"output file already exists: {existing_outputs[0]}"
                )
            options.output_dir.mkdir(parents=True, exist_ok=True)
            temporary: list[tuple[Path, Path]] = []
            try:
                for path, content in outputs:
                    temp = path.with_name(path.name + ".tmp")
                    temp.write_text(content, encoding="utf-8", newline="")
                    temporary.append((temp, path))
                for temp, path in temporary:
                    temp.replace(path)
            finally:
                for temp, _ in temporary:
                    if temp.exists():
                        temp.unlink()
            print(f"Extracted {len(outputs)} build order(s) to {options.output_dir}")
        return 0
    except (BuildOrderValidationError, ImportValidationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except (DatastoreError, ProfileResolutionError, IdentityCatalogError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
