# Build-Order Global Event Probe Design

## Purpose

Build a dedicated diagnostic variant of Macro Trainer that subscribes to every discoverable official `GE_*` global event and records what fires during controlled gameplay. The resulting `scarlog.txt` evidence will determine which GRI-83 handlers can replace polling or capability fallbacks with reliable event-driven behavior.

The investigation changes the evidence standard for GRI-83: event-driven checks are preferred. Polling is retained only when the probe and official-source research establish that no usable event exists, that the event payload cannot be scoped to the human player and matched to the requested action, or that event semantics do not represent the objective accurately.

## Isolation

The probe uses branch `codex/gri-83-event-probe` and worktree `.worktrees/gri-83-event-probe`, created from the shared `codex/gri-83-objective-checks` foundation. It does not modify any issue worktree or the eventual integration branch.

Probe-only imports and logging never enter a production branch. After the investigation, findings return to the existing persistent issue agent for each affected GRI sub-issue.

## Official Event Contract

The Content Editor scripting guide documents `Rule_AddGlobalEvent(FunctionName, GlobalEventKey)` as the supported global-event rule and directs authors to discover event keys through the editor's `GE` autocomplete. Official SCAR source also defines `Rule_AddGlobalEvent(f, eventType, userDataTable)` in `rulesystem.scar` and uses it with events including `GE_ConstructionComplete`, `GE_BuildItemComplete`, `GE_EntityKilled`, `GE_UpgradeStart`, and `GE_UpgradeComplete`.

The implementation inventory is every `GE_*` constant discoverable from the installed Content Editor's official constants and editor autocomplete. It is not limited to events already associated with a build-order check. Each inventory entry records the exact constant name and value reference used in SCAR.

References:

- [Editing a Script: Global Event rules](https://support.ageofempires.com/hc/en-us/articles/4424274153620-Editing-a-Script)
- [Script Debugging](https://support.ageofempires.com/hc/en-us/articles/4467678364052-Script-Debugging)

## Probe Runtime

The probe module owns:

- a registry containing every discovered event name, constant, and callback;
- a monotonically increasing global sequence number;
- per-event invocation counts;
- the latest raw callback context for every event; and
- unconditional SCAR-console logging.

Startup creates a distinct callback closure for every registry entry and calls `Rule_AddGlobalEvent` with that callback and event constant. A registration line is printed immediately before each subscription so a fatal startup error identifies the exact event being registered.

Every callback:

1. increments the global sequence and its event count;
2. stores the raw context in a debugger-visible global keyed by event name;
3. prints a begin record containing sequence, event name, and callback-context type;
4. walks every available context field in deterministic key order;
5. prints each field path, `scartype`, and safely stringified value; and
6. prints an end record.

Nested tables are traversed with cycle detection and a conservative depth bound. The untouched raw context remains available through the debugger Globals pane when a nested or engine-owned value cannot be represented fully in text.

The log record prefix is `GRI83_EVENT`. Records are delimiter-separated and contain no localized presentation text, allowing the main task to parse `scarlog.txt` into an event sequence and payload matrix.

Logging is always enabled. The probe has no runtime controls, filters, sampling, or event suppression. It deliberately records high-volume and unexpected events because discovering their behavior is its only purpose.

## Lifecycle

Probe registration is idempotent. The module starts once from the diagnostic build's normal startup path. If an official removal mechanism is verified, game-over cleanup unregisters every stored callback. If the rulesystem exposes no supported per-event removal contract, the design records that limitation and relies on match teardown; it does not invent a removal call.

The probe must not create, complete, or otherwise mutate build-order objectives. It observes and logs only.

## Build and Debug Workflow

The main task performs these steps:

1. create the dedicated branch and worktree;
2. enumerate official `GE_*` constants and preserve the inventory as probe source;
3. add the probe module and its diagnostic-only import;
4. run the AoE4 SCAR API checker and whitespace validation;
5. build the `.aoe4mod` from the dedicated worktree; and
6. hand the build and gameplay action matrix to the user.

The user launches AoE4 with `-dev`, attaches the Content Editor, runs the diagnostic mod, performs representative human and opponent actions, and attaches the resulting `scarlog.txt` to the main task. Breakpoints and the Globals/Locals panes may be used to inspect raw contexts when the serialized log is insufficient.

There is no automated-test layer for this throwaway diagnostic build. Its validation is a successful SCAR check, successful Content Editor build, successful debugger attachment, callback execution, and an inspectable log file.

## Gameplay Action Matrix

One run should exercise at least:

- human and opponent unit queueing and production completion;
- human and opponent building foundation placement, construction start, cancellation, and completion;
- human and opponent upgrade queueing, start, cancellation where possible, and completion;
- ordinary landmark age-up start and completion plus one non-building age-up mechanism when practical;
- resource gathering, spending, delivery, and resource depletion;
- villager task changes among food, wood, gold, stone, construction, repair, and idle;
- unit creation, death, conversion or ownership transfer, garrisoning, ungarrisoning, and transformation when practical;
- rallypoint changes on human and opponent production buildings and town centers; and
- objective step activation/deactivation boundaries so event timing can be compared with handler lifecycle needs.

Actions are performed in a known order and recorded alongside approximate game time. Opponent actions precede matching human actions where possible so payload ownership can be distinguished.

## Evidence Analysis

The main task parses the attached log into a table containing:

- event name;
- triggering action;
- human or opponent actor;
- callback count and ordering;
- context keys and observed SCAR types;
- player/owner identity availability;
- entity, squad, producer, queue item, blueprint, upgrade, resource, or target identity availability;
- duplicate behavior;
- timing relative to start/completion/cancellation; and
- suitability for a latched or reversible build-order check.

An event is suitable for a production handler only when the observed payload supports an explicit human-player predicate before blueprint, action, or target matching. An event that fires but cannot distinguish the human from an opponent is not sufficient.

## Worktree Reassessment

After the evidence matrix is reviewed, the main task identifies affected checks and sends each finding to that check's existing persistent issue agent. Each issue remains isolated in its original worktree.

Agents replace polling with events when the evidence demonstrates correct semantics and player scoping. Event registrations must be per-handler or shared safely, support multiple active descriptors, ignore late callbacks, and clean up idempotently. Revised branches repeat static review and return to the user-selected validation queue. Polling remains only with a written probe finding explaining why the event path is unworkable for that check.

## Success Criteria

The investigation is complete when:

- the diagnostic worktree subscribes to every discoverable official `GE_*` event;
- the built mod produces parseable `GRI83_EVENT` records in `scarlog.txt`;
- the controlled action matrix includes both human and opponent activity;
- every relevant observed event has documented payload and timing semantics; and
- every GRI-83 handler has an evidence-backed decision to use an event or retain polling.
