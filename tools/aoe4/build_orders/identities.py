from functools import lru_cache
from typing import Any, Dict, List, Optional

from aoe4 import aoe4world
from aoe4.constants import TECHNOLOGIES, UNITS, UPGRADES


# Author id -> the game ids (attribNames) it matches
AuthorIds = Dict[str, List[str]]

# Categories that read more than their own aoe4world folder. The upgrades check
# covers both technologies and unit upgrades
_CATEGORY_SOURCES = {
    UPGRADES: (TECHNOLOGIES, UPGRADES),
}


def _author_id(aoe4world_id: str) -> str:
    return aoe4world_id.replace("-", "_")


def author_ids_from_families(category: str, families: List[Dict[str, Any]]) -> AuthorIds:
    """Build the author id table from aoe4world's unified `data` list

    A family id (`spearman`, `culture_wing`) maps to every game id in the family so checks
    match it in any age. Variation ids (`culture_wing_2`) pick out a single game id,
    except for units where they're aliases of the family.
    """
    ids: AuthorIds = {}
    for family in families:
        variations = [v for v in family.get('variations', []) if v.get('attribName')]
        game_ids = sorted({v['attribName'] for v in variations})
        if not game_ids:
            continue
        ids[_author_id(family['id'])] = game_ids
        for v in variations:
            # A variation id can equal its family id (`upgrade-king-3`), the family wins
            ids.setdefault(
                _author_id(v['id']),
                game_ids if category == UNITS else [v['attribName']])
    return ids


@lru_cache(maxsize=None)
def _civ_author_ids(civ: str, category: str) -> Optional[AuthorIds]:
    ids: AuthorIds = {}
    for source in _CATEGORY_SOURCES.get(category, (category,)):
        try:
            families = aoe4world.load_unified(source, civ)
        except aoe4world.Aoe4WorldError as e:
            print(f"[Identities] Passing ids through unresolved civ={civ} category={category}: {e}")
            return None
        ids |= author_ids_from_families(source, families)
    return ids


def resolve_ids(ids: Optional[AuthorIds], category: str, author_ids: List[str]) -> List[str]:
    """Translate author ids into game ids. Game ids are accepted as-is"""
    if ids is None:
        return list(author_ids)

    game_ids = []
    for author_id in author_ids:
        if author_id in ids:
            game_ids.extend(ids[author_id])
        elif any(author_id in known for known in ids.values()):
            game_ids.append(author_id)
        else:
            raise ValueError(f"unknown {category} id={author_id}")
    return game_ids


def _reverse_one(ids: AuthorIds, game_ids: List[str]) -> Optional[str]:
    matches = [a for a, known in ids.items() if known == sorted(game_ids)]
    return min(matches, key=lambda a: (len(a), a), default=None)


def reverse_ids(ids: Optional[AuthorIds], game_ids: List[str]) -> List[str]:
    """Inverse of `resolve_ids`, preferring one author id that covers every game id"""
    ids = ids or {}
    whole = _reverse_one(ids, game_ids)
    if whole is not None:
        return [whole]
    # TODO: A `oneof` mixing a family with other ids comes back as the family's variations.
    # Grouping subsets back into families seems excessive until a build order needs it.
    return [_reverse_one(ids, [game_id]) or game_id for game_id in game_ids]


def resolve(civ: str, category: str, author_ids: List[str]) -> List[str]:
    try:
        return resolve_ids(_civ_author_ids(civ, category), category, author_ids)
    except ValueError as e:
        raise ValueError(f"{e} for civ={civ}") from e


def reverse(civ: str, category: str, game_ids: List[str]) -> List[str]:
    return reverse_ids(_civ_author_ids(civ, category), game_ids)
