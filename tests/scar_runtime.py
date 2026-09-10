"""Small Lua 5.1 subset runtime for executing data-model SCAR in tests.

This intentionally supports only language/library features used by the pure-data
editor model. Engine APIs are outside its scope.
"""

from __future__ import annotations

from dataclasses import dataclass
import math as _math
import re
from typing import Any, Iterable


@dataclass(frozen=True)
class Token:
    kind: str
    value: Any
    offset: int


class LuaSyntaxError(ValueError):
    pass


class LuaTable:
    def __init__(self) -> None:
        self.data: dict[Any, Any] = {}

    def __getitem__(self, key: Any) -> Any:
        return self.data.get(key)

    def __setitem__(self, key: Any, value: Any) -> None:
        if key is None:
            raise TypeError("Lua table index is nil")
        if value is None:
            self.data.pop(key, None)
        else:
            self.data[key] = value

    def __len__(self) -> int:
        index = 1
        while self.data.get(index) is not None:
            index += 1
        return index - 1

    def array(self) -> list[Any]:
        return [self.data[index] for index in range(1, len(self) + 1)]

    def append(self, value: Any) -> None:
        self[len(self) + 1] = value

    def delete_at(self, index: int) -> Any:
        return _table_remove(self, index)


@dataclass(frozen=True)
class LuaResults:
    values: tuple[Any, ...]


class _Return(Exception):
    def __init__(self, values: tuple[Any, ...]) -> None:
        self.values = values


class _Break(Exception):
    pass


def _lex(source: str) -> list[Token]:
    tokens: list[Token] = []
    index = 0
    while index < len(source):
        character = source[index]
        if character.isspace():
            index += 1
            continue
        if source.startswith("--", index):
            newline = source.find("\n", index + 2)
            index = len(source) if newline < 0 else newline + 1
            continue
        if character in {'"', "'"}:
            quote = character
            start = index
            index += 1
            value: list[str] = []
            while index < len(source) and source[index] != quote:
                if source[index] == "\\":
                    index += 1
                    if index >= len(source):
                        raise LuaSyntaxError(f"unterminated string at {start}")
                    escapes = {"n": "\n", "r": "\r", "t": "\t"}
                    value.append(escapes.get(source[index], source[index]))
                else:
                    value.append(source[index])
                index += 1
            if index >= len(source):
                raise LuaSyntaxError(f"unterminated string at {start}")
            index += 1
            tokens.append(Token("string", "".join(value), start))
            continue
        number = re.match(r"(?:\d+\.\d+|\d+)", source[index:])
        if number:
            text = number.group(0)
            tokens.append(
                Token("number", float(text) if "." in text else int(text), index)
            )
            index += len(text)
            continue
        name = re.match(r"[A-Za-z_][A-Za-z0-9_]*", source[index:])
        if name:
            text = name.group(0)
            tokens.append(Token("name", text, index))
            index += len(text)
            continue
        operator = next(
            (item for item in ("...", "~=", "==", "<=", ">=", "..") if source.startswith(item, index)),
            None,
        )
        if operator is not None:
            tokens.append(Token("symbol", operator, index))
            index += len(operator)
            continue
        if character in "+-*/%=<>#(){}[],.;":
            tokens.append(Token("symbol", character, index))
            index += 1
            continue
        raise LuaSyntaxError(f"unexpected character {character!r} at {index}")
    tokens.append(Token("eof", "<eof>", len(source)))
    return tokens


class _Parser:
    _PRECEDENCE = {
        "or": 1,
        "and": 2,
        "==": 3,
        "~=": 3,
        "<": 3,
        "<=": 3,
        ">": 3,
        ">=": 3,
        "..": 4,
        "+": 5,
        "-": 5,
        "*": 6,
        "/": 6,
        "%": 6,
    }

    def __init__(self, source: str) -> None:
        self.tokens = _lex(source)
        self.index = 0

    @property
    def current(self) -> Token:
        return self.tokens[self.index]

    def peek(self, offset: int = 1) -> Token:
        return self.tokens[self.index + offset]

    def advance(self) -> Token:
        token = self.current
        self.index += 1
        return token

    def accept(self, value: str) -> bool:
        if self.current.value == value:
            self.advance()
            return True
        return False

    def expect(self, value: str) -> Token:
        if self.current.value != value:
            raise LuaSyntaxError(
                f"expected {value!r} at {self.current.offset}, got {self.current.value!r}"
            )
        return self.advance()

    def expect_name(self) -> str:
        if self.current.kind != "name":
            raise LuaSyntaxError(
                f"expected name at {self.current.offset}, got {self.current.value!r}"
            )
        return str(self.advance().value)

    def parse(self) -> list[Any]:
        block = self.parse_block({"<eof>"})
        self.expect("<eof>")
        return block

    def parse_block(self, stops: set[str]) -> list[Any]:
        statements = []
        while self.current.value not in stops:
            statements.append(self.parse_statement())
            self.accept(";")
        return statements

    def parse_statement(self) -> Any:
        if self.accept("function"):
            name = self.expect_name()
            self.expect("(")
            parameters: list[str] = []
            if not self.accept(")"):
                parameters.append(self.expect_name())
                while self.accept(","):
                    parameters.append(self.expect_name())
                self.expect(")")
            body = self.parse_block({"end"})
            self.expect("end")
            return ("function", name, parameters, body)
        if self.accept("local"):
            names = [self.expect_name()]
            while self.accept(","):
                names.append(self.expect_name())
            expressions = self.parse_expr_list() if self.accept("=") else []
            return ("local", names, expressions)
        if self.accept("if"):
            branches = []
            condition = self.parse_expression()
            self.expect("then")
            branches.append((condition, self.parse_block({"elseif", "else", "end"})))
            while self.accept("elseif"):
                condition = self.parse_expression()
                self.expect("then")
                branches.append(
                    (condition, self.parse_block({"elseif", "else", "end"}))
                )
            fallback = []
            if self.accept("else"):
                fallback = self.parse_block({"end"})
            self.expect("end")
            return ("if", branches, fallback)
        if self.accept("for"):
            names = [self.expect_name()]
            while self.accept(","):
                names.append(self.expect_name())
            if self.accept("="):
                start = self.parse_expression()
                self.expect(",")
                stop = self.parse_expression()
                step = self.parse_expression() if self.accept(",") else ("literal", 1)
                self.expect("do")
                body = self.parse_block({"end"})
                self.expect("end")
                return ("for_number", names[0], start, stop, step, body)
            self.expect("in")
            expressions = self.parse_expr_list()
            self.expect("do")
            body = self.parse_block({"end"})
            self.expect("end")
            return ("for_each", names, expressions, body)
        if self.accept("while"):
            condition = self.parse_expression()
            self.expect("do")
            body = self.parse_block({"end"})
            self.expect("end")
            return ("while", condition, body)
        if self.accept("return"):
            if self.current.value in {"end", "elseif", "else", "<eof>"}:
                return ("return", [])
            return ("return", self.parse_expr_list())
        if self.accept("break"):
            return ("break",)

        target = self.parse_expression()
        if self.current.value in {"=", ","}:
            targets = [target]
            while self.accept(","):
                targets.append(self.parse_expression())
            self.expect("=")
            return ("assign", targets, self.parse_expr_list())
        if target[0] != "call":
            raise LuaSyntaxError(
                f"expected assignment or call at {self.current.offset}"
            )
        return ("call_statement", target)

    def parse_expr_list(self) -> list[Any]:
        expressions = [self.parse_expression()]
        while self.accept(","):
            expressions.append(self.parse_expression())
        return expressions

    def parse_expression(self, minimum: int = 1) -> Any:
        left = self.parse_unary()
        while True:
            operator = self.current.value
            precedence = self._PRECEDENCE.get(operator, 0)
            if precedence < minimum:
                break
            self.advance()
            next_minimum = precedence if operator == ".." else precedence + 1
            right = self.parse_expression(next_minimum)
            left = ("binary", operator, left, right)
        return left

    def parse_unary(self) -> Any:
        is_unary = (
            self.current.kind == "symbol" and self.current.value in {"-", "#"}
        ) or (self.current.kind == "name" and self.current.value == "not")
        if is_unary:
            operator = self.advance().value
            return ("unary", operator, self.parse_unary())
        return self.parse_postfix()

    def parse_postfix(self) -> Any:
        expression = self.parse_primary()
        while True:
            if self.accept("."):
                expression = ("index", expression, ("literal", self.expect_name()))
            elif self.accept("["):
                key = self.parse_expression()
                self.expect("]")
                expression = ("index", expression, key)
            elif self.accept("("):
                arguments = [] if self.accept(")") else self.parse_expr_list()
                if arguments:
                    self.expect(")")
                expression = ("call", expression, arguments)
            else:
                return expression

    def parse_primary(self) -> Any:
        token = self.current
        if token.kind == "name" and token.value == "function":
            self.advance()
            self.expect("(")
            parameters: list[str] = []
            if not self.accept(")"):
                parameters.append(self.expect_name())
                while self.accept(","):
                    parameters.append(self.expect_name())
                self.expect(")")
            body = self.parse_block({"end"})
            self.expect("end")
            return ("lambda", parameters, body)
        if token.kind in {"string", "number"}:
            self.advance()
            return ("literal", token.value)
        if token.value == "true":
            self.advance()
            return ("literal", True)
        if token.value == "false":
            self.advance()
            return ("literal", False)
        if token.value == "nil":
            self.advance()
            return ("literal", None)
        if token.kind == "name":
            self.advance()
            return ("name", token.value)
        if self.accept("("):
            expression = self.parse_expression()
            self.expect(")")
            return expression
        if self.accept("{"):
            fields = []
            array_index = 1
            while not self.accept("}"):
                if self.accept("["):
                    key = self.parse_expression()
                    self.expect("]")
                    self.expect("=")
                    fields.append((key, self.parse_expression()))
                elif self.current.kind == "name" and self.peek().value == "=":
                    key = ("literal", self.advance().value)
                    self.expect("=")
                    fields.append((key, self.parse_expression()))
                else:
                    fields.append((("literal", array_index), self.parse_expression()))
                    array_index += 1
                if not self.accept(",") and not self.accept(";"):
                    self.expect("}")
                    break
            return ("table", fields)
        raise LuaSyntaxError(
            f"expected expression at {token.offset}, got {token.value!r}"
        )


class _Frame:
    def __init__(self, runtime: "ScarRuntime", top_level: bool = False) -> None:
        self.runtime = runtime
        self.locals: dict[str, Any] = {}
        self.top_level = top_level

    def get(self, name: str) -> Any:
        if name in self.locals:
            return self.locals[name]
        return self.runtime.globals.get(name)

    def set(self, name: str, value: Any, *, local: bool = False) -> None:
        if local or name in self.locals:
            self.locals[name] = value
        else:
            self.runtime.globals[name] = value


class _LuaFunction:
    def __init__(
        self, runtime: "ScarRuntime", parameters: list[str], body: list[Any]
    ) -> None:
        self.runtime = runtime
        self.parameters = parameters
        self.body = body

    def __call__(self, *arguments: Any) -> LuaResults:
        frame = _Frame(self.runtime)
        for index, parameter in enumerate(self.parameters):
            frame.set(
                parameter,
                arguments[index] if index < len(arguments) else None,
                local=True,
            )
        try:
            self.runtime._execute_block(self.body, frame)
        except _Return as result:
            return LuaResults(result.values)
        return LuaResults(())


def _lua_truthy(value: Any) -> bool:
    return value is not None and value is not False


def _first(value: Any) -> Any:
    if isinstance(value, LuaResults):
        return value.values[0] if value.values else None
    return value


def _lua_type(value: Any) -> str:
    if value is None:
        return "nil"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, LuaTable):
        return "table"
    if callable(value):
        return "function"
    return "userdata"


def _pairs(table: LuaTable) -> list[tuple[Any, Any]]:
    return list(table.data.items())


def _ipairs(table: LuaTable) -> list[tuple[int, Any]]:
    return [(index, table[index]) for index in range(1, len(table) + 1)]


def _next(table: LuaTable) -> Any:
    return next(iter(table.data), None)


def _table_insert(table: LuaTable, *arguments: Any) -> None:
    if len(arguments) == 1:
        table[len(table) + 1] = arguments[0]
        return
    if len(arguments) != 2:
        raise TypeError("table.insert expects two or three total arguments")
    position, value = int(arguments[0]), arguments[1]
    for index in range(len(table), position - 1, -1):
        table[index + 1] = table[index]
    table[position] = value


def _table_remove(table: LuaTable, position: Any = None) -> Any:
    index = len(table) if position is None else int(position)
    if index < 1 or index > len(table):
        return None
    value = table[index]
    for current in range(index, len(table)):
        table[current] = table[current + 1]
    table[len(table)] = None
    return value


_LUA_PATTERNS = {
    "^%s+": r"^\s+",
    "%s+$": r"\s+$",
    "[^a-z0-9]+": r"[^a-z0-9]+",
    "^-+": r"^-+",
    "-+$": r"-+$",
    "[/_]+": r"[/_]+",
    "%s+": r"\s+",
}


def _string_gsub(value: str, pattern: str, replacement: str) -> LuaResults:
    translated = _LUA_PATTERNS.get(pattern)
    if translated is None:
        raise NotImplementedError(f"unsupported Lua pattern {pattern!r}")
    result, count = re.subn(translated, replacement, value)
    return LuaResults((result, count))


def _string_gmatch(value: str, pattern: str):
    if pattern == "[^%.]+":
        return iter(value.split("."))
    raise NotImplementedError(f"unsupported Lua pattern {pattern!r}")


class ScarRuntime:
    def __init__(self, source: str) -> None:
        self.globals: dict[str, Any] = {}
        self._install_builtins()
        program = _Parser(source).parse()
        self._execute_block(program, _Frame(self, top_level=True))

    def _install_builtins(self) -> None:
        table_library = LuaTable()
        table_library["insert"] = _table_insert
        table_library["remove"] = _table_remove
        string_library = LuaTable()
        string_library["lower"] = lambda value: value.lower()
        string_library["gsub"] = _string_gsub
        string_library["gmatch"] = _string_gmatch
        math_library = LuaTable()
        math_library["floor"] = _math.floor
        self.globals.update(
            {
                "type": _lua_type,
                "pairs": _pairs,
                "ipairs": _ipairs,
                "next": _next,
                "table": table_library,
                "string": string_library,
                "math": math_library,
            }
        )

    def table(self, value: Any) -> Any:
        return self._luaify(value, {})

    def _luaify(self, value: Any, seen: dict[int, Any]) -> Any:
        if isinstance(value, LuaTable) or value is None or isinstance(
            value, (str, int, float, bool)
        ):
            return value
        identity = id(value)
        if identity in seen:
            return seen[identity]
        if isinstance(value, dict):
            table = LuaTable()
            seen[identity] = table
            for key, item in value.items():
                table[self._luaify(key, seen)] = self._luaify(item, seen)
            return table
        if isinstance(value, (list, tuple)):
            table = LuaTable()
            seen[identity] = table
            for index, item in enumerate(value, start=1):
                table[index] = self._luaify(item, seen)
            return table
        raise TypeError(f"cannot convert {type(value).__name__} to Lua")

    def call(self, name: str, *arguments: Any) -> Any:
        function = self.globals[name]
        converted = [self.table(argument) for argument in arguments]
        result = function(*converted)
        if not isinstance(result, LuaResults):
            return result
        if len(result.values) == 0:
            return None
        if len(result.values) == 1:
            return result.values[0]
        return result.values

    def _evaluate_exprs(self, expressions: list[Any], frame: _Frame) -> list[Any]:
        values: list[Any] = []
        for index, expression in enumerate(expressions):
            value = self._evaluate(expression, frame)
            if index == len(expressions) - 1 and isinstance(value, LuaResults):
                values.extend(value.values)
            else:
                values.append(_first(value))
        return values

    def _execute_block(self, statements: Iterable[Any], frame: _Frame) -> None:
        for statement in statements:
            kind = statement[0]
            if kind == "function":
                _, name, parameters, body = statement
                self.globals[name] = _LuaFunction(self, parameters, body)
            elif kind == "local":
                _, names, expressions = statement
                values = self._evaluate_exprs(expressions, frame)
                for index, name in enumerate(names):
                    frame.set(name, values[index] if index < len(values) else None, local=True)
            elif kind == "assign":
                _, targets, expressions = statement
                values = self._evaluate_exprs(expressions, frame)
                for index, target in enumerate(targets):
                    self._assign(
                        target,
                        values[index] if index < len(values) else None,
                        frame,
                    )
            elif kind == "call_statement":
                self._evaluate(statement[1], frame)
            elif kind == "if":
                _, branches, fallback = statement
                for condition, body in branches:
                    if _lua_truthy(_first(self._evaluate(condition, frame))):
                        self._execute_block(body, frame)
                        break
                else:
                    self._execute_block(fallback, frame)
            elif kind == "for_each":
                _, names, expressions, body = statement
                iterables = self._evaluate_exprs(expressions, frame)
                iterable = iterables[0] if iterables else []
                for item in iterable:
                    values = item if isinstance(item, tuple) else (item,)
                    for index, name in enumerate(names):
                        frame.set(
                            name,
                            values[index] if index < len(values) else None,
                            local=True,
                        )
                    try:
                        self._execute_block(body, frame)
                    except _Break:
                        break
            elif kind == "for_number":
                _, name, start_expr, stop_expr, step_expr, body = statement
                start = int(_first(self._evaluate(start_expr, frame)))
                stop = int(_first(self._evaluate(stop_expr, frame)))
                step = int(_first(self._evaluate(step_expr, frame)))
                final = stop + (1 if step > 0 else -1)
                for value in range(start, final, step):
                    frame.set(name, value, local=True)
                    try:
                        self._execute_block(body, frame)
                    except _Break:
                        break
            elif kind == "while":
                _, condition, body = statement
                while _lua_truthy(_first(self._evaluate(condition, frame))):
                    try:
                        self._execute_block(body, frame)
                    except _Break:
                        break
            elif kind == "return":
                raise _Return(tuple(self._evaluate_exprs(statement[1], frame)))
            elif kind == "break":
                raise _Break()
            else:
                raise AssertionError(f"unknown statement {kind}")

    def _assign(self, target: Any, value: Any, frame: _Frame) -> None:
        if target[0] == "name":
            frame.set(target[1], value)
            return
        if target[0] == "index":
            table = _first(self._evaluate(target[1], frame))
            key = _first(self._evaluate(target[2], frame))
            table[key] = value
            return
        raise LuaSyntaxError("invalid assignment target")

    def _evaluate(self, expression: Any, frame: _Frame) -> Any:
        kind = expression[0]
        if kind == "literal":
            return expression[1]
        if kind == "name":
            return frame.get(expression[1])
        if kind == "table":
            table = LuaTable()
            for key_expr, value_expr in expression[1]:
                key = _first(self._evaluate(key_expr, frame))
                value = _first(self._evaluate(value_expr, frame))
                table[key] = value
            return table
        if kind == "lambda":
            _, parameters, body = expression
            return _LuaFunction(self, parameters, body)
        if kind == "index":
            table = _first(self._evaluate(expression[1], frame))
            key = _first(self._evaluate(expression[2], frame))
            return table[key]
        if kind == "call":
            function = _first(self._evaluate(expression[1], frame))
            arguments = self._evaluate_exprs(expression[2], frame)
            return function(*arguments)
        if kind == "unary":
            operator = expression[1]
            value = _first(self._evaluate(expression[2], frame))
            if operator == "not":
                return not _lua_truthy(value)
            if operator == "-":
                return -value
            if operator == "#":
                return len(value)
        if kind == "binary":
            operator = expression[1]
            left = _first(self._evaluate(expression[2], frame))
            if operator == "and":
                return _first(self._evaluate(expression[3], frame)) if _lua_truthy(left) else left
            if operator == "or":
                return left if _lua_truthy(left) else _first(self._evaluate(expression[3], frame))
            right = _first(self._evaluate(expression[3], frame))
            if operator == "==":
                return left == right
            if operator == "~=":
                return left != right
            if operator == "<":
                return left < right
            if operator == "<=":
                return left <= right
            if operator == ">":
                return left > right
            if operator == ">=":
                return left >= right
            if operator == "+":
                return left + right
            if operator == "-":
                return left - right
            if operator == "*":
                return left * right
            if operator == "/":
                return left / right
            if operator == "%":
                return left % right
            if operator == "..":
                return f"{left}{right}"
        raise AssertionError(f"unknown expression {kind}")
