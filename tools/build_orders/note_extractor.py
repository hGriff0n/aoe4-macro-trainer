import html
import re
from dataclasses import dataclass

from .identities import IdentityCatalog, IdentityCatalogError, normalize_identity_id


NOTE_TOKEN = re.compile(
    r"@(?P<namespace>[^@\s/]+)/(?P<name>[^@\s/]+)\.webp@"
)
POSSIBLE_NOTE_TOKEN = re.compile(r"@[^@\s]+@?")
BUILDING_IMPERATIVE = re.compile(
    r"^\s*(?:build|add|make)\s+(?:(?:a|an)\s+)?"
    r"(?:(?P<count>\d+)|(?P<ordinal>second))?\s*"
    r"(?P<token>@[^@\s/]+/[^@\s/]+\.webp@)\s*[.!]?\s*$",
    re.IGNORECASE,
)
PRODUCE_IMPERATIVE = re.compile(
    r"^\s*(?:produce|train)\s+(?:(?P<count>\d+)\s+)?"
    r"(?P<token>@[^@\s/]+/[^@\s/]+\.webp@)\s*[.!]?\s*$",
    re.IGNORECASE,
)
HAVE_STATE = re.compile(
    r"^\s*have\s+(?P<count>\d+)\s+"
    r"(?P<token>@[^@\s/]+/[^@\s/]+\.webp@)\s*[.!]?\s*$",
    re.IGNORECASE,
)
RESEARCH_IMPERATIVE = re.compile(
    r"^\s*(?P<queued>queue\s+)?research\s+"
    r"(?P<token>@[^@\s/]+/[^@\s/]+\.webp@)\s*[.!]?\s*$",
    re.IGNORECASE,
)
RALLY_IMPERATIVE = re.compile(
    r"^\s*(?:rally|@resource/rally\.webp@)\s*(?:-|=)?(?:>|→)\s*"
    r"(?P<token>@resource/[^@\s/]+\.webp@)\s*[.!]?\s*$",
    re.IGNORECASE,
)
RESOURCE_THRESHOLD = re.compile(
    r"^\s*(?:at|when|once)(?:\s+you\s+have)?\s+(?P<count>\d+)\s+"
    r"(?P<token>@resource/[^@\s/]+\.webp@)\s*,\s*(?P<action>.+?)\s*$",
    re.IGNORECASE,
)
VILLAGER_ALLOCATION = re.compile(
    r"^\s*(?P<count>\d+)\s+@unit_[^@\s/]+/villager\.webp@\s+on\s+"
    r"(?P<token>@resource/[^@\s/]+\.webp@)\s*[.!]?\s*$",
    re.IGNORECASE,
)
GUARDED_CLAUSE = re.compile(
    r"(?:\b(?:if|unless|against|otherwise|optionally|either|or|and/or|not|never|"
    r"versus|vs|don't|doesn't|can't|cannot|after|before|until)\b|[&/])",
    re.IGNORECASE,
)
RESOURCE_IDS = {
    "food": "food",
    "sheep": "food",
    "deer": "food",
    "berrybush": "food",
    "berries": "food",
    "farm": "food",
    "gold": "gold",
    "stone": "stone",
    "wood": "wood",
    "tree": "wood",
    "gaiatreeprototypetree": "wood",
}
TOKEN_AUTHOR_ID_EXCEPTIONS = {
    "technology_templar/safepassage": "safe_passage",
}


@dataclass(frozen=True)
class ExtractedCheck:
    field: str
    value: dict[str, object]
    rule: str
    start: int
    end: int
    synthetic_step: bool = False
    corroborates: bool = False


@dataclass(frozen=True)
class ExtractionDiagnostic:
    code: str
    start: int
    end: int
    message: str


@dataclass(frozen=True)
class NoteExtraction:
    checks: tuple[ExtractedCheck, ...] = ()
    diagnostics: tuple[ExtractionDiagnostic, ...] = ()


def _author_id(token: re.Match[str]) -> str:
    source_id = f'{token.group("namespace")}/{token.group("name")}'
    if source_id in TOKEN_AUTHOR_ID_EXCEPTIONS:
        return TOKEN_AUTHOR_ID_EXCEPTIONS[source_id]
    name = token.group("name")
    if name.startswith("resource_"):
        name = name.removeprefix("resource_")
    return normalize_identity_id(name)


def _unresolved(
    match: re.Match[str], token: re.Match[str], civ: str, category: str, identities: IdentityCatalog
) -> NoteExtraction | None:
    identifier = _author_id(token)
    try:
        if category == "squad":
            identities.resolve_squad_family(civ, identifier)
        else:
            identities.resolve(civ, category, identifier)
    except IdentityCatalogError as exc:
        start, end = match.span("token")
        return NoteExtraction(
            diagnostics=(
                ExtractionDiagnostic("unresolved_identity", start, end, str(exc)),
            )
        )
    return None


def _resource_id(token: re.Match[str]) -> str | None:
    return RESOURCE_IDS.get(_author_id(token))


def _invalid_count(match: re.Match[str]) -> NoteExtraction | None:
    count = match.groupdict().get("count")
    if count is not None and int(count) <= 0:
        start, end = match.span("count")
        return NoteExtraction(
            diagnostics=(
                ExtractionDiagnostic(
                    "invalid_count", start, end, "count must be a positive integer"
                ),
            )
        )
    return None


def _with_offset(extraction: NoteExtraction, offset: int) -> NoteExtraction:
    return NoteExtraction(
        checks=tuple(
            ExtractedCheck(
                item.field,
                item.value,
                item.rule,
                item.start + offset,
                item.end + offset,
                item.synthetic_step,
                item.corroborates,
            )
            for item in extraction.checks
        ),
        diagnostics=tuple(
            ExtractionDiagnostic(
                item.code,
                item.start + offset,
                item.end + offset,
                item.message,
            )
            for item in extraction.diagnostics
        ),
    )


def extract_note(
    note: str,
    civ: str,
    identities: IdentityCatalog,
    structured_vils: dict[str, int] | None = None,
) -> NoteExtraction:
    decoded = html.unescape(note)
    guard_text = POSSIBLE_NOTE_TOKEN.sub(
        lambda item: " " * len(item.group(0)), decoded
    )
    guard = GUARDED_CLAUSE.search(guard_text)
    if guard is not None:
        return NoteExtraction(
            diagnostics=(
                ExtractionDiagnostic(
                    "guarded_clause",
                    guard.start(),
                    guard.end(),
                    f"guarded wording '{guard.group(0)}' requires review",
                ),
            )
        )

    allocation = VILLAGER_ALLOCATION.fullmatch(decoded)
    if allocation is not None:
        token = NOTE_TOKEN.fullmatch(allocation.group("token"))
        resource = _resource_id(token) if token is not None else None
        count = int(allocation.group("count"))
        if resource is not None and structured_vils is not None:
            if structured_vils.get(resource) == count:
                return NoteExtraction(
                    checks=(
                        ExtractedCheck(
                            "vils",
                            {resource: count},
                            "vils.corroboration.v1",
                            *allocation.span(),
                            corroborates=True,
                        ),
                    )
                )
            return NoteExtraction(
                diagnostics=(
                    ExtractionDiagnostic(
                        "conflicting_vils",
                        allocation.start(),
                        allocation.end(),
                        f"note requests {count} {resource} villagers but structured allocation is "
                        f"{structured_vils.get(resource, 0)}",
                    ),
                )
            )

    threshold = RESOURCE_THRESHOLD.fullmatch(decoded)
    if threshold is not None:
        invalid_count = _invalid_count(threshold)
        if invalid_count is not None:
            return invalid_count
        token = NOTE_TOKEN.fullmatch(threshold.group("token"))
        resource = _resource_id(token) if token is not None else None
        if resource is None:
            start, end = threshold.span("token")
            return NoteExtraction(
                diagnostics=(
                    ExtractionDiagnostic(
                        "unresolved_resource", start, end, "unsupported resource token"
                    ),
                )
            )
        action = extract_note(threshold.group("action"), civ, identities, structured_vils)
        action_offset = threshold.start("action")
        action = _with_offset(action, action_offset)
        if not action.checks or action.diagnostics:
            return NoteExtraction(
                diagnostics=(
                    ExtractionDiagnostic(
                        "unsafe_threshold",
                        threshold.start(),
                        threshold.end(),
                        "resource threshold action was not fully deterministic",
                    ),
                    *action.diagnostics,
                )
            )
        threshold_end = threshold.end("token")
        return NoteExtraction(
            checks=(
                ExtractedCheck(
                    "resources",
                    {resource: int(threshold.group("count"))},
                    "resources.threshold.v1",
                    threshold.start(),
                    threshold_end,
                    True,
                ),
                *action.checks,
            ),
            diagnostics=action.diagnostics,
        )

    match = BUILDING_IMPERATIVE.fullmatch(decoded)
    if match is not None:
        invalid_count = _invalid_count(match)
        if invalid_count is not None:
            return invalid_count
        token = NOTE_TOKEN.fullmatch(match.group("token"))
        if token is not None and token.group("namespace").startswith("building_"):
            unresolved = _unresolved(match, token, civ, "entity", identities)
            if unresolved is not None:
                return unresolved
            identifier = _author_id(token)

            value: dict[str, object] = {"id": identifier}
            if match.group("count") is not None:
                value["count"] = int(match.group("count"))
            return NoteExtraction(
                checks=(
                    ExtractedCheck(
                        "built", value, "built.imperative.v1", *match.span()
                    ),
                )
            )

    match = PRODUCE_IMPERATIVE.fullmatch(decoded)
    if match is not None:
        invalid_count = _invalid_count(match)
        if invalid_count is not None:
            return invalid_count
        token = NOTE_TOKEN.fullmatch(match.group("token"))
        if token is not None and token.group("namespace").startswith("unit_"):
            unresolved = _unresolved(match, token, civ, "squad", identities)
            if unresolved is not None:
                return unresolved
            value = {"id": _author_id(token)}
            if match.group("count") is not None:
                value["count"] = int(match.group("count"))
            return NoteExtraction(
                checks=(
                    ExtractedCheck(
                        "produce", value, "produce.imperative.v1", *match.span()
                    ),
                )
            )

    match = HAVE_STATE.fullmatch(decoded)
    if match is not None:
        invalid_count = _invalid_count(match)
        if invalid_count is not None:
            return invalid_count
        token = NOTE_TOKEN.fullmatch(match.group("token"))
        if token is not None:
            namespace = token.group("namespace")
            if namespace.startswith("unit_"):
                field, category, rule = "units", "squad", "units.have.v1"
            elif namespace.startswith("building_"):
                field, category, rule = "buildings", "entity", "buildings.have.v1"
            else:
                field = category = rule = ""
            if field:
                unresolved = _unresolved(match, token, civ, category, identities)
                if unresolved is not None:
                    return unresolved
                return NoteExtraction(
                    checks=(
                        ExtractedCheck(
                            field,
                            {
                                "id": _author_id(token),
                                "count": int(match.group("count")),
                            },
                            rule,
                            *match.span(),
                        ),
                    )
                )

    match = RESEARCH_IMPERATIVE.fullmatch(decoded)
    if match is not None:
        token = NOTE_TOKEN.fullmatch(match.group("token"))
        if token is not None and token.group("namespace").startswith("technology_"):
            unresolved = _unresolved(match, token, civ, "upgrade", identities)
            if unresolved is not None:
                return unresolved
            value = {"id": _author_id(token)}
            if match.group("queued") is not None:
                value["queued"] = True
            return NoteExtraction(
                checks=(
                    ExtractedCheck(
                        "upgrades", value, "upgrades.research.v1", *match.span()
                    ),
                )
            )

    match = RALLY_IMPERATIVE.fullmatch(decoded)
    if match is not None:
        token = NOTE_TOKEN.fullmatch(match.group("token"))
        resource = _resource_id(token) if token is not None else None
        if resource is not None:
            return NoteExtraction(
                checks=(
                    ExtractedCheck(
                        "rallypoint",
                        {"resource": resource},
                        "rallypoint.resource.v1",
                        *match.span(),
                    ),
                )
            )

    malformed = tuple(
        ExtractionDiagnostic(
            "malformed_token",
            token.start(),
            token.end(),
            "token must use @namespace/name.webp@ syntax",
        )
        for token in POSSIBLE_NOTE_TOKEN.finditer(decoded)
        if NOTE_TOKEN.fullmatch(token.group(0)) is None
        and ("/" in token.group(0) or ".webp" in token.group(0).casefold())
    )
    unused = tuple(
        ExtractionDiagnostic(
            "unused_token", token.start(), token.end(), "token was not used by a safe rule"
        )
        for token in NOTE_TOKEN.finditer(decoded)
    )
    return NoteExtraction(diagnostics=malformed + unused)
