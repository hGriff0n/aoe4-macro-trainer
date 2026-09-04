import argparse
import html
from http.client import HTTPException
import json
from pathlib import Path
import re
import sys
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

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
CHECK_ID_CATEGORIES = {
    "built": "entity",
    "buildings": "entity",
    "produce": "squad",
    "units": "squad",
    "upgrades": "upgrade",
}
UPGRADE_AGE_UP_CIVS = frozenset({"abbasid", "ayyubids", "templar", "golden_horde"})
OVERLAY_CIVILIZATIONS = {
    "Abbasid Dynasty": "abbasid",
    "Ayyubids": "ayyubids",
    "Byzantines": "byzantines",
    "Chinese": "chinese",
    "Delhi Sultanate": "delhi",
    "English": "english",
    "French": "french",
    "Golden Horde": "golden_horde",
    "House of Lancaster": "house_of_lancaster",
    "Holy Roman Empire": "hre",
    "Japanese": "japanese",
    "Jeanne d'Arc": "jeanne_darc",
    "Jin Dynasty": "jin_dynasty",
    "Knights Templar": "templar",
    "Macedonian Dynasty": "macedonian_dynasty",
    "Malians": "malians",
    "Mongols": "mongols",
    "Order of the Dragon": "order_of_the_dragon",
    "Ottomans": "ottomans",
    "Rus": "rus",
    "Sengoku Daimyo": "sengoku_daimyo",
    "Tughlaq Dynasty": "tughlaq_dynasty",
    "Zhu Xi's Legacy": "zhu_xi",
}
AOE4GUIDES_BUILD_ID = re.compile(r"^[A-Za-z0-9_-]+$")
OVERLAY_ROOT_FIELDS = {
    "description",
    "civilization",
    "name",
    "author",
    "source",
    "build_order",
    "video",
    "season",
    "map",
    "strategy",
}
OVERLAY_STEP_FIELDS = {"age", "population_count", "time", "villager_count", "resources", "notes"}
OVERLAY_RESOURCE_FIELDS = {"food", "wood", "gold", "stone", "builder"}
OVERLAY_TIME = re.compile(r"^\d+:[0-5]\d$")
OVERLAY_NOTE_TOKEN = re.compile(
    r"@(?P<token>[^@\s/]+/(?P<name>[^@\s/]+))\.webp@"
)
OVERLAY_NOTE_LABELS = {
    "civilization_flag/ayy": "Ayyubids",
    "civilization_flag/eng": "English",
    "civilization_flag/hos": "House of Lancaster",
    "civilization_flag/mon": "Mongols",
    "resource/berrybush": "Berry Bush",
    "resource/gaiatreeprototypetree": "Tree",
    "technology_templar/safepassage": "Safe Passage",
}
MAX_OVERLAY_RESPONSE_BYTES = 2 * 1024 * 1024


class BuildOrderValidationError(ValueError):
    pass


class RejectRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def build_overlay_opener():
    return build_opener(RejectRedirectHandler())


def render_overlay_note(note: str) -> str:
    decoded = html.unescape(note)

    def readable_token(match: re.Match[str]) -> str:
        name = match.group("name")
        if name.startswith("resource_"):
            name = name.removeprefix("resource_")
        label = OVERLAY_NOTE_LABELS.get(
            match.group("token"),
            name.replace("-", " ").replace("_", " ").title(),
        )
        if match.start() > 0 and (
            decoded[match.start() - 1].isalnum()
            or decoded[match.start() - 1] == "@"
        ):
            label = " " + label
        if match.end() < len(decoded) and decoded[match.end()].isalnum():
            label += " "
        return label

    return OVERLAY_NOTE_TOKEN.sub(readable_token, decoded)


def translate_overlay_document(document: Any, source: Path | str) -> dict[str, object]:
    file = source
    overlay = _mapping(document, file, "")
    _reject_unknown_fields(overlay, OVERLAY_ROOT_FIELDS, source, "")
    _overlay_text(overlay.get("description"), source, "description")
    for field in ("author", "video"):
        if field in overlay:
            _overlay_text(overlay[field], source, field)
    for field in ("season", "map", "strategy"):
        if field in overlay and overlay[field] is not None:
            if not isinstance(overlay[field], str):
                _error(source, field, "must be a string or null")
    civilization = _string(overlay.get("civilization"), file, "civilization")
    if civilization not in OVERLAY_CIVILIZATIONS:
        _error(source, "civilization", f"unsupported civilization '{civilization}'")

    steps = []
    raw_steps = _list(overlay.get("build_order"), file, "build_order")
    if not raw_steps:
        _error(source, "build_order", "must not be empty")
    for index, raw_step in enumerate(raw_steps):
        step_path = f"build_order[{index}]"
        step = _mapping(raw_step, file, step_path)
        _reject_unknown_fields(step, OVERLAY_STEP_FIELDS, source, step_path)
        _overlay_integer(step.get("age"), source, f"{step_path}.age", minimum=-1, maximum=4)
        _overlay_integer(step.get("population_count"), source, f"{step_path}.population_count", minimum=-1)
        _overlay_integer(step.get("villager_count"), source, f"{step_path}.villager_count", minimum=-1)
        resources_path = f"{step_path}.resources"
        resources = _mapping(step.get("resources"), file, resources_path)
        _reject_unknown_fields(resources, OVERLAY_RESOURCE_FIELDS, source, resources_path)
        translated: dict[str, object] = {}
        if "time" in step:
            time = _string(step["time"], file, f"{step_path}.time")
            if not OVERLAY_TIME.fullmatch(time):
                _error(source, f"{step_path}.time", "must use M:SS time format")
            translated["title"] = time
        allocations = {}
        for resource in RESOURCE_ORDER:
            count = _overlay_integer(
                resources.get(resource),
                source,
                f"{resources_path}.{resource}",
                minimum=0,
                range_message="must be a non-negative integer",
            )
            if count > 0:
                allocations[resource] = count
        _overlay_integer(resources.get("builder"), source, f"{resources_path}.builder", minimum=-1)
        if allocations:
            translated["vils"] = allocations
        notes = []
        for note_index, note in enumerate(_list(step.get("notes"), file, f"{step_path}.notes")):
            if not isinstance(note, str):
                _error(source, f"{step_path}.notes[{note_index}]", "must be a string")
            if note:
                notes.append(render_overlay_note(note))
        if notes:
            translated["hints"] = notes
        if not allocations and not notes:
            _error(source, step_path, "has no translatable checks or hints")
        steps.append(translated)

    return {
        "civ": OVERLAY_CIVILIZATIONS[civilization],
        "title": _string(overlay.get("name"), file, "name"),
        "link": _source_link(overlay.get("source"), file, "source"),
        "steps": steps,
    }


def fetch_overlay_document(url: str) -> Any:
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise BuildOrderValidationError(f"{url}: invalid aoe4guides build URL: {exc}") from exc
    if (
        parsed.scheme.lower() != "https"
        or parsed.hostname not in {"aoe4guides.com", "www.aoe4guides.com"}
        or port is not None
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise BuildOrderValidationError(f"{url}: expected an HTTPS aoe4guides.com build URL")
    path_parts = [part for part in parsed.path.split("/") if part]
    if len(path_parts) == 2 and path_parts[0] == "builds":
        build_id = path_parts[1]
    elif len(path_parts) == 3 and path_parts[:2] == ["api", "builds"]:
        build_id = path_parts[2]
    else:
        raise BuildOrderValidationError(f"{url}: expected an aoe4guides.com build URL")
    if not AOE4GUIDES_BUILD_ID.fullmatch(build_id):
        raise BuildOrderValidationError(f"{url}: invalid aoe4guides build ID")

    endpoint = f"https://aoe4guides.com/api/builds/{build_id}?overlay=true"
    request = Request(
        endpoint,
        headers={"Accept": "application/json", "User-Agent": "aoe4-macro-trainer"},
    )
    try:
        with build_overlay_opener().open(request, timeout=30) as response:
            body_bytes = response.read(MAX_OVERLAY_RESPONSE_BYTES + 1)
            if len(body_bytes) > MAX_OVERLAY_RESPONSE_BYTES:
                raise BuildOrderValidationError(
                    f"{url}: aoe4guides response exceeds {MAX_OVERLAY_RESPONSE_BYTES} bytes"
                )
            body = body_bytes.decode("utf-8")
    except HTTPError as exc:
        if exc.code == 404:
            raise BuildOrderValidationError(f"{url}: aoe4guides build not found (HTTP 404)") from exc
        if exc.code == 429:
            raise BuildOrderValidationError(f"{url}: aoe4guides rate limit exceeded (HTTP 429)") from exc
        raise BuildOrderValidationError(f"{url}: aoe4guides request failed (HTTP {exc.code})") from exc
    except URLError as exc:
        raise BuildOrderValidationError(f"{url}: unable to reach aoe4guides: {exc.reason}") from exc
    except UnicodeDecodeError as exc:
        raise BuildOrderValidationError(
            f"{url}: aoe4guides returned non-UTF-8 data: {exc}"
        ) from exc
    except HTTPException as exc:
        raise BuildOrderValidationError(
            f"{url}: aoe4guides response was interrupted: {exc}"
        ) from exc
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise BuildOrderValidationError(f"{url}: aoe4guides returned invalid JSON: {exc}") from exc


def _error(file: Path | str, path: str, message: str) -> None:
    raise BuildOrderValidationError(f"{file}: {path}: {message}")


def _reject_unknown_fields(
    mapping: dict[str, Any], allowed: set[str], file: Path | str, path: str
) -> None:
    unknown = set(mapping) - allowed
    if unknown:
        field = sorted(unknown)[0]
        _error(file, f"{path}.{field}" if path else field, "unknown field")


def _overlay_integer(
    value: Any,
    file: Path | str,
    path: str,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
    range_message: str | None = None,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _error(file, path, "must be an integer")
    if (minimum is not None and value < minimum) or (maximum is not None and value > maximum):
        if range_message is not None:
            _error(file, path, range_message)
        if minimum is not None and maximum is not None:
            _error(file, path, f"must be between {minimum} and {maximum}")
        if minimum is not None:
            _error(file, path, f"must be at least {minimum}")
        _error(file, path, f"must be at most {maximum}")
    return value


def _overlay_text(value: Any, file: Path | str, path: str) -> str:
    if not isinstance(value, str):
        _error(file, path, "must be a string")
    return value


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


def _source_link(value: Any, file: Path, path: str) -> str:
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


def _resource_checks(value: Any, file: Path, path: str) -> list[CheckDescriptor]:
    mapping = _mapping(value, file, path)
    checks: list[CheckDescriptor] = []
    for resource, count in mapping.items():
        item_path = f"{path}.{resource}"
        if resource not in RESOURCES:
            _error(file, item_path, "unsupported resource")
        number = _positive(count, file, item_path)
        title = f"Collect at least {number} {resource}"
        checks.append(CheckDescriptor("resources", title, False, {"resource": resource, "count": number}))
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
        checks.append(CheckDescriptor("rallypoint", f"Rally to {resource}", False, {"resource": resource}))
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
        if kind == "age_up":
            payload["trigger"] = _age_up_trigger(civ)
            title = f"Age Up: {label}"
        else:
            count_label = "" if payload["count"] == 1 else f'{payload["count"]} '
            title = f"Build {count_label}{label}"
        result.append(CheckDescriptor(kind, title, False, dict(payload)))
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
        label = _humanize_identity_id(identifier)
        title = f"Queue {label} for research" if queued else f"Research {label}"
        if optional:
            title = f"[Optional] {title}"
        result.append(CheckDescriptor("upgrades", title, optional, payload))
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
) -> str:
    try:
        return _resolve_squad_family_payload(
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
        family_id = _resolve_counted_squad(
            payload,
            kind="produce",
            identifier=identifier,
            civ=civ,
            identities=identities,
            file=file,
            path=item_path,
        )
        unit = _humanize_identity_id(family_id)
        counted_unit = unit if payload["count"] == 1 else _pluralize_unit(unit)
        optional = False
        if payload.get("constant", False):
            title = f"Constantly produce {unit}"
            optional = True
        elif payload.get("queued", False):
            title = f"Queue {payload['count']} {counted_unit}"
        else:
            title = f"Produce {payload['count']} {counted_unit}"
        result.append(CheckDescriptor("produce", title, optional, payload))
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
        result.append(CheckDescriptor("buildings", _humanize_identity_id(identifier), False, payload))
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
        family_id = _resolve_counted_squad(
            payload,
            kind="units",
            identifier=identifier,
            civ=civ,
            identities=identities,
            file=file,
            path=item_path,
        )
        title = f"Have {payload['count']} active {_humanize_identity_id(family_id)}"
        result.append(CheckDescriptor("units", title, False, payload))
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
        checks.append(CheckDescriptor("hints", f"[HINT] {text}", True, {"text": text}))
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


def _compile_order(document: Any, file: Path, index: int | None, identities: IdentityCatalog) -> BuildOrder:
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile or import Macro Trainer build orders.")
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--import-file", type=Path, help="RTS Overlay .bo JSON file to import")
    inputs.add_argument("--import-url", help="aoe4guides build page or API URL to import")
    parser.add_argument("--output", type=Path, required=True, help="YAML file to write")
    args = parser.parse_args(argv)

    try:
        if args.import_file is not None:
            try:
                document = json.loads(args.import_file.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                raise BuildOrderValidationError(
                    f"{args.import_file}: unable to read overlay JSON: {exc}"
                ) from exc
            source: Path | str = args.import_file
        else:
            document = fetch_overlay_document(args.import_url)
            source = args.import_url
        translated = translate_overlay_document(document, source)
        args.output.write_text(
            yaml.safe_dump(translated, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
            newline="",
        )
    except (BuildOrderValidationError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
