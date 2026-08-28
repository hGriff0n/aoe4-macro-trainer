# Start-event objective refactors

## Evidence

The 2026-08-27 probe shows that upgrade identity is carried in `context.upgrade`, not `context.pbg`. `GE_UpgradeStart` fires when Forestry and Economic Wing become active. Successful research emits `GE_UpgradeCancelled` immediately followed by `GE_UpgradeComplete`, so cancellation cannot be applied synchronously. Upgrade ownership remains polymorphic: resolve an entity executor's owner or accept a direct player executor.

`GE_ConstructionStart` fired once per placed foundation in the observed session and is distinct from `GE_ConstructionWorkerStart`. It carries `context.player`, `context.pbg`, and `context.entity`. The age-up schema is latched on start, so later construction cancellation does not undo the completed age-up descriptor.

For production, `GE_EntityCommandIssued` with command type 3 fired once per queue click. It did not fire when a waiting Villager advanced to active production, so it is queue insertion rather than production start. Its callback identifies only the source entity; product identity must come from the source entity's production queue. No unit cancellation was exercised, so callback ordering and cancellation signaling remain unproven.

## Design

### GRI-57

- Conventional civilizations subscribe to `GE_ConstructionStart`; upgrade-age civilizations subscribe to `GE_UpgradeStart`.
- Reject non-human ownership before matching the cached full PBG tuple.
- Read upgrade identity from `context.upgrade`.
- Deduplicate construction foundations by `EntityID` defensively, then latch completion. Cancellation does not revert a latched age-up start.
- Retain completed-upgrade and completed-landmark activation reconciliation for actions completed before handler activation.

### Queue-event probe

- On `GE_EntityCommandIssued`, log source owner and every production-queue entry synchronously and one simulation tick later.
- Log the same queue snapshot on `GE_BuildItemComplete`, `GE_BuildItemCancelled`, `GE_UpgradeStart`, `GE_UpgradeCancelled`, and `GE_UpgradeComplete`.
- Preserve full PBG tuples and item types. Never hardcode command enum values into objective handlers based only on this probe.
- The controlled session queues two distinct units, cancels a waiting unit, cancels an active unit, queues an upgrade behind another item where possible, genuinely cancels/requeues it, and repeats relevant actions with an opponent.

### GRI-59 and GRI-60

- Do not remove their current queue polling until the focused probe proves a command is emitted for both insertion and cancellation and establishes whether queue mutation is visible synchronously or only on the next tick.
- GRI-59 may independently fix completed-event identity to `context.upgrade`; its final queued refactor uses start/cancel/complete plus event-triggered queue reconciliation.
- A successful upgrade completion wins over the immediately preceding cancellation. Cancellation is marked pending and reconciled after event dispatch; completed research remains latched, while a queued check may return false only while its step is still active.
- GRI-60 continues using `GE_BuildItemComplete` for normal production. Its queued refactor uses human-owned source commands and completion/cancellation events only after the probe proves full add/remove coverage.

## Validation boundary

All callbacks filter specifically to the bound human player before inspecting identity or changing objective state. Sub-issue agents run static tests only and return validation requests. The main thread builds only the user-selected worktree.
