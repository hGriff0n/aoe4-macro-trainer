# General Programming Style Guide

These rules are a base contract for code in any language. The language-specific guides add rules on top of them.

## 1. Write less code

- **Use an existing library before writing your own.** Don't hand-write a parser, serializer, retry loop or path resolver when the stdlib or a well-known package already does the job. A few lines of glue around a dependency beat hundreds of lines of custom code that need their own tests.
- **Don't build a feature you can't explain.** If you can't say in one sentence who uses a feature and why, leave it out and write the open question down as a TODO. A feature is easy to add once its use case is clear and expensive to keep while it isn't.
- **Don't guard against cases that don't happen in practice.** Skip things like atomic temp-file writes, collision detection, duplicate-argument rejection and refusing to overwrite output unless a real failure calls for them. If you think one might matter later, leave a `TODO` instead of the code.
- **Delete what's finished or dead.** Once a planning doc, spec or task report has been carried out, delete it. Remove unused code too. Commented-out code is only acceptable as a short block kept on purpose, with a `TODO` that says why.
- **Compose small named helpers through a higher-order function** rather than repeating logic inline:
  ```lua
  return check(player, want.a, CountA)
     and check(player, want.b, CountB)
  ```

## 2. Structure

- **Give each variant of a concept its own self-contained module.** When a system has several kinds of something (commands, message types, rules, checks), put everything about one kind in one place: parsing, serialization, validation, display text and behavior.
- **Register variants in a central registry and look them up by key.** Shared code should never branch on the kind. Adding a variant should take one new file and one registration line.
- **Dispatch through data, not `if/elif` chains on a type or name.** Use a registry, a lookup table, or the framework's own dispatch hook (for example, binding a handler to each CLI subcommand). Unknown inputs fall through to a reasonable default, such as the title-cased raw name.
- **Keep the same shape across languages.** When the same concept exists on both sides of a boundary, such as a producer and a consumer or a compiler and a runtime, structure both sides the same way. Someone who knows one side should be able to find their way around the other.
- **Split files by concern:** entry point and lifecycle, the core engine, the variants, shared helpers, and platform-specific code. Avoid god files and god state objects.
- **Keep platform-specific code behind a small module** that raises its own error type. Callers convert that error into one of their own.
- **Translate foreign formats straight into the domain model.** An importer should build domain objects directly. Don't convert to another serialized format and then run the normal compiler over that.
- **Keep reading separate from building.** One step does I/O and returns raw data (`read_x(path) -> dict`). Another turns raw data into domain objects (`thing_from_dict(data)`). Formats that share a shape then share the builder, and adding a format only takes a new reader.
- **Put descriptive pass-through attributes in an open metadata map** (author, source link, description and so on). Don't add a typed field for each one. Promote an attribute to a real field only once code depends on it.
- **Build lookup tables as a pattern, a small map of known exceptions, and a generic fallback.** Don't try to list every case up front. Unknown inputs fall through to a reasonable default, such as the title-cased raw name.
- **Keep constants with the code that uses them.** A constant used by one function can be a local inside it. A table used across the domain goes in the shared constants module. Don't define either at the top of an unrelated module.
- **Use guard clauses with early `return`** rather than nesting.

## 3. Be lenient by default

- **Validate the shape that matters and use defaults for the rest.** Check container types and required fields. Read optional fields with defaults. Don't thread location arguments through every function just to produce detailed error paths. One plain message naming the field is enough.
- **Validate strictly at real trust boundaries**, such as user input that becomes a filesystem path, a shell argument or a query. Being lenient doesn't mean being unsafe.
  - For network fetches, keep a host allowlist, require HTTPS, reject redirects, and set a size cap and a timeout. Build the request URL yourself from a validated id instead of fetching whatever URL the user typed.
  - Being lenient applies to the *content* that comes back, so don't reject unknown fields or enforce value ranges you don't use.
- **Parse at the edge into a typed value.** Turn raw input such as a URL string into a small value object (`{parsed_id, original}`) as soon as it arrives, for example in the CLI argument parser. Then a bad input fails before any work starts, and the rest of the code never sees the raw string.
- **Prefer partial success for batches.** When a batch of inputs is processed, one failure shouldn't lose the rest. If the code currently aborts on the first error, leave a TODO saying so.

## 4. TODOs and open questions

- **Leave explicit `TODO`s for known gaps that aren't hit today.** Write them in the voice of a decision that is still open, and include the reasoning:
  ```
  TODO: This overwrites on collision. Do I want this?
  The alternative was to raise, which seems excessive.
  ```
- **Stub a hook you know you'll need with a no-op that has a TODO.** Don't build it out speculatively.
- **When a hook needs input that isn't known yet, leave the stub and say what's missing.** Don't invent the data.
- **Keep TODOs specific and current.** Delete a TODO once the question is answered. Reword vague ones into concrete statements, for example "validate ids" becomes "validate that the owner can actually build these ids".

## 4a. Commands that change state

- **Give every command that writes state a `--dry-run` flag.** In dry-run mode, print what would happen with one marker per item:
  ```
  (+) Added new item `a`
  (*) Overwriting/updating item `b`
  (-) Deleted item `c`
  (?) No item found with id=d
  ```
- **Accept a list wherever a command takes inputs** (`--files a b`, `--urls x y`), rather than a mutually exclusive single `--file` or `--url`.
- **When an id the user asked for doesn't exist, log it and move on.** Don't crash on the lookup.

## 4b. Formatting

- **Write one statement per line.** Never pack lines with `if x: raise ...` or `a; b`. Dense one-liners hide branches from readers and from diffs.
- **When a condition has several clauses, put one clause per line**, inside parentheses, with each continuation line starting with the operator (`or`, `and`).
- **Break a long function into small named steps**, for example parse URL → extract id → make request → map errors → decode. Each step should be readable on its own.
- **Group sections of a longer module under short banner comments** (for example "URL validation", "Fetching", "Translation").

## 5. Comments

- **Comment why, not what.** Good comments record platform quirks, ordering constraints, workarounds and non-obvious decisions. For example: "Can't do X here because Y isn't initialized until the next tick."
- **Document an interface where it's declared.** Give a one-line description of each method or slot. Don't repeat that description at every implementation.
- **Don't write comments that narrate the code.**

## 6. Naming

- **Use a consistent prefix or namespace for each module's public API** in languages without real namespaces.
- **Mark module-private names with the language's convention**, such as a leading underscore or `local`.
- **Give magic numbers and opaque ids a named constant** at the top of the file.

## 7. Logging

- **Prefix each log line with a tag naming the component, and put identifiers in `key=value` form:**
  `[Component] Registered item=<id>`
- **Log every skip, fallback and lifecycle transition**: registered, activated, deactivated, skipped as invalid, missing handler. This matters most when logs are your only debugger.
- **Remove noisy per-iteration debug logging once a feature works.** Keep the lifecycle logs.

## 8. Tests

- **Logic should have tests**, such as parsing, serialization round-trips, registries and data transforms. Keep them small and focused, with one round-trip test per variant.
- **At a minimum, run every changed code path once before calling it done.** A single smoke run of each CLI command catches most of the slips that lean code otherwise ships with: wrong call signatures, missing shared arguments, and broken defaults.
- **Keep the safety checks when cutting back a test suite.** The test you can drop is "rejects field it doesn't care about". The tests to keep are "can't fetch from a disallowed host" and "round-trips correctly".
- **Don't write tests that check source file contents** (for example, grepping for a function name). They don't verify behavior and they break on every refactor.

## 9. Process

- **Make it work end to end before polishing it.** Get one variant fully working, then roll the same pattern out to the others.
- **Keep commits small and clearly named.** Make cleanup, such as removing debug logging or dead files, its own commit.
