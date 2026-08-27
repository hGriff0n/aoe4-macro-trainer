# Build-Order Global Event Probe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a dedicated Macro Trainer diagnostic mod that subscribes to all official `GE_*` events and emits machine-parseable callback contexts to `scarlog.txt`.

**Architecture:** A local Python generator reads the sanitized official AoE4 MCP index and writes a deterministic SCAR event inventory. A probe module registers one stored callback per event with `Rule_AddGlobalEvent`, logs every callback unconditionally, and retains raw contexts for the attached debugger. Only the diagnostic worktree imports the module.

**Tech Stack:** Python 3 standard library (`argparse`, `pathlib`, `sqlite3`), AoE4 SCAR/Lua, Content Editor global-event rules, SCAR console and `scarlog.txt`.

**Spec:** `docs/superpowers/specs/2026-08-26-build-order-event-probe-design.md`

## Global Constraints

- Work only on branch `codex/gri-83-event-probe` in `.worktrees/gri-83-event-probe`, created from commit `8b112758f3cc49ca24613623a5893259d120fd04` on `codex/gri-83-objective-checks`.
- Inventory every distinct `GE_*` `api_constant` in the official API source set; do not limit the probe to current GRI-83 checks.
- Register through official `Rule_AddGlobalEvent(callback, eventConstant)` behavior.
- Logging is unconditional. Do not add controls, filters, sampling, rate limits, or event suppression.
- Do not add automated tests for this throwaway probe. Verification is deterministic inventory generation, SCAR checking, a successful Content Editor build, debugger attachment, and `scarlog.txt` inspection.
- The probe observes only. It must not mutate objectives or gameplay state.
- Do not call `Rule_Remove` for global events: official `rulesystem.scar` states that `Rule_Remove` supports time rules only and global-event removal requires additional input for which no supported wrapper was found.
- Production issue branches remain unchanged until the probe evidence is reviewed.

---

### Task 1: Create the Diagnostic Worktree and Official Event Inventory

**Files:**
- Create: `tools/event_probe/generate_registry.py`
- Create/generated and commit: `assets/scar/event_probe/generated_events.scar`

**Interfaces:**
- Consumes: SQLite database with `code_records(symbol, symbol_kind, source_set, ...)` from the AoE4 MCP workspace.
- Produces: `generate_registry(database: Path, output: Path) -> list[str]` and SCAR global `EVENT_PROBE_EVENTS`, an ordered array of `{name=<string>, event=<GE constant>}`.

- [ ] **Step 1: Create the isolated worktree**

From the repository root, create the branch from the approved design commit:

```powershell
git worktree add .worktrees/gri-83-event-probe -b codex/gri-83-event-probe 8b112758f3cc49ca24613623a5893259d120fd04
```

Verify:

```powershell
git -C .worktrees/gri-83-event-probe branch --show-current
git -C .worktrees/gri-83-event-probe rev-parse HEAD
```

Expected: branch `codex/gri-83-event-probe` and head `8b112758f3cc49ca24613623a5893259d120fd04`.

- [ ] **Step 2: Implement the registry generator**

Create `tools/event_probe/generate_registry.py` with this interface and query:

```python
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


EVENT_QUERY = """
SELECT DISTINCT symbol
FROM code_records
WHERE source_set = 'official_api'
  AND symbol_kind = 'api_constant'
  AND substr(symbol, 1, 3) = 'GE_'
ORDER BY symbol
"""


def load_events(database: Path) -> list[str]:
    with sqlite3.connect(database) as connection:
        events = [row[0] for row in connection.execute(EVENT_QUERY)]
    if not events:
        raise RuntimeError("official event inventory is empty")
    if len(events) != len(set(events)):
        raise RuntimeError("official event inventory contains duplicates")
    return events


def render_registry(events: list[str]) -> str:
    lines = [
        "-- Generated from official_api Essence_Constants.api; diagnostic branch only.",
        "EVENT_PROBE_EVENTS = {",
    ]
    lines.extend(
        f'\t{{name = "{event}", event = {event}}},' for event in events
    )
    lines.extend(["}", ""])
    return "\n".join(lines)


def generate_registry(database: Path, output: Path) -> list[str]:
    events = load_events(database)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_registry(events), encoding="utf-8", newline="\n")
    return events


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    events = generate_registry(args.db, args.output)
    print(f"generated {len(events)} global events at {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Generate and inspect the full inventory**

Run from the diagnostic worktree:

```powershell
python tools/event_probe/generate_registry.py `
  --db E:\Docs\github\aoemod\aoe4-mcp\data\index.sanitized.sqlite3 `
  --output assets/scar/event_probe/generated_events.scar
```

Expected against the current sanitized index: `generated 185 global events`, including at least:

```text
GE_BuildItemCancelled
GE_BuildItemComplete
GE_BuildItemStart
GE_ConstructionCancelled
GE_ConstructionComplete
GE_ConstructionStart
GE_EntityOwnerChange
GE_EntitySpawn
GE_PlayerAddResource
GE_ResourceDroppedOff
GE_SquadOwnerChange
GE_SquadProductionQueue
GE_SquadSpawn
GE_UpgradeCancelled
GE_UpgradeComplete
GE_UpgradeStart
```

Regenerate a second time and verify there is no diff:

```powershell
python tools/event_probe/generate_registry.py --db E:\Docs\github\aoemod\aoe4-mcp\data\index.sanitized.sqlite3 --output assets/scar/event_probe/generated_events.scar
git diff --exit-code -- assets/scar/event_probe/generated_events.scar
```

- [ ] **Step 4: Commit the generator and inventory**

```powershell
git add tools/event_probe/generate_registry.py assets/scar/event_probe/generated_events.scar
git commit -m "chore: generate GRI-83 global event inventory"
```

---

### Task 2: Implement Unconditional Event Context Logging

**Files:**
- Create: `assets/scar/event_probe/event_probe.scar`
- Modify: `assets/scar/winconditions/Macro Trainer.scar`

**Interfaces:**
- Consumes: global `EVENT_PROBE_EVENTS` from Task 1 and official `Rule_AddGlobalEvent(callback, eventConstant)`.
- Produces: `EventProbe_Start()`, global `EVENT_PROBE_SEQUENCE`, `EVENT_PROBE_COUNTS`, and `EVENT_PROBE_LAST_CONTEXT`; log records prefixed `GRI83_EVENT`.

- [ ] **Step 1: Add the probe state and deterministic context serializer**

Create `assets/scar/event_probe/event_probe.scar`. Use these globals and record shapes:

```lua
EVENT_PROBE_STARTED = false
EVENT_PROBE_SEQUENCE = 0
EVENT_PROBE_COUNTS = {}
EVENT_PROBE_LAST_CONTEXT = {}

function EventProbe_PrintRecord(sequence, eventName, recordType, path, valueType, value)
	print("GRI83_EVENT|" .. tostring(sequence)
		.. "|" .. eventName
		.. "|" .. recordType
		.. "|" .. path
		.. "|" .. valueType
		.. "|" .. tostring(value))
end
```

Implement:

```lua
function EventProbe_SortedKeys(value)
function EventProbe_LogValue(sequence, eventName, path, value, depth, seen)
function EventProbe_Log(eventName, context)
```

`EventProbe_SortedKeys` collects table keys and sorts them by `tostring(key)`. `EventProbe_LogValue` prints primitives directly; for tables it checks `seen[value]`, prints `<cycle>` when already visited, prints `<max-depth>` after depth `4`, and otherwise visits every sorted key recursively. For engine-owned values, log `scartype(value)` and `tostring(value)` without calling type-specific entity, squad, player, or PBG APIs. The raw callback context remains stored for debugger inspection.

`EventProbe_Log` must emit:

```text
GRI83_EVENT|<sequence>|<event>|BEGIN|context|<type>|<value>
GRI83_EVENT|<sequence>|<event>|FIELD|context.<path>|<type>|<value>
GRI83_EVENT|<sequence>|<event>|END|context|<type>|<value>
```

- [ ] **Step 2: Register every event with a stable callback identity**

Use a callback factory so each entry retains its event name:

```lua
function EventProbe_CreateCallback(eventName)
	return function(context)
		EventProbe_Log(eventName, context)
	end
end

function EventProbe_Start()
	if EVENT_PROBE_STARTED then
		return
	end
	EVENT_PROBE_STARTED = true

	for _, entry in ipairs(EVENT_PROBE_EVENTS) do
		entry.callback = EventProbe_CreateCallback(entry.name)
		print("GRI83_EVENT|REGISTER|" .. entry.name)
		Rule_AddGlobalEvent(entry.callback, entry.event)
	end

	print("GRI83_EVENT|READY|" .. tostring(#EVENT_PROBE_EVENTS))
end
```

Do not add a stop function that calls `Rule_Remove`: the official wrapper does not remove event rules.

- [ ] **Step 3: Import and start the probe in the diagnostic main script**

In `assets/scar/winconditions/Macro Trainer.scar`, immediately after the existing utility imports add:

```lua
import("event_probe/generated_events.scar")
import("event_probe/event_probe.scar")
```

At the first line of `Mod_OnInit`, add:

```lua
EventProbe_Start()
```

Leave every normal Macro Trainer system intact so ordinary player actions can be exercised in the same match.

- [ ] **Step 4: Run static validation and inspect registration completeness**

Run:

```powershell
git diff --check
rg -c "name = \"GE_" assets/scar/event_probe/generated_events.scar
rg -n "EventProbe_Start|Rule_AddGlobalEvent|GRI83_EVENT" assets/scar/event_probe assets/scar/winconditions/'Macro Trainer.scar'
```

Expected: inventory count equals the generator output; one dynamic registration path; unconditional logging present; no logging controls.

Pass the generated inventory, `event_probe.scar`, and modified main script to the AoE4 MCP `check_code` tool. Treat unknown external calls, low-confidence APIs, and syntax findings as blocking except for `Rule_AddGlobalEvent`, which is an official `rulesystem.scar` wrapper with direct official game-mode usage rather than a C++ API entry. Module-local helper names may likewise be recorded as local-symbol checker limitations.

- [ ] **Step 5: Commit the runtime probe**

```powershell
git add assets/scar/event_probe/event_probe.scar assets/scar/winconditions/'Macro Trainer.scar'
git commit -m "feat: add GRI-83 global event probe"
```

---

### Task 3: Build the Probe and Hand Off the Debug Run

**Files:**
- Create outside Git: built `.aoe4mod` package and Content Editor burn logs.
- Create after user run, outside Git: parsed event evidence matrix from `scarlog.txt`.

**Interfaces:**
- Consumes: `E:\Docs\github\aoemod\aoe4-macro-trainer\.worktrees\gri-83-event-probe\Macro Trainer.aoe4mod` and committed probe source.
- Produces: a successfully built diagnostic mod, gameplay action checklist, user-supplied `scarlog.txt`, and per-event evidence matrix.

- [ ] **Step 1: Verify the exact source state before building**

```powershell
git status --short
git log -3 --oneline --decorate
git diff --check
```

Expected: clean tracked worktree and both probe commits above the design commit.

- [ ] **Step 2: Build only the diagnostic worktree**

Invoke the `aoe4mod-build` skill with:

```text
E:\Docs\github\aoemod\aoe4-macro-trainer\.worktrees\gri-83-event-probe\Macro Trainer.aoe4mod
```

Require a zero Content Editor exit code and a freshly produced package. Do not build any GRI issue worktree during this task.

- [ ] **Step 3: Hand off the attached-debugger workflow**

Provide the user these exact checks:

1. Launch AoE4 with `-dev` and attach the Content Editor.
2. Start a match with the diagnostic Macro Trainer mod.
3. Confirm the SCAR console contains `GRI83_EVENT|READY|<inventory-count>`.
4. Perform the spec's gameplay action matrix in a recorded order, including matching opponent actions before human actions.
5. Exit the match and attach `Documents\My Games\Age of Empires IV\Logfiles\<latest-run>\scarlog.txt` to the main task.

If startup fails, use the last `GRI83_EVENT|REGISTER|<event>` record and fatal stack trace to identify the exact incompatible constant; fix and rebuild rather than suppressing runtime logging for working events.

- [ ] **Step 4: Parse and document the evidence**

Parse `GRI83_EVENT` records by sequence and event. Produce a matrix with:

```text
event | action | actor | callback count/order | context keys/types | player predicate | canonical ID | timing | suitable checks | verdict
```

For each GRI-83 check, record either:

```text
event preferred: <event> — <payload/timing/player evidence>
```

or:

```text
polling retained: <events tested> — <missing/incorrect payload or semantics>
```

- [ ] **Step 5: Dispatch worktree reassessments**

Send each affected finding to its existing persistent issue agent. Agents update only their original branch/worktree, preserve explicit human-player filtering, run their issue's focused/full/static checks, commit, and return through scoped review before rejoining the validation queue.
