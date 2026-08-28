import argparse
import json
import os
import sqlite3
import tempfile
from pathlib import Path
from typing import Iterable, Mapping

from tools.build_orders.identities import DEFAULT_IDENTITY_CATALOG, IDENTITY_ID, IdentityCatalog


CATEGORY_MAP = {
    "buildings": "entity",
    "units": "squad",
    "technologies": "upgrade",
}

SOURCE_CIVILIZATIONS = {
    "ab": "abbasid", "ay": "ayyubids", "by": "byzantines",
    "ch": "chinese", "de": "delhi", "en": "english", "fr": "french",
    "hl": "house_of_lancaster", "horde": "golden_horde", "hr": "hre",
    "ja": "japanese", "je": "jeanne_darc", "jin": "jin_dynasty",
    "kt": "templar", "ma": "malians", "macedonian": "macedonian_dynasty",
    "mo": "mongols", "od": "order_of_the_dragon", "ot": "ottomans",
    "ru": "rus", "daimyo": "sengoku_daimyo", "tughlaq": "tughlaq_dynasty",
    "zx": "zhu_xi",
    "aybCmp": None, "crdCmp": None, "rogue": None, "song_cmp": None,
}

# These playable records have upstream translation placeholders instead of usable
# official IDs. Keep them unavailable until upstream provides real names.
PLAYABLE_TRANSLATION_SENTINEL_PBG_IDS = {
    9001600: "missing upstream display name",
    9003200: "missing upstream display name",
    9003576: "missing upstream display name",
    9003662: "missing upstream display name",
    9004099: "missing upstream display name",
}
TRANSLATION_SENTINEL_PREFIX = "-translation-not-found-"


class IdentityGenerationError(ValueError):
    pass


def _require_string(details: Mapping[str, object], field: str) -> str:
    value = details.get(field)
    if not isinstance(value, str) or not value:
        raise IdentityGenerationError(f"malformed relevant record: non-empty {field} is required")
    return value


def _require_row_string(row: Mapping[str, object], field: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value:
        raise IdentityGenerationError(f"malformed relevant record: non-empty {field} is required")
    return value


def _normalize_official_id(value: str, field: str) -> str:
    normalized = value.replace("-", "_")
    if not IDENTITY_ID.fullmatch(normalized):
        raise IdentityGenerationError(f"malformed relevant record: {field} is not a normalized official ID")
    return normalized


def _parse_details(row: Mapping[str, object]) -> Mapping[str, object]:
    details_json = row.get("details_json")
    if not isinstance(details_json, str):
        raise IdentityGenerationError("malformed relevant record: details_json must be a string")
    try:
        details = json.loads(details_json)
    except json.JSONDecodeError as exc:
        raise IdentityGenerationError(f"malformed relevant record: invalid details_json: {exc}") from exc
    if not isinstance(details, dict):
        raise IdentityGenerationError("malformed relevant record: details_json must contain an object")
    return details


def _insert_identity(
    output: dict[str, str],
    civilization: str,
    category: str,
    identifier: str,
    attrib_name: str,
) -> None:
    existing = output.get(identifier)
    if existing is not None and existing != attrib_name:
        raise IdentityGenerationError(
            f"conflicting identity for {civilization}.{category}.{identifier}: "
            f"{existing!r} and {attrib_name!r}"
        )
    output[identifier] = attrib_name


def generate_identity_document(rows: Iterable[Mapping[str, object]]) -> dict[str, object]:
    grouped_identities: dict[tuple[str, str, str], dict[str, str]] = {}
    for row in rows:
        category = row.get("category")
        if category not in CATEGORY_MAP:
            raise IdentityGenerationError(f"malformed relevant record: unsupported category {category!r}")
        details = _parse_details(row)
        base_id = _require_string(details, "baseId")
        attrib_name = _require_string(details, "attribName")
        item_id = _require_row_string(row, "item_id")
        civs = details.get("civs")
        if not isinstance(civs, list) or not civs or any(not isinstance(civ, str) or not civ for civ in civs):
            raise IdentityGenerationError("malformed relevant record: non-empty civs are required")

        identity_category = CATEGORY_MAP[category]
        included_civilizations: list[str] = []
        for source_civ in civs:
            if source_civ not in SOURCE_CIVILIZATIONS:
                raise IdentityGenerationError(f"unknown source civilization '{source_civ}'")
            civilization = SOURCE_CIVILIZATIONS[source_civ]
            if civilization is not None:
                included_civilizations.append(civilization)

        if not included_civilizations:
            continue
        if base_id.startswith(TRANSLATION_SENTINEL_PREFIX):
            pbgid = row.get("pbgid")
            if pbgid not in PLAYABLE_TRANSLATION_SENTINEL_PBG_IDS:
                raise IdentityGenerationError(f"unknown translation-sentinel PBG ID {pbgid!r}")
            continue

        normalized_base_id = _normalize_official_id(base_id, "baseId")
        normalized_item_id = _normalize_official_id(item_id, "item_id")
        for civilization in included_civilizations:
            identities = grouped_identities.setdefault(
                (civilization, identity_category, normalized_base_id),
                {},
            )
            existing = identities.get(normalized_item_id)
            if existing is not None and existing != attrib_name:
                raise IdentityGenerationError(
                    f"conflicting identity for {civilization}.{identity_category}.{normalized_item_id}: "
                    f"{existing!r} and {attrib_name!r}"
                )
            identities[normalized_item_id] = attrib_name

    civilizations: dict[str, dict[str, dict[str, str]]] = {}
    for (civilization, category, base_id), items in sorted(grouped_identities.items()):
        output = civilizations.setdefault(civilization, {}).setdefault(category, {})
        canonical_ids = set(items.values())
        if len(canonical_ids) == 1:
            _insert_identity(output, civilization, category, base_id, next(iter(canonical_ids)))
            continue
        for item_id, attrib_name in sorted(items.items()):
            _insert_identity(output, civilization, category, item_id, attrib_name)

    return {
        "schema_version": 1,
        "source": "official_base_data",
        "civilizations": civilizations,
    }


def read_official_rows(database: Path) -> list[dict[str, object]]:
    uri = f"file:{database.resolve().as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    try:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT category, item_id, base_id, attrib_name, pbgid, details_json
            FROM base_data_entries
            WHERE source_set = 'official_base_data'
              AND category IN ('buildings', 'units', 'technologies')
            ORDER BY category, base_id, attrib_name, details_json
            """
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def write_identity_document(document: Mapping[str, object], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(document, indent=2, sort_keys=True) + "\n"
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=output.parent,
            prefix=f".{output.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(content)
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, output)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_IDENTITY_CATALOG)
    args = parser.parse_args(argv)
    document = generate_identity_document(read_official_rows(args.database))
    write_identity_document(document, args.output)
    IdentityCatalog.load(args.output)
    return 0
