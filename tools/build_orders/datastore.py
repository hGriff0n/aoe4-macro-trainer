from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

from .model import BuildOrder, Catalog, CheckDescriptor, Step


SCHEMA_VERSION = 1
DATASTORE_FILENAME = "macroTrainerBuildOrders.rlt"
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class DatastoreError(ValueError):
    pass


@dataclass
class _LuaTable:
    keyed: dict[object, object]
    array: list[object]


@dataclass(frozen=True)
class _Token:
    kind: str
    value: object
    offset: int


class _Tokenizer:
    def __init__(self, text: str) -> None:
        self.text = text
        self.offset = 0

    def _skip_space(self) -> None:
        while self.offset < len(self.text):
            if self.text[self.offset].isspace():
                self.offset += 1
                continue
            if self.text.startswith("--", self.offset):
                newline = self.text.find("\n", self.offset + 2)
                self.offset = len(self.text) if newline < 0 else newline + 1
                continue
            break

    def next(self) -> _Token:
        self._skip_space()
        start = self.offset
        if start >= len(self.text):
            return _Token("EOF", None, start)

        character = self.text[start]
        if character in "{}[]=,;":
            self.offset += 1
            return _Token(character, character, start)
        if character in {'"', "'"}:
            return self._string(character)
        if character == "-" or character.isdigit():
            match = re.match(r"-?[0-9]+", self.text[start:])
            if match is not None:
                self.offset += len(match.group(0))
                return _Token("INTEGER", int(match.group(0)), start)
        match = _IDENTIFIER.match(self.text, start)
        if match is not None:
            self.offset = match.end()
            return _Token("IDENTIFIER", match.group(0), start)
        raise DatastoreError(f"unexpected character at offset {start}")

    def _string(self, quote: str) -> _Token:
        start = self.offset
        self.offset += 1
        result: list[str] = []
        escapes = {"n": "\n", "r": "\r", "t": "\t", "\\": "\\", '"': '"', "'": "'"}
        while self.offset < len(self.text):
            character = self.text[self.offset]
            self.offset += 1
            if character == quote:
                return _Token("STRING", "".join(result), start)
            if character == "\\":
                if self.offset >= len(self.text):
                    break
                escaped = self.text[self.offset]
                self.offset += 1
                if escaped not in escapes:
                    raise DatastoreError(
                        f"unsupported string escape at offset {self.offset - 2}"
                    )
                result.append(escapes[escaped])
            else:
                result.append(character)
        raise DatastoreError(f"unterminated string at offset {start}")


class _Parser:
    def __init__(self, text: str) -> None:
        self.tokens = _Tokenizer(text)
        self.current = self.tokens.next()

    def _advance(self) -> _Token:
        previous = self.current
        self.current = self.tokens.next()
        return previous

    def _expect(self, kind: str) -> _Token:
        if self.current.kind != kind:
            raise DatastoreError(
                f"expected {kind} at offset {self.current.offset}, got {self.current.kind}"
            )
        return self._advance()

    def parse(self) -> _LuaTable:
        name = self._expect("IDENTIFIER").value
        if name != "LuaDataStore":
            raise DatastoreError("datastore must assign LuaDataStore")
        self._expect("=")
        value = self._value()
        self._expect("EOF")
        if not isinstance(value, _LuaTable):
            raise DatastoreError("LuaDataStore must be a table")
        return value

    def _value(self) -> object:
        if self.current.kind == "{":
            return self._table()
        if self.current.kind in {"STRING", "INTEGER"}:
            return self._advance().value
        if self.current.kind == "IDENTIFIER":
            value = self._advance().value
            if value == "true":
                return True
            if value == "false":
                return False
            if value == "nil":
                return None
            raise DatastoreError(f"unsupported value {value!r}")
        raise DatastoreError(
            f"expected datastore value at offset {self.current.offset}"
        )

    def _table(self) -> _LuaTable:
        self._expect("{")
        keyed: dict[object, object] = {}
        array: list[object] = []
        while self.current.kind != "}":
            if self.current.kind == "[":
                self._advance()
                if self.current.kind not in {"STRING", "INTEGER"}:
                    raise DatastoreError("bracketed table key must be a string or integer")
                key = self._advance().value
                self._expect("]")
                self._expect("=")
                self._add_key(keyed, key, self._value())
            elif self.current.kind == "IDENTIFIER":
                identifier = self.current
                self._advance()
                if self.current.kind == "=":
                    self._advance()
                    self._add_key(keyed, identifier.value, self._value())
                else:
                    if identifier.value == "true":
                        array.append(True)
                    elif identifier.value == "false":
                        array.append(False)
                    elif identifier.value == "nil":
                        array.append(None)
                    else:
                        raise DatastoreError(
                            f"unsupported array value {identifier.value!r}"
                        )
            else:
                array.append(self._value())
            if self.current.kind in {",", ";"}:
                self._advance()
            elif self.current.kind != "}":
                raise DatastoreError(
                    f"expected table separator at offset {self.current.offset}"
                )
        self._advance()
        return _LuaTable(keyed, array)

    @staticmethod
    def _add_key(target: dict[object, object], key: object, value: object) -> None:
        if key in target:
            raise DatastoreError(f"duplicate table key {key!r}")
        target[key] = value


def _escape(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\r", "\\r")
        .replace("\n", "\\n")
        .replace("\t", "\\t")
    )


def _render_key(key: str) -> str:
    if _IDENTIFIER.fullmatch(key):
        return key
    return f'["{_escape(key)}"]'


def _render_value(value: object, indent: int) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return f'"{_escape(value)}"'
    if value is None:
        return "nil"
    if isinstance(value, list):
        if not value:
            return "{}"
        prefix = "    " * indent
        child = "    " * (indent + 1)
        lines = ["{"]
        lines.extend(f"{child}{_render_value(item, indent + 1)}," for item in value)
        lines.append(f"{prefix}}}")
        return "\n".join(lines)
    if isinstance(value, dict):
        if not value:
            return "{}"
        prefix = "    " * indent
        child = "    " * (indent + 1)
        lines = ["{"]
        for key in sorted(value):
            if not isinstance(key, str):
                raise DatastoreError("datastore table keys must be strings")
            lines.append(
                f"{child}{_render_key(key)} = {_render_value(value[key], indent + 1)},"
            )
        lines.append(f"{prefix}}}")
        return "\n".join(lines)
    raise DatastoreError(f"unsupported datastore value: {value!r}")


def _catalog_data(catalog: Catalog) -> dict[str, object]:
    build_orders: dict[str, object] = {}
    seen: set[str] = set()
    for order in sorted(catalog.build_orders, key=lambda item: item.id):
        if order.id in seen:
            raise DatastoreError(f"duplicate build order id {order.id!r}")
        seen.add(order.id)
        steps = []
        for step_index, step in enumerate(order.steps, start=1):
            checks = []
            for check_index, check in enumerate(step.checks, start=1):
                checks.append(
                    {
                        "id": f"{order.id}:{step_index}:{check_index}",
                        "kind": check.kind,
                        "optional": check.optional,
                        "payload": check.payload,
                        "title": check.title,
                    }
                )
            steps.append(
                {"checks": checks, "title": step.title or f"Step {step_index}"}
            )
        record: dict[str, object] = {
            "civ": order.civ,
            "id": order.id,
            "steps": steps,
            "title": order.title,
        }
        if order.link is not None:
            record["source"] = order.link
        build_orders[order.id] = record
    return {"build_orders": build_orders, "schema_version": SCHEMA_VERSION}


def render_datastore(catalog: Catalog) -> str:
    data = _catalog_data(catalog)
    build_orders = _render_value(data["build_orders"], 1)
    return (
        "LuaDataStore = {\n"
        f"    schema_version = {SCHEMA_VERSION},\n"
        f"    build_orders = {build_orders},\n"
        "}\n"
    )


def _require_table(value: object, path: str) -> _LuaTable:
    if not isinstance(value, _LuaTable):
        raise DatastoreError(f"{path} must be a table")
    return value


def _require_mapping(value: object, path: str) -> dict[object, object]:
    table = _require_table(value, path)
    if table.array:
        raise DatastoreError(f"{path} must use keyed entries")
    return table.keyed


def _require_array(value: object, path: str, *, nonempty: bool = False) -> list[object]:
    table = _require_table(value, path)
    if table.keyed:
        raise DatastoreError(f"{path} must use array entries")
    if nonempty and not table.array:
        raise DatastoreError(f"{path} must not be empty")
    return table.array


def _require_exact_keys(mapping: dict[object, object], required: set[str], optional: set[str], path: str) -> None:
    keys = set(mapping)
    missing = required - keys
    unknown = keys - required - optional
    if missing:
        raise DatastoreError(f"{path} missing {sorted(missing)[0]!r}")
    if unknown:
        raise DatastoreError(f"{path} has unknown key {sorted(unknown, key=str)[0]!r}")


def _require_string(value: object, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise DatastoreError(f"{path} must be a non-empty string")
    return value


def _payload(value: object, path: str) -> object:
    if isinstance(value, (str, int, bool)):
        return value
    table = _require_table(value, path)
    if table.keyed and table.array:
        raise DatastoreError(f"{path} cannot mix keyed and array entries")
    if table.array:
        return [_payload(item, f"{path}[{index}]") for index, item in enumerate(table.array)]
    result: dict[str, object] = {}
    for key, item in table.keyed.items():
        if not isinstance(key, str):
            raise DatastoreError(f"{path} keys must be strings")
        result[key] = _payload(item, f"{path}.{key}")
    return result


def parse_datastore(text: str) -> Catalog:
    root = _require_mapping(_Parser(text).parse(), "LuaDataStore")
    _require_exact_keys(root, {"schema_version", "build_orders"}, set(), "LuaDataStore")
    if root["schema_version"] != SCHEMA_VERSION:
        raise DatastoreError(
            f"unsupported datastore schema version {root['schema_version']!r}"
        )
    raw_orders = _require_mapping(root["build_orders"], "build_orders")
    orders: list[BuildOrder] = []
    for key in sorted(raw_orders, key=str):
        if not isinstance(key, str) or not key:
            raise DatastoreError("build_orders keys must be non-empty strings")
        path = f"build_orders[{key!r}]"
        record = _require_mapping(raw_orders[key], path)
        _require_exact_keys(record, {"id", "civ", "title", "steps"}, {"source"}, path)
        identifier = _require_string(record["id"], f"{path}.id")
        if identifier != key:
            raise DatastoreError(f"{path} record id must match its table key")
        civ = _require_string(record["civ"], f"{path}.civ")
        title = _require_string(record["title"], f"{path}.title")
        source = record.get("source")
        if source is not None:
            source = _require_string(source, f"{path}.source")
        steps: list[Step] = []
        for step_index, raw_step in enumerate(
            _require_array(record["steps"], f"{path}.steps", nonempty=True),
            start=1,
        ):
            step_path = f"{path}.steps[{step_index - 1}]"
            step = _require_mapping(raw_step, step_path)
            _require_exact_keys(step, {"title", "checks"}, set(), step_path)
            step_title = _require_string(step["title"], f"{step_path}.title")
            checks: list[CheckDescriptor] = []
            for check_index, raw_check in enumerate(
                _require_array(step["checks"], f"{step_path}.checks", nonempty=True),
                start=1,
            ):
                check_path = f"{step_path}.checks[{check_index - 1}]"
                check = _require_mapping(raw_check, check_path)
                _require_exact_keys(
                    check,
                    {"id", "kind", "title", "optional", "payload"},
                    set(),
                    check_path,
                )
                check_id = _require_string(check["id"], f"{check_path}.id")
                expected_id = f"{identifier}:{step_index}:{check_index}"
                if check_id != expected_id:
                    raise DatastoreError(
                        f"{check_path}.id must be {expected_id!r}"
                    )
                optional = check["optional"]
                if not isinstance(optional, bool):
                    raise DatastoreError(f"{check_path}.optional must be boolean")
                payload = _payload(check["payload"], f"{check_path}.payload")
                if not isinstance(payload, dict):
                    raise DatastoreError(f"{check_path}.payload must be a keyed table")
                checks.append(
                    CheckDescriptor(
                        _require_string(check["kind"], f"{check_path}.kind"),
                        _require_string(check["title"], f"{check_path}.title"),
                        optional,
                        payload,
                    )
                )
            steps.append(Step(step_title, tuple(checks)))
        orders.append(BuildOrder(identifier, civ, title, tuple(steps), source))
    return Catalog(tuple(orders))


def load_datastore(path: Path) -> Catalog:
    if not path.exists():
        return Catalog(())
    try:
        return parse_datastore(path.read_text(encoding="utf-8-sig"))
    except OSError as exc:
        raise DatastoreError(f"could not read datastore {path}: {exc}") from exc


def write_datastore(path: Path, catalog: Catalog) -> None:
    content = render_datastore(catalog)
    temporary = path.with_name(path.name + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(content, encoding="utf-8", newline="")
        temporary.replace(path)
    except OSError as exc:
        raise DatastoreError(f"could not write datastore {path}: {exc}") from exc
    finally:
        try:
            if temporary.exists():
                temporary.unlink()
        except OSError:
            pass
