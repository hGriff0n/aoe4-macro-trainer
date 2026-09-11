from __future__ import annotations

import html
import json
import re
from http.client import HTTPException, IncompleteRead
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

import yaml

from .identities import IdentityCatalog

OVERLAY_CIVILIZATIONS = {
    "Abbasid Dynasty": "abbasid", "Ayyubids": "ayyubids", "Byzantines": "byzantines",
    "Chinese": "chinese", "Delhi Sultanate": "delhi", "English": "english",
    "French": "french", "Golden Horde": "golden_horde", "House of Lancaster": "house_of_lancaster",
    "Holy Roman Empire": "hre", "Japanese": "japanese", "Jeanne d'Arc": "jeanne_darc",
    "Jin Dynasty": "jin_dynasty", "Knights Templar": "templar", "Macedonian Dynasty": "macedonian_dynasty",
    "Malians": "malians", "Mongols": "mongols", "Order of the Dragon": "order_of_the_dragon",
    "Ottomans": "ottomans", "Rus": "rus", "Sengoku Daimyo": "sengoku_daimyo",
    "Tughlaq Dynasty": "tughlaq_dynasty", "Zhu Xi's Legacy": "zhu_xi",
}
AOE4GUIDES_BUILD_ID = re.compile(r"^[A-Za-z0-9_-]+$")
OVERLAY_ROOT_FIELDS = {"description", "civilization", "name", "author", "source", "build_order", "video", "season", "map", "strategy"}
OVERLAY_STEP_FIELDS = {"age", "population_count", "time", "villager_count", "resources", "notes"}
OVERLAY_RESOURCE_FIELDS = {"food", "wood", "gold", "stone", "builder"}
OVERLAY_TIME = re.compile(r"^\d+:[0-5]\d$")
OVERLAY_NOTE_TOKEN = re.compile(r"@(?P<token>[^@\s/]+/(?P<name>[^@\s/]+))\.webp@")
OVERLAY_NOTE_LABELS = {
    "civilization_flag/ayy": "Ayyubids", "civilization_flag/eng": "English",
    "civilization_flag/hos": "House of Lancaster", "civilization_flag/mon": "Mongols",
    "resource/berrybush": "Berry Bush", "resource/gaiatreeprototypetree": "Tree",
    "technology_templar/safepassage": "Safe Passage",
}
MAX_OVERLAY_RESPONSE_BYTES = 2 * 1024 * 1024


class ImportValidationError(ValueError):
    pass


class RejectRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def build_overlay_opener():
    return build_opener(RejectRedirectHandler())


def read_overlay_file(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ImportValidationError(f"{path}: unable to read overlay JSON: {exc}") from exc


def render_import_yaml(document: dict[str, object]) -> str:
    try:
        return yaml.safe_dump(document, sort_keys=False, allow_unicode=True)
    except yaml.YAMLError as exc:
        raise ImportValidationError(f"unable to render imported YAML: {exc}") from exc


def write_import_yaml(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(content, encoding="utf-8", newline="")
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def render_overlay_note(note: str) -> str:
    decoded = html.unescape(note)
    def readable_token(match: re.Match[str]) -> str:
        name = match.group("name")
        if name.startswith("resource_"):
            name = name.removeprefix("resource_")
        label = OVERLAY_NOTE_LABELS.get(match.group("token"), name.replace("-", " ").replace("_", " ").title())
        if match.start() > 0 and (decoded[match.start() - 1].isalnum() or decoded[match.start() - 1] == "@"):
            label = " " + label
        if match.end() < len(decoded) and decoded[match.end()].isalnum():
            label += " "
        return label
    return OVERLAY_NOTE_TOKEN.sub(readable_token, decoded)


def _error(file: Path | str, path: str, message: str) -> None:
    raise ImportValidationError(f"{file}: {path}: {message}")


def _mapping(value: Any, file: Path | str, path: str) -> dict[str, Any]:
    if not isinstance(value, dict): _error(file, path, "must be a mapping")
    return value


def _list(value: Any, file: Path | str, path: str) -> list[Any]:
    if not isinstance(value, list): _error(file, path, "must be a list")
    return value


def _string(value: Any, file: Path | str, path: str) -> str:
    if not isinstance(value, str) or not value: _error(file, path, "must be a non-empty string")
    return value


def _source_link(value: Any, file: Path | str, path: str) -> str:
    if not isinstance(value, str) or not value or any(c.isspace() for c in value): _error(file, path, "must be an absolute HTTP(S) URL")
    try: parsed = urlsplit(value)
    except ValueError: _error(file, path, "must be an absolute HTTP(S) URL")
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc: _error(file, path, "must be an absolute HTTP(S) URL")
    return value


def _reject_unknown_fields(mapping: dict[str, Any], allowed: set[str], file: Path | str, path: str) -> None:
    unknown = set(mapping) - allowed
    if unknown: _error(file, f"{path}.{sorted(unknown)[0]}" if path else sorted(unknown)[0], "unknown field")


def _overlay_integer(value: Any, file: Path | str, path: str, *, minimum: int | None = None, maximum: int | None = None, range_message: str | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int): _error(file, path, "must be an integer")
    if (minimum is not None and value < minimum) or (maximum is not None and value > maximum):
        if range_message: _error(file, path, range_message)
        if minimum is not None and maximum is not None: _error(file, path, f"must be between {minimum} and {maximum}")
        if minimum is not None: _error(file, path, f"must be at least {minimum}")
        _error(file, path, f"must be at most {maximum}")
    return value


def _overlay_text(value: Any, file: Path | str, path: str) -> str:
    if not isinstance(value, str): _error(file, path, "must be a string")
    return value


def translate_overlay_document(document: Any, source: Path | str, identities: IdentityCatalog | None = None) -> dict[str, object]:
    overlay = _mapping(document, source, "")
    _reject_unknown_fields(overlay, OVERLAY_ROOT_FIELDS, source, "")
    _overlay_text(overlay.get("description"), source, "description")
    for field in ("author", "video"):
        if field in overlay: _overlay_text(overlay[field], source, field)
    for field in ("season", "map", "strategy"):
        if field in overlay and overlay[field] is not None and not isinstance(overlay[field], str): _error(source, field, "must be a string or null")
    civilization = _string(overlay.get("civilization"), source, "civilization")
    if civilization not in OVERLAY_CIVILIZATIONS: _error(source, "civilization", f"unsupported civilization '{civilization}'")
    raw_steps = _list(overlay.get("build_order"), source, "build_order")
    if not raw_steps: _error(source, "build_order", "must not be empty")
    steps = []
    for index, raw_step in enumerate(raw_steps):
        step_path = f"build_order[{index}]"; step = _mapping(raw_step, source, step_path)
        _reject_unknown_fields(step, OVERLAY_STEP_FIELDS, source, step_path)
        _overlay_integer(step.get("age"), source, f"{step_path}.age", minimum=-1, maximum=4)
        _overlay_integer(step.get("population_count"), source, f"{step_path}.population_count", minimum=-1)
        _overlay_integer(step.get("villager_count"), source, f"{step_path}.villager_count", minimum=-1)
        resources_path = f"{step_path}.resources"; resources = _mapping(step.get("resources"), source, resources_path)
        _reject_unknown_fields(resources, OVERLAY_RESOURCE_FIELDS, source, resources_path)
        translated = {}
        if "time" in step:
            time = _string(step["time"], source, f"{step_path}.time")
            if not OVERLAY_TIME.fullmatch(time): _error(source, f"{step_path}.time", "must use M:SS time format")
            translated["title"] = time
        allocations = {}
        for resource in ("food", "gold", "wood", "stone"):
            count = _overlay_integer(resources.get(resource), source, f"{resources_path}.{resource}", minimum=0, range_message="must be a non-negative integer")
            if count > 0: allocations[resource] = count
        _overlay_integer(resources.get("builder"), source, f"{resources_path}.builder", minimum=-1)
        if allocations: translated["vils"] = allocations
        notes = []
        for note_index, note in enumerate(_list(step.get("notes"), source, f"{step_path}.notes")):
            if not isinstance(note, str): _error(source, f"{step_path}.notes[{note_index}]", "must be a string")
            if note: notes.append(render_overlay_note(note))
        if notes: translated["hints"] = notes
        if not allocations and not notes: _error(source, step_path, "has no translatable checks or hints")
        steps.append(translated)
    return {"civ": OVERLAY_CIVILIZATIONS[civilization], "title": _string(overlay.get("name"), source, "name"), "link": _source_link(overlay.get("source"), source, "source"), "steps": steps}


def fetch_overlay_document(url: str) -> Any:
    try:
        parsed = urlsplit(url); port = parsed.port
    except ValueError as exc:
        raise ImportValidationError(f"{url}: invalid aoe4guides build URL: {exc}") from exc
    if parsed.scheme.lower() != "https" or parsed.hostname not in {"aoe4guides.com", "www.aoe4guides.com"} or port is not None or parsed.username is not None or parsed.password is not None:
        raise ImportValidationError(f"{url}: expected an HTTPS aoe4guides.com build URL")
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) == 2 and parts[0] == "builds": build_id = parts[1]
    elif len(parts) == 3 and parts[:2] == ["api", "builds"]: build_id = parts[2]
    else: raise ImportValidationError(f"{url}: expected an aoe4guides.com build URL")
    if not AOE4GUIDES_BUILD_ID.fullmatch(build_id): raise ImportValidationError(f"{url}: invalid aoe4guides build ID")
    endpoint = f"https://aoe4guides.com/api/builds/{build_id}?overlay=true"; request = Request(endpoint, headers={"Accept": "application/json", "User-Agent": "aoe4-macro-trainer"})
    try:
        with build_overlay_opener().open(request, timeout=30) as response:
            body_bytes = response.read(MAX_OVERLAY_RESPONSE_BYTES + 1)
            if len(body_bytes) > MAX_OVERLAY_RESPONSE_BYTES: raise ImportValidationError(f"{url}: aoe4guides response exceeds {MAX_OVERLAY_RESPONSE_BYTES} bytes")
            body = body_bytes.decode("utf-8")
    except HTTPError as exc:
        if exc.code == 404: raise ImportValidationError(f"{url}: aoe4guides build not found (HTTP 404)") from exc
        if exc.code == 429: raise ImportValidationError(f"{url}: aoe4guides rate limit exceeded (HTTP 429)") from exc
        raise ImportValidationError(f"{url}: aoe4guides request failed (HTTP {exc.code})") from exc
    except URLError as exc: raise ImportValidationError(f"{url}: unable to reach aoe4guides: {exc.reason}") from exc
    except UnicodeDecodeError as exc: raise ImportValidationError(f"{url}: aoe4guides returned non-UTF-8 data: {exc}") from exc
    except (HTTPException, IncompleteRead) as exc: raise ImportValidationError(f"{url}: aoe4guides response was interrupted: {exc}") from exc
    try: return json.loads(body)
    except json.JSONDecodeError as exc: raise ImportValidationError(f"{url}: aoe4guides returned invalid JSON: {exc}") from exc
