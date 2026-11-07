from functools import lru_cache
from http.client import HTTPException
import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request

from aoe4 import web


# `cache/` is gitignored at the repo root
_CACHE_DIR = Path(__file__).resolve().parents[2] / "cache" / "aoe4world"
# Records the upstream commit each cached file was last checked at, and its ETag
_INDEX_FILE = _CACHE_DIR / "index.json"
_MAX_RESPONSE_BYTES = 8 * 1024 * 1024
_CIV_SLUG = re.compile(r"[a-z]+")
_USER_AGENT = "aoe4-macro-trainer"

# aoe4world slugs are our civ ids without underscores, except for these
_KNOWN_CIV_SLUGS = {
    "house_of_lancaster": "lancaster",
    "macedonian_dynasty": "macedonian",
    "sengoku_daimyo": "sengoku",
    "tughlaq_dynasty": "tughlaq",
}


class Aoe4WorldError(ValueError):
    pass


def _civ_slug(civ: str) -> str:
    slug = _KNOWN_CIV_SLUGS.get(civ, civ.replace("_", ""))
    # The slug becomes part of both a cache path and a URL
    if not _CIV_SLUG.fullmatch(slug):
        raise Aoe4WorldError(f"invalid civ={civ!r}")
    return slug


###
# Fetching
###
_NETWORK_ERRORS = (URLError, HTTPException, UnicodeDecodeError, ValueError)


@lru_cache(maxsize=1)
def _latest_commit() -> Optional[str]:
    """The sha of aoe4world/data's newest commit, checked once per run. None when offline"""
    request = Request(
        "https://api.github.com/repos/aoe4world/data/commits/main",
        headers={"Accept": "application/vnd.github.sha", "User-Agent": _USER_AGENT}
    )
    try:
        sha, _ = web.fetch(request, 64)
        return sha.strip()
    except _NETWORK_ERRORS as exc:
        print(f"[Aoe4World] Unable to check for updates, using cached files: {exc!r}")
        return None


def _fetch(name: str, etag: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """Return `(body, etag)`, with a `None` body when the file matches `etag`"""
    headers = {"Accept": "application/json", "User-Agent": _USER_AGENT}
    if etag is not None:
        headers["If-None-Match"] = etag
    request = Request(f"https://raw.githubusercontent.com/aoe4world/data/main/{name}", headers=headers)
    try:
        body, response_headers = web.fetch(request, _MAX_RESPONSE_BYTES)
        return body, response_headers.get("ETag")
    except HTTPError as exc:
        if exc.code == 304:
            return None, etag
        raise Aoe4WorldError(f"{request.full_url}: request failed (HTTP {exc.code})") from exc
    except _NETWORK_ERRORS as exc:
        raise Aoe4WorldError(f"{request.full_url}: unable to fetch from aoe4world: {exc!r}") from exc


###
# Caching
###
def _families(body: str, source: Any) -> List[Dict[str, Any]]:
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise Aoe4WorldError(f"{source}: invalid json: {exc!r}") from exc
    if not isinstance(data, dict) or not isinstance(data.get('data'), list):
        raise Aoe4WorldError(f"{source}: expected a `data` list")
    return data['data']


def _read_index() -> Dict[str, Dict[str, Optional[str]]]:
    if not _INDEX_FILE.exists():
        return {}
    return json.loads(_INDEX_FILE.read_text(encoding="utf-8"))


def _write_index_entry(name: str, commit: Optional[str], etag: Optional[str]):
    index = _read_index()
    index[name] = {'commit': commit, 'etag': etag}
    _INDEX_FILE.write_text(json.dumps(index, indent=2), encoding="utf-8")


# ponytail: raw.githubusercontent caches for ~5 minutes, so a file checked right after an
# upstream commit can still 304 and get marked current until the next commit.
def load_unified(category: str, civ: str) -> List[Dict[str, Any]]:
    """Return the `data` list of aoe4world's `<category>/<civ>-unified.json`

    Cached files are only re-checked after a new upstream commit, and only re-downloaded
    if the file itself changed.
    """
    name = f"{category}/{_civ_slug(civ)}-unified.json"
    path = _CACHE_DIR / name
    entry = _read_index().get(name, {}) if path.exists() else {}

    latest = _latest_commit()
    if path.exists() and (latest is None or entry.get('commit') == latest):
        return _families(path.read_text(encoding="utf-8"), path)

    body, etag = _fetch(name, entry.get('etag'))
    if body is None:
        families = _families(path.read_text(encoding="utf-8"), path)
        print(f"[Aoe4World] Unchanged file={name}")
    else:
        families = _families(body, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        print(f"[Aoe4World] Cached file={path}")
    _write_index_entry(name, latest, etag)
    return families
