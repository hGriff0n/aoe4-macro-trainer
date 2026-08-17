# Multiplayer-Deterministic Phase Timer Design

## Scope

Implement GRI-43 by adapting the phase timer so normal/slow transitions mutate simulation state deterministically in multiplayer. Preserve the existing 45-second normal phase, 15-second player-facing slow phase, simulation rates, localized objectives, and precomputed simulation-time durations.

The design follows the AoE4 multiplayer mutation pattern: local code may decide and broadcast intent, but shared simulation mutations execute only inside a registered network-event handler that runs on every peer.

## Authority Election

Every peer computes the timer authority using the same deterministic rule: select the connected, non-defeated human player with the lowest player ID. AI players never qualify.

Each peer retains the active phase number and absolute phase deadline. The same one-shot deadline callback is scheduled on every peer. When it fires, only the peer whose local player matches the elected authority broadcasts the transition intent. All other peers return without mutating simulation state.

If the authority disconnects or is defeated, the next eligible human becomes authority. The existing absolute deadline remains authoritative; election does not restart or extend the phase. Because the deadline callback exists on every peer, the newly elected authority can broadcast when that deadline arrives without reconstructing the timer owned by the departed player.

If no eligible human remains, no transition is broadcast and the current phase remains unchanged while normal game-over handling proceeds.

## Network Event and Payload

Register one top-level network handler during `Mod_OnInit`, before any transition can be requested. The registered name, called name, and global function name must match exactly.

The broadcast payload is a string containing:

- the next monotonically increasing phase number;
- the target phase identifier (`normal` or `slow`).

The network handler parses and validates both fields. It ignores malformed payloads, unknown phase identifiers, phase numbers that are not exactly the expected successor, and events whose sender is not the currently elected authority. Sender validation prevents a non-authority client from forcing a phase change, while the phase number makes duplicate or stale delivery idempotent.

The handler does not trust `Game_GetLocalPlayer()` for shared decisions. Player IDs and eligibility are resolved identically on every peer; local-player identity is used only by the deadline callback to decide whether this machine should broadcast.

## Phase State and Data Flow

Startup elects the current authority and requests phase 1 (`normal`) through the network event. The network handler is the only phase-entry path:

1. Validate the sender, phase number, and target phase.
2. Remove the previous deadline rule and silently expire the previous objective.
3. Commit the accepted phase number and phase identifier.
4. Select the phase's precomputed duration, simulation rate, objective title, and next phase.
5. Record `phaseStartTime` and the absolute `phaseDeadline`.
6. Register and start the new objective and its countdown.
7. Apply `Misc_SetSimRate`.
8. Schedule the shared one-shot deadline callback using the phase duration.

At the deadline, the callback reads the already committed next phase and phase number. The elected local authority broadcasts that intent; it performs no objective, rate, world, player, entity, or other simulation mutation itself. Receipt of the event starts the next phase on all peers on the same lockstep tick.

The absolute deadline remains stored as phase state for authority handoff, diagnostics, and validation. Authority changes do not rewrite it. The one-shot delay remains the scheduling mechanism, so this change does not add a polling loop.

## Lifecycle and Failure Handling

`Mod_OnInit` registers the network event. `Mod_Start` precomputes the existing whole simulation-time durations and initiates the normal phase through the elected authority's network broadcast.

Defeat and disconnect state feed authority eligibility but do not directly transition or restart a phase. A handoff becomes effective whenever authority is evaluated, including at the active deadline.

`Mod_OnGameOver` removes the shared deadline callback and clears the active objective. It restores the normal simulation rate through a deterministic network request when an eligible human remains. If the engine's game-over lifecycle no longer accepts network events, the implementation will omit the restoration mutation rather than perform a peer-local simulation write; the match is already ending and correctness takes priority over cosmetic cleanup.

## Component Boundaries

- Authority selection returns an eligible player ID or no authority. It depends only on synchronized player state and defeat tracking.
- The deadline callback compares the elected ID with the local player ID and broadcasts a string intent. It never mutates shared state.
- The network handler validates intent and owns all shared phase mutations.
- Phase application owns objective lifecycle, rate selection, deadline state, and scheduling, and is called only by the network handler.
- Game-over cleanup cancels pending local callbacks and prevents later phase requests.

These boundaries keep local-only decisions visibly separate from lockstep mutations and allow source-level tests to reject accidental shared writes outside the handler path.

## Testing and Validation

Extend the Python contract suite to require:

- network event registration during initialization;
- a matching top-level global handler;
- string payload encoding and parsing for phase number and identifier;
- deterministic lowest-ID connected, non-defeated human election;
- authority and sequential phase-number validation;
- no shared phase mutation in the deadline callback;
- all objective, phase-state, sim-rate, and next-deadline mutations behind the network handler;
- one deadline callback scheduled on every peer;
- preservation of the absolute deadline across authority changes;
- AI exclusion and no-authority behavior;
- removal of pending callbacks and objective cleanup on game over.

Run the complete automated suite, validate the SCAR APIs against the available AoE4 API references, and export the mod. Multiplayer playtesting must cover two humans transitioning together, a non-authority attempting no duplicate broadcast, authority defeat, authority disconnect during each phase, next-authority takeover at the unchanged deadline, AI exclusion, and normal game-over cleanup.
