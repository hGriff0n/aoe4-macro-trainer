# Python Style Guide

This guide builds on `styleguide-general.md`.

## Layout

- **Put code in libraries and keep script entry points thin.** Put the majority of logic in a reusable package split by domain, with separate modules for types, each I/O format, variants, constants and OS-specific code. Keep the CLI in one small script.
- **Name each I/O module after the format it handles** (`yaml.py`, `json_store.py`). Each one exposes a `load_x(path)` / `save_x(obj, path)` pair.
- **Order imports as stdlib, then third-party, then local**, with a blank line between groups.
- **A side-effect import is fine when that import is the registration point.** Alias it to `_` and add a comment saying why it's there:
  ```python
  import mypkg.plugins.register_all as _  # plugins registered to singleton
  ```
- **In longer modules, separate sections with `###` banner comments:**
  ```python
  ###
  # URL Validation
  ###
  ```
- **Use `import x` for imports by default.** Prefer using `import x`, especially when `x` helps with self-documenting code. Use `from x import y` if the package only uses 1-3 elements. Use `import x as y` when x is either very long, clashes with other imports, or y is an understood shorthand. Only use `from x import *` for constants-only modules

## Types and data

- **Use `@dataclass` for records**, with `field(default_factory=...)` for mutable defaults. Records can be mutable when loaders build them up step by step.
- **Use an ABC with `@abstractmethod` for interfaces.** Give every abstract method a one-line docstring and a `pass` body.
- **Add `from __future__ import annotations` to files whose classes refer to themselves** (`-> MyClass`).
- **Define type aliases for the shapes that cross boundaries**, for example `WireRepr = Dict[str, Any]`.
- **Use `typing` generics (`List`, `Dict`, `Optional`) in new code.** Don't rewrite existing `X | None` annotations just to switch styles.
- **Small helper pairs that are inverses of each other should say so in their docstrings** ("Inverse of `parse_ids`").

## Registry pattern

Each variant is one class, and that class owns all of its conversions:

```python
@register_factory
@dataclass
class FooItem(ItemBase):
    values: Dict[str, int] = field(default_factory=dict)

    @staticmethod
    def key() -> str:
        return "foo"

    def to_source(self) -> SourceRepr: ...

    @staticmethod
    def from_source(data: SourceRepr) -> List[FooItem]: ...
```

- **Put code that every variant shares in a class decorator or base class**, for example the envelope fields, list normalization and checking the kind on the way in. Don't copy it into each class.
- **A registry singleton does its one-time setup in `__new__`**, because `__init__` runs on every call.
- **One source entry may expand to several runtime items.** Let `from_source` return a list, and have the writer merge them back.
- **Name private helpers inside a variant class with an underscore**, for example `_instance_from_source` for parsing one list element.

## CLI

- **Use argparse subparsers with `set_defaults(func=handler)`, then call `args.func(args, ctx)`.** Never switch on `args.command`.
- **Every handler has the same signature**, `(args, shared_context)`. `main()` does the setup they all share once and then dispatches.
- **Add an argument shared by every subcommand in a loop** over the subparsers.
- **Keep each handler a few lines long.** For example, write `store.pop(id, None)` rather than validating that the id exists and erroring if it doesn't.
- **Parse structured arguments with `type=`.** A small dataclass holds the parsed value next to the original, and its `parse_arg` method raises `argparse.ArgumentTypeError`:
  ```python
  @dataclass
  class SourceUrl:
      build_id: str
      orig: str

      @staticmethod
      def parse_arg(url: str) -> SourceUrl:
          try:
              return SourceUrl(build_id=_extract_id(url), orig=url)
          except Exception as exc:
              raise ArgumentTypeError(f'Invalid URL: {exc}') from exc
  ```
- **Mutating subcommands take `--dry_run` (`action="store_true"`).** Put the dry-run branching in one shared helper, not in every handler.
- **Have the save function report what it wrote** (`Saved N items to <path>`), so callers don't each print it.

## Errors

- **Prefer returning errors/None from layer boundaries instead of throwing:** This enables the calling code to treat the error as it deisres: throw an exception, log, etc.
  ```python
  def _load_one(f: Path) -> Optional[Thing]:
      try:
          return loader.load(f)
      except Exception as e:
          print(f'Error loading {f}: {e!r}')
          return None
  ```
- **Wrap lower-level errors at the layer boundary**, for example turning an OS-module error into your domain error.
- **Catch specific low-level exceptions at the I/O call** (`HTTPError`, `URLError`, `UnicodeDecodeError`) and re-raise them as domain error with context, using `from exc`. Put status-code-to-message mapping in a small helper, not a chain of `raise` statements.

## Idioms

- **Read optional fields with `.get('key', default)`.** Check the type only for the top-level container shape.
- **Build output with dict merge** (`base | extra`). Add optional keys only when they are set, using `if x is not None: data['x'] = x`.
- **Prefer comprehensions and `map`/filter** over append loops when the result is a single expression:
  ```python
  return [x for x in map(_load_one, paths) if x is not None]
  ```
- **Use `pathlib` for all path work** (`rglob`, `suffix`, `stem`, `mkdir(parents=True, exist_ok=True)`), and always open files with `encoding='utf-8'`.
- **Prefer double quotes for strings and single quotes for keys.** Dictionary keys should use single quotes to help distinquish from string values
- **Don't pass long keyword-only parameter lists through every helper.** If several functions need the same context, the logic probably belongs on an object.

## Pitfalls that lean, untested code ships with

Check for these before calling code done:

- `x in (".json")` is a substring test on a string. A one-element tuple needs a trailing comma: `(".json",)`.
- A trailing comma after a dataclass field default (`field(default_factory=list),`) turns the default into a tuple.
- An argument added "to every subcommand" in a loop has to include subcommands added later.

## Tests

- **Use pytest.** Write one round-trip test per variant (source → wire → source) and one test for registry lookup.
- **Use small inline fixtures.** Don't build fixture directories for data that fits in a few lines.
