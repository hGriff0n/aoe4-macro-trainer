
from argparse import ArgumentTypeError
from dataclasses import dataclass
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
# URL Validation
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


@dataclass
class AoE4Url:
    build_id: str
    orig: str

    @staticmethod
    def parse_arg(url: str) -> AoE4Url:
        try:
            return AoE4Url(build_id=_parse_aoe4guide_url(url), orig=url)
        except Exception as exc:
            raise ArgumentTypeError(f"Invalid URL: {exc}") from exc


###
# Pull/Read Overlay files
###
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


def _fetch_url(url: AoE4Url) -> Dict[str, Any] | None:
    request = Request(
        f"https://aoe4guides.com/api/builds/{url.build_id}?overlay=true",
        headers={"Accept": "application/json", "User-Agent": "aoe4-macro-trainer"}
    )
    try:
        body = _make_aoe4_request(request, url.orig)
    except HTTPError as exc:
        reason = _extract_http_error_reason(exc)
        print(f"{url.orig}: aoe4guides {reason} (HTTP {exc.code})")
        return None
    except URLError as exc:
        print(f"{url.orig}: unable to reach aoe4guides: {exc.reason}")
        return None
    except UnicodeDecodeError as exc:
        print(f"{url.orig}: aoe4guides returned non-UTF-8 data: {exc!r}")
        return None
    except (HTTPException, IncompleteRead) as exc:
        print(f"{url.orig}: aoe4guides response was interrupted: {exc!r}")
        return None

    try:
        overlay = parse_json(body)
        if overlay:
            if "source" in overlay:
                overlay["original_source"] = overlay["source"]
            overlay["source"] = request.full_url
        return overlay
    except ValueError as exc:
        print(f"{url.orig}: aoe4guides returned invalid Json: {exc!r}")
        return None


###
# Translating HTML/WEBP icons to renderable text
###
OVERLAY_NOTE_TOKEN = re.compile(r"@(?P<token>[^@\s/]+/(?P<name>[^@\s/]+))\.webp@")

# The default icon -> text translation is just replace(`-`, `_`) so most cases
# are handled automatically. For the handful that aren't, we consult this table
# Interestingly, there's a "rally" resource
_KNOWN_ICON_TEXT_MAP = {
    "units": {},
    "building": {},
    "resource": {
        "berrybush": "berries",
        "gaiatreeprototypetree": "tree",
    },
    "tech": {
        "survival-techniques": "survival_techniques",
        "safepassage": "safe_passage",
    },
    "civs": {
        "ayy": "ayyubids",
        "eng": "english",
        "hos": "house_of_lancaster",
        "mon": "mongols"
    }
}


def _default_overlay_icon_to_text(icon: str) -> str:
    return icon.replace("-", "_")


def _try_icon_lookup_to_text(token: str, known_special: Dict[str, str]) -> str:
    if token in known_special:
        return known_special[token]
    return _default_overlay_icon_to_text(token)


def _convert_overlay_icon_to_text(token: str, name: str) -> str:
    if token.startswith("unit"):
        return _try_icon_lookup_to_text(name, _KNOWN_ICON_TEXT_MAP["units"])
    if token.startswith("resource"):
        return _try_icon_lookup_to_text(
            name.replace("resource_", ""), _KNOWN_ICON_TEXT_MAP["resource"])
    if token.startswith("building"):
        return _try_icon_lookup_to_text(name, _KNOWN_ICON_TEXT_MAP["building"])
    if token.startswith("civilization_flag"):
        return _try_icon_lookup_to_text(name, _KNOWN_ICON_TEXT_MAP["civs"])
    if token.startswith("technology"):
        return _try_icon_lookup_to_text(name, _KNOWN_ICON_TEXT_MAP["tech"])
    return _default_overlay_icon_to_text(name)


def _render_note(n: str) -> str:
    decoded = html.unescape(n)
    def _readable_token(m: re.Match[str]) -> str:
        label = _convert_overlay_icon_to_text(m.group("token"), m.group("name"))
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


_OVERLAY_TIME = re.compile(r"^(?P<min>\d+):(?P<sec>[0-5]\d)$")
def _compile_step(step: Dict[str, Any]) -> BuildOrderStep | None:
    resources = step.get("resources", {})
    if not isinstance(resources, dict):
        raise ValueError("Overlay.step.resources must be a dict")

    ideal_timing = None
    m = _OVERLAY_TIME.fullmatch(step.get("time", ""))
    if m:
        ideal_timing = int(m.group("min")) * 60 + int(m.group("sec"))

    vils = {}
    for res in ("food", "gold", "wood", "stone"):
        count = resources.get(res, 0)
        if not isinstance(count, int):
            raise ValueError("Overlay.step.resources[_] must be an int")
        if count > 0:
            vils[res] = count

    notes = list(filter(lambda n: n, (_render_note(n) for n in step.get("notes", []))))
    if not (notes or vils):
        return None
    return BuildOrderStep(
        checks=(notes and [HintCheck(hints=notes)] or []) + (
            vils and [VilCheck(resources=vils)] or []),
        ideal_timing=ideal_timing
    )


def _collect_metadata(o: Dict[str, Any]) -> Dict[str, Any]:
    _META_FIELDS = (
        "author", "video", "description", "season",
        "map", "strategy", "source", "link"
    )
    return {k: o[k] for k in _META_FIELDS if k in o and o[k]}


def _compile_overlay(o: Dict[str, Any], link: str | None = None) -> BuildOrder | None:
    bo = o.get("build_order", [])
    if not isinstance(bo, list):
        print("(!) Overlay.build_order must be a list")
        return None

    title = o["name"]
    civ = _internal_civ_id(o["civilization"])
    meta = _collect_metadata(o)
    return BuildOrder(
        id=f"{civ}.{title}".replace("/", "-").replace(":", "-"),
        civ=civ,
        title=title,
        steps=list(filter(lambda x: x, (_compile_step(step) for step in bo))),
        metadata=meta
    )


def _has_required_overlay_keys(o) -> bool:
    if "civilization" not in o:
        print(f"(!) Invalid overlay object: missing `civilization` field")
        return False
    if "name" not in o:
        print(f"(!) Invalid overlay object: missing `name` field")
        return False
    return True


# Technically, this only works on the "overlay" format from the RTSOverlay
def import_build_orders(files: List[Path], urls: List[AoE4Url]) -> List[BuildOrder]:
    overlays = [
        (f, read_json(f)) for f in (files or [])
            if f.suffix.lower() in (".bo", ".json")
    ] + [
        (u, _fetch_url(u)) for u in (urls or [])
    ]

    bos = []
    for src, o in overlays:            
        if o is None:
            print(f"(!) Failed to fetch build order from {src}")
            continue
        if not _has_required_overlay_keys(o):
            continue
        if isinstance(src, AoE4Url):
            o["link"] = src.orig

        bo = _compile_overlay(o)
        if bo is not None:
            bos.append(bo)

    return bos
