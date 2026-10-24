# SCAR Style Guide

This guide builds on `styleguide-general.md`. The Lua sections apply to any Lua codebase. The SCAR section adds rules for Age of Empires IV scripting.

## Age of Empires IV Idioms

- **Callbacks passed to `Rule_Add` and `Rule_AddGlobalEvent` must be named global functions.** Anonymous closures are rejected.
- **`UI_CreateCommand` takes the global function's name as a string.** Keep these names in a table.
- **Don't pause the sim on the same tick as showing UI**, or the UI won't load. Schedule a one-shot rule that calls `Rule_RemoveMe()`.
- **PBG wrappers are opaque.** Compare their fields structurally, never with `==`, and cache resolved PBGs by id.
- **Always pass `""` as the text-datastore path.**
- **Use `print` logs from the SCAR log as the debugger.** Read the log before guessing.
- **Build every displayed string through a localization helper layer** (concatenation, joining, wrapping raw text in a loc string). Never concatenate a raw Lua string into UI text. Store locdb and format ids as named constants.
- **When a screen name is missing, fall back to the raw id as text and log it.** Never error on a missing name.
- **Use a dev-time import wrapper that can load from an absolute path for hot reload** during development, and switch it back to plain `import` for builds.
- **Keep the wincondition entry file thin.** It wires each submodule's `OnInit`, `OnStart` and `Stop` together and contains no logic of its own.
- **Don't write tests that read `.scar` source bytes.** Verify behavior in-game.

## File layout

Split every file into these banner-delimited sections, in this order. A section can be empty, but keep its banner.

```lua
-----------------------------------------------------------------------
-- Imports
-----------------------------------------------------------------------
-----------------------------------------------------------------------
-- Data
-----------------------------------------------------------------------
-----------------------------------------------------------------------
-- Private Implementation
-----------------------------------------------------------------------
-----------------------------------------------------------------------
-- Public Interface
-----------------------------------------------------------------------
-----------------------------------------------------------------------
-- Public Implementation
-----------------------------------------------------------------------
```

- **Imports:** each file imports everything it uses. Don't rely on another file having imported it first.
- **Data:** `local _UPPER_SNAKE` constants. These are private to the file.
- **Private Implementation:** `local function` only. These are private to the file.
- **Public Interface:** the global functions other files call.
- **Public Implementation:** functions that must be global for host reasons, such as callbacks, but that aren't part of the public interface.

When a project has several modules with the same shape, keep a template file with this layout and copy it for each new module.

## Naming

| Kind | Pattern |
|---|---|
| Public API | `<Namespace>_<Verb>`, for example `Mod_Pbg_Resolve` |
| Local helper | `_PascalCase` local |
| Constants | `local _UPPER_SNAKE` |
| Variable | `local snake_case` |

Lua has no namespaces, so the prefix is the namespace. Don't use bare globals such as `STATE` or `CACHE`, and don't make every helper a global.

## Plugin-style modules

When a system has several kinds of something, give each kind its own file. Each file exposes the same set of lifecycle functions, registers them through an explicit `<Kind>_Register()` function, and an init function calls every register function. Registration should never run as a side effect when the file loads.

```lua
function Module_Register()
    Singleton_RegisterHandlers(
        "bar",
        Module_Function,
        ...  -- Remaining functions for plugin
    )
end
```

- **Document each slot once**, at the registration function.
- **Optional slots take `nil`**, and the engine checks for `nil`.
- **Key per-instance state by the instance's id.** Assume several instances of the same kind can be active at once.
- **Return booleans from lifecycle functions** ("did this succeed", "is this complete"). The engine owns any shared side effects. Modules report state; they don't drive the engine.
- **Prefer events to polling.** Register one listener per kind, add it on the first activation, and remove it when the last instance deactivates. Track this with a flag such as `listener_registered`.
- **Make start and stop idempotent**, with an early return guarded by a state flag.
- **Pass collaborators in as arguments** (for example `OnStart(start_hooks)`) rather than reaching into another module's globals.
- **Don't build batching, re-entrancy guards or depth counters into the engine.** Keep the core loop simple enough that it doesn't need them.

## Idioms

- **Use `a and b or c` for simple selections**, and `x or {}` / `x or 1` for defaults.
- **When a call has many arguments or a condition has many clauses, put one per line** and start continuation lines with `and`/`or`.
- **Wrap every value with `tostring(...)` when building a log string.**
- **Validate external data with a chain of `type(x) == "..." and ...` predicates.** Skip and log whatever fails.
- **Indentation follows the file you're in.** Don't mix tabs and spaces within one file.
