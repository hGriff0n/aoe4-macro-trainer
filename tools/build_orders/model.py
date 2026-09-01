from dataclasses import dataclass
import re
import unicodedata


@dataclass(frozen=True)
class CheckDescriptor:
    kind: str
    title: str
    optional: bool
    payload: dict[str, object]


@dataclass(frozen=True)
class Step:
    title: str | None
    checks: tuple[CheckDescriptor, ...]


@dataclass(frozen=True)
class BuildOrder:
    id: str
    civ: str
    title: str
    steps: tuple[Step, ...]
    link: str | None = None


@dataclass(frozen=True)
class Catalog:
    build_orders: tuple[BuildOrder, ...]


def normalize_id(civ: str, title: str) -> str:
    normalized = unicodedata.normalize("NFKD", f"{civ}-{title}")
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")
