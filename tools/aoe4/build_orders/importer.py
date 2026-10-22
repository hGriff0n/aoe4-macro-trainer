
import html
from http.client import HTTPException, IncompleteRead
from pathlib import Path
import re
from typing import Any, Dict, List
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from aoe4.build_orders.json import parse_json, read_json
from aoe4.build_orders.types import BuildOrder, BuildOrderStep
from aoe4.build_orders.checks.other import HintCheck
from aoe4.build_orders.checks.vils import VilCheck
from aoe4.constants import CIVILIZATION_NAME_TO_ID_MAP


###
# Pull/Read Overlay files
###
def _parse_url_into_parts(url: str) -> List[str]:
    try:
        parsed = urlsplit(url)
    except ValueError as exc:
        raise URLError(
            f"{url}: failed to parse aoe4guides URL: {exc}") from exc

    if (
        parsed.scheme.lower() != "https"
        or parsed.hostname not in {"aoe4guides.com", "www.aoe4guides.com"}
        or parsed.port is not None
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise URLError(
            f"{url}: expected an HTTPS aoe4guides.com build URL")

    return [p for p in parsed.path.split("/") if p]


# Parses the provided aoe4guides url to extract the build_id
def _parse_aoe4guide_url(url: str) -> str:
    parts = _parse_url_into_parts(url)
    if len(parts) == 2 and parts[0] == "builds":
        return parts[1]
    elif len(parts) == 3 and parts[:2] == ["api", "builds"]:
        return parts[2]
    else:
        raise URLError(f"{url}: failed to extract aoe4guides build_id from URL")


class RejectRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _make_aoe4_request(request: Request, url: str):
    MAX_OVERLAY_RESPONSE_BYTES = 2 * 1024 * 1024
    with build_opener(
            RejectRedirectHandler()).open(request, timeout=30) as response:
        body_bytes = response.read(MAX_OVERLAY_RESPONSE_BYTES + 1)
        if len(body_bytes) > MAX_OVERLAY_RESPONSE_BYTES:
            raise ValueError(f"{url}: aoe4guides response exceeds {MAX_OVERLAY_RESPONSE_BYTES} bytes")
        return body_bytes.decode("utf-8")


def _extract_http_error_reason(exc: HTTPError) -> str:
    if exc.code == 404:
        return "build not found"
    elif exc.code == 429:
        return "rate limit exceeded"
    else:
        return "request failed"


def _fetch_url(url: str) -> Dict[str, Any]:
    build_id = _parse_aoe4guide_url(url)
    # TODO: Validate build id against regex (`re.compile(r"^[A-Za-z0-9_-]+$")`)

    request = Request(
        f"https://aoe4guides.com/api/builds/{build_id}?overlay=true",
        headers={"Accept": "application/json", "User-Agent": "aoe4-macro-trainer"}
    )
    try:
        body = _make_aoe4_request(request, url)
    except HTTPError as exc:
        reason = _extract_http_error_reason(exc)
        raise ValueError(f"{url}: aoe4guides {reason} (HTTP {exc.code})") from exc
    except URLError as exc:
        raise ValueError(f"{url}: unable to reach aoe4guides: {exc.reason}") from exc
    except UnicodeDecodeError as exc:
        raise ValueError(f"{url}: aoe4guides returned non-UTF-8 data: {exc}") from exc
    except (HTTPException, IncompleteRead) as exc:
        raise ValueError(f"{url}: aoe4guides response was interrupted: {exc}") from exc

    try:
        overlay = parse_json(body)
        if "source" in overlay:
            overlay["original_source"] = overlay["source"]
        overlay["source"] = request.full_url
        return overlay
    except ValueError as exc:
        raise ValueError(f"{url}: aoe4guides returned invalid Json: {exc}") from exc


###
# Translating HTML/WEBP icons to renderable text
###
# TODO: Probably also need to handle unit tokens but ai didn't find any hardcoded
OVERLAY_NOTE_TOKEN = re.compile(r"@(?P<token>[^@\s/]+/(?P<name>[^@\s/]+))\.webp@")
OVERLAY_FLAG_ICON = re.compile(r"civilization_flag/(?P<civ>[a-z][a-z][a-z])")
OVERLAY_RESOURCE_ICON = re.compile(r"resource/(?P<resource>\w)")
OVERLAY_TECH_ICON = re.compile(r"technology[^/]*/(?P<tech>\w)")

def _try_civ_flag_icon_to_text(token: str) -> str | None:
    m = OVERLAY_FLAG_ICON.match(token)
    if not m:
        return None

    # TODO: Need to find more examples (also move to private global)
    civ = m.group("civ")
    return {
        "ayy": "Ayyubids",
        "eng": "English",
        "hos": "House of Lancaster",
        "mon": "Mongols"
    }.get(civ, civ.capitalize())


def _try_resource_icon_to_text(token: str) -> str | None:
    m = OVERLAY_RESOURCE_ICON.match(token)
    if not m:
        return None

    res = m.group("resource")
    # TODO: Need to find more examples (also move to private global)
    return {
        "berrybush": "Berry Bush",
        "gaiatreeprototypetree": "Tree"
    }.get(res, res.capitalize())


def _try_tech_icon_to_text(token: str) -> str | None:
    m = OVERLAY_TECH_ICON.match(token)
    if not m:
        return None

    tech = m.group("tech")
    # TODO: Need to find more examples (also move to private global)
    return {
        "safepassage": "Safe Passage"
    }.get(tech, tech.capitalize())


def _convert_overlay_icon_to_text(token: str, name: str) -> str:
    civ = _try_civ_flag_icon_to_text(token)
    if civ:
        return civ
    res = _try_resource_icon_to_text(token)
    if res:
        return res
    tech = _try_tech_icon_to_text(token)
    if tech:
        return tech
    return name.replace("-", " ").replace("_", " ").title()


def _render_note(n: str) -> str:
    decoded = html.unescape(n)
    def _readable_token(m: re.Match[str]) -> str:
        name = m.group("name")
        if name.startswith("resource_"):
            name = name.removeprefix("resource_")
        label = _convert_overlay_icon_to_text(m.group("token"), name)
        if (
            m.start() > 0
            and (decoded[m.start() - 1].isalnum()
                 or decoded[m.start() - 1] == "@")
        ):
            label = " " + label
        if m.end() < len(decoded) and decoded[m.end()].isalnum():
            label += " "
        return label
        
    return OVERLAY_NOTE_TOKEN.sub(_readable_token, decoded)


###
# Translating overlays to BuildOrder
###
def _internal_civ_id(civ: str):
    return CIVILIZATION_NAME_TO_ID_MAP.get(civ, civ)


def _compile_step(step: Dict[str, Any]) -> BuildOrderStep:
    resources = step.get("resources", {})
    if not isinstance(resources, dict):
        raise ValueError("Overlay.step.resources must be a dict")

    # TODO: villager_count and population_count and vils -> num building

    ideal_timing = step.get("time")  # TODO: check M:SS format

    vils = {}
    for res in ("food", "gold", "wood", "stone"):
        count = resources.get(res, 0)
        if not isinstance(count, int):
            raise ValueError("Overlay.step.resources[_] must be an int")
        if count > 0:
            vils[res] = count

    notes = [_render_note(n) for n in step.get("notes", [])]
    # TODO: Potentially extract check information (compiler:252)
    checks = _try_extract_from_note(notes)
    ## TODO(pr#18): Add `import_metadata{rule_set, extractions, diagnostics}`
    return BuildOrderStep(
        checks=checks + [HintCheck(hints=notes)] + (
            vils and [VilCheck(resources=vils)] or []),
        ideal_timing=ideal_timing
    )


# TODO: Ai version has accumulating extraction  metadata in final build order
# diagnostic was only set once
def _try_extract_from_note(notes: List[str]) -> List[BuildOrderStep]:
    return []


def _compile_overlay(o: Dict[str, Any]) -> BuildOrder:
    bos = o.get("build_order", [])
    if not isinstance(bos, list):
        raise ValueError("Overlay.build_order must be a list")

    # TODO: Collect metadata (description, author, video, season, map, strategy)
    metadata: Dict[str, Any] = {}

    title = o["name"]
    civ = _internal_civ_id(o["civilization"])
    return BuildOrder(
        id=f"{civ}.{title}",
        civ=civ,
        title=title,
        steps=[_compile_step(s) for s in bos],
        link=o.get("source"),
        metadata=metadata
    )


# Technically, this only works on the "overlay" format from the RTSOverlay
# TODO: Crashes if any errors, should probably report failures and do partial success
def import_build_orders(files: List[Path], urls: List[str]) -> List[BuildOrder]:
    overlays = [
        (f, read_json(f)) for f in files if f.suffix.lower() in (".bo", ".json")
    ] + [
        (u, _fetch_url(u)) for u in urls
    ]

    bos = []
    for src, o in overlays:            
        if o is None:
            print(f"Failed to fetch build order from {src}")
            continue

        bo = _compile_overlay(o)
        if bo is None:
            print(f"Failed to load build order from {src}")
        else:
            bos.append(bo)

    return bos
