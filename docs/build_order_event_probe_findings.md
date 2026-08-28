# GRI-83 build-order event probe findings

## Scope

This report analyzes one single-player Abbasid probe session recorded in:

`E:\Docs\My Games\Age of Empires IV\LogFiles\AoE4_08_27_14h-09m-58s\scarlog.2026-08-27.14-09-58.txt`

The human player produced one Scout and two Villagers, changed the Town Center rally target between food and a Sheep, constructed a House of Wisdom, Mining Camp, House, and Lumber Camp, researched Forestry, and advanced with Economic Wing. The session also included cancelled Barracks, Mining Camp, and Mill placements.

The probe registered 177 runtime-available global events, skipped 8 unavailable constants, and recorded 61,068 complete callback sequences across 20 event types. All action events in this single-player session that directly exposed an owner used internal `PlayerID=1007`. Code must never hardcode that value; handlers must compare event ownership with their bound human player.

## Executive recommendations

| Check | Best observed signal | Verdict |
| --- | --- | --- |
| `built` (GRI-56) | `GE_ConstructionComplete` | Use as the primary completion signal. It carries human-filterable owner, canonical building PBG, and entity instance. Retain an activation snapshot for pre-existing buildings. |
| `age_up` (GRI-57) | `GE_UpgradeStart` is the best observed Abbasid-wing candidate | An existing House of Wisdom does not prove a wing started. Resolve the upgrade executor's owner. Verify positive-progress semantics and test ordinary constructed landmarks separately before replacing polling for other civilizations. |
| `upgrades` (GRI-59) | `GE_UpgradeComplete` for completed research; `GE_UpgradeStart` for active research | Use completion events plus activation reconciliation. Queue insertion remains unresolved because both tested upgrades started on idle executors. Handle either entity- or player-shaped executor ownership. |
| `produce` (GRI-60) | `GE_BuildItemComplete` | Use for completed production. It provides product PBG, player, and spawned squad. No typed queue/start event fired. |
| `units` (GRI-62) | Periodic authoritative reconciliation | Retain periodic owner-filtered squad polling. `GE_BuildItemComplete` and death/ownership events may trigger extra recounts, but the observed event set is incomplete for conversions, grants, despawns, and ownership changes. |
| `rallypoint` (GRI-80) | `GE_EntityCommandIssued`, observed `EntityCommandType(12)` | The change is observable, but the callback exposes only the source entity and target instance/position—not a canonical resource. Keep the check optional/inert unless runtime target inspection proves resource classification. |
| `vils` (GRI-55) | None established by this session | Keep authoritative polling. Command events describe intent and do not expose authoritative current worker allocation. |
| `resources` (GRI-58) | None suitable | `GE_PlayerAddResource` fired 2,172 times and is delta/noise-oriented, not a reliable threshold state. Keep authoritative polling. |
| `hints` (GRI-63) | Not applicable | Presentation-only optional descriptors have no runtime condition. No event-driven change is needed. |

## Registration versus runtime traffic

Registration was a single startup pass: 177 `REGISTERED` records, 8 `UNAVAILABLE` records, and one `READY` record. Numbered records were actual callbacks, not repeated registration.

| Event | Callback count |
| --- | ---: |
| `GE_AbilityExecuted` | 29,387 |
| `GE_AbilityComplete` | 29,370 |
| `GE_PlayerAddResource` | 2,172 |
| All other events combined | 139 |

The ability events were passive/system activity repeated across entities. They should not drive build-order checks. Global sequence adjacency is not proof of causality because this traffic creates thousands of unrelated callbacks between player actions.

Unavailable constants in this runtime were `GE_EntityBlockShotCountUpdated`, `GE_InfluenceUpdate`, `GE_PlayerSentTribute`, `GE_PresentationSoundEvent`, `GE_ResourceDroppedOff`, `GE_ResourceEnabled`, `GE_SquadColourChanged`, and `GE_WeaponChanged`.

## Unit production

### Queue commands

The Town Center entity `1000005876` emitted `GE_EntityCommandIssued` with `EntityCommandType(3)` at:

| Sequence / line | Time | Correlated result |
| --- | --- | --- |
| `319` / 2648–2651 | 14:10:44.266 | Scout completed 22.899 seconds later |
| `6259` / 48540–48543 | 14:11:22.615 | First Villager completed 19.916 seconds later |
| `6306` / 48898–48901 | 14:11:22.831 | Second Villager completed 39.699 seconds later |

This strongly identifies command type 3 as a production-queue addition in this context. The callback contains only `context.command` and `context.entity.EntityID`; it does not contain the queued product PBG. It can prove that something was queued at a particular building, but not which unit without a separate queue-inspection API.

Although `GE_BuildItemStart`, `GE_BuildItemCancelled`, and `GE_SquadProductionQueue` were registered, none emitted a callback.

### Completed products

| Sequence / lines | Time | Product | Context |
| --- | --- | --- | --- |
| `3819` / 29695–29701 | 14:11:07.165 | Scout, PBG `199733`, `unit_scout_1_abb` | player `1007`; spawned squad `50046` |
| `10044` / 77619–77625 | 14:11:42.531 | Villager, PBG `199747`, `unit_villager_1_abb` | player `1007`; spawned squad `50047` |
| `14699` / 113268–113274 | 14:12:02.530 | Villager, PBG `199747` | player `1007`; spawned squad `50048` |

Each action produced exactly one `GE_BuildItemComplete`. The useful fields are:

- `context.player.PlayerID` for the mandatory human-player filter;
- the complete `context.pbg` tuple for canonical identity and mod-pack collision safety;
- `context.spawnedSquad.SquadID` for deduplication or a targeted recount.

For `produce`, count matching human-owned completions while the descriptor is active. This probe does not establish whether scripted grants also emit `GE_BuildItemComplete`, so that semantic should be documented or tested separately.

## Construction

`GE_ConstructionStart`, `GE_ConstructionWorkerStart`, `GE_ConstructionCancelled`, and `GE_ConstructionComplete` all carried:

- `context.player.PlayerID`;
- the full canonical `context.pbg` tuple;
- `context.entity.EntityID` for the building instance.

| Building | PBG | Instance | Start | Worker start | Terminal event |
| --- | ---: | ---: | --- | --- | --- |
| House of Wisdom | `199772` | `1000005890` | seq `853`, lines 6772–6778 | seq `1329`, lines 10454–10460 | complete seq `5915`, lines 45894–45900 |
| Mining Camp, cancelled placement | `199633` | `1000005893` | seq `4207`, lines 32676–32682 | none | cancel seq `4514`, lines 35051–35057 |
| Mining Camp | `199633` | `1000005894` | seq `4784`, lines 37134–37140 | seq `5317`, lines 41257–41263 | complete seq `9338`, lines 72211–72217 |
| House | `199635` | `1000005895` | seq `7481`, lines 57933–57939 | seq `9661`, lines 74686–74692 | complete seq `13101`, lines 101027–101033 |
| Mill, cancelled placement | `199631` | `1000005898` | seq `36621`, lines 280992–280998 | none | cancel seq `36872`, lines 282911–282917 |
| Lumber Camp | `199634` | `1000005899` | seq `37248`, lines 285780–285786 | seq `37718`, lines 289390–289396 | complete seq `43323`, lines 332225–332231 |

A Barracks placement, PBG `199643`, instance `1000005891`, also started, received a worker, and was cancelled. Cancelled foundations emitted owner-tagged `GE_EntityKilled` records, so death events must not be treated as unit deaths or construction completion.

For `built`, subscribe to `GE_ConstructionComplete`, reject non-human owners first, match the canonical PBG, and deduplicate by entity instance. Retain activation-time reconciliation because no event reconstructs already completed buildings.

## Technology and age-up upgrades

| Upgrade | PBG | Executor | Start | Terminal records |
| --- | ---: | ---: | --- | --- |
| Economic Wing | `2033116`, `upgrade_add_economy_wing` | House of Wisdom `1000005890` | seq `32114`, lines 246497–246502 | cancel seq `58719`, lines 449777–449782; complete seq `58720`, lines 449783–449788 |
| Forestry | `171999`, `upgrade_econ_resource_wood_fell_rate_1` | Lumber Camp `1000005899` | seq `43884`, lines 336504–336509 | cancel seq `56474`, lines 432641–432646; complete seq `56475`, lines 432647–432652 |

`GE_UpgradeStart` and `GE_UpgradeComplete` provide the full upgrade PBG but normally expose only `context.executer.EntityID`. Resolve that entity's player owner and compare it with the handler-bound human before matching the upgrade. In this session, the executors can be tied to player `1007` through their earlier construction events.

Both successful upgrades emitted `GE_UpgradeCancelled` immediately before `GE_UpgradeComplete`. The cancellation context used `context.executer.PlayerID=1007`. This appears to be terminal queue cleanup, not an actual failed research action. A handler must not undo or reject a completion merely because it observes this paired cancellation.

For completed upgrades, `GE_UpgradeComplete` is the strongest observed signal. Reconcile already completed human-player upgrades when the descriptor activates, because an event-only handler cannot reconstruct earlier completions.

`GE_UpgradeStart` proves that research became active on an executor in these two samples. It does **not** prove insertion into a production queue: both Forestry and Economic Wing were initiated on idle executors. Therefore `upgrades.queued: true` remains unresolved pending a controlled test that queues research behind another item or a verified queue-inspection API.

Upgrade ownership context is polymorphic in this log. Starts and the two named completes used `context.executer.EntityID`; the paired cancellations and secondary PBG `108171` completion used `context.executer.PlayerID`. A shared filter must accept a direct player or resolve an entity owner before comparing with the bound human.

The paired Cancel→Complete behavior proves only that a successful completion must win and must not be undone by the immediately preceding cancellation. No genuine user-cancelled research was tested, so handlers must not generalize this result into ignoring every cancellation.

Economic Wing proves that Abbasid age-up cannot be detected by the existence or construction progress of the House of Wisdom: that building completed about 112 seconds before the wing began. Match the wing upgrade PBG instead. `GE_PlayerPhaseUp` was registered but never fired. A second `GE_UpgradeComplete` with unresolved PBG `108171` and direct player `1007` followed Economic Wing completion by one millisecond; it may represent a generic age transition, but that remains inference and it loses the selected wing identity.

This session does not establish how ordinary constructed-landmark age-ups behave, and it does not prove whether `GE_UpgradeStart` fires at queue insertion or only once positive wing progress begins. GRI-57 needs separate civilization tests before replacing those paths with events.

## Rally target changes

The Town Center entity `1000005876` emitted two `GE_EntityCommandIssued` callbacks with `EntityCommandType(12)`:

| Sequence / lines | Time | Target shape |
| --- | --- | --- |
| `8828` / 68281–68285 | 14:11:36.415 | `context.target.SquadID=50044` |
| `12403` / 95682–95686 | 14:11:52.597 | `context.target.EntityID=1000005141` |

These two callbacks align with the stated food/Sheep rally changes and strongly identify command type 12 as the rally-target command for this Town Center. The target shapes do not establish which callback represented which resource:

- Squad `50044` was later observed as a player-`1007`-owned movable/damageable unit squad. Sheep is plausible but its blueprint was not emitted.
- Entity `1000005141` was repeatedly targeted by human-owned gather commands. A food resource or carcass is plausible but its blueprint/resource type was not emitted.

Neither classification is proven by the rally callback alone.

The event context does not include:

- source entity owner;
- source or target blueprint/PBG;
- a resource enum;
- a stable Town Center ordinal.

An implementation would need to resolve the source entity owner and blueprint, then resolve or inspect the target instance at callback time. The probe establishes that rally changes are observable but does not establish a safe generic mapping from target to `food`, `wood`, `gold`, or `stone`. Until that mapping is proven, `rallypoint` descriptors should remain visible but optional and non-blocking.

## Active unit counts and deaths

No player-wide unit-count event fired. `GE_EntityKilled` included `numRemainingEntities`, but this described the victim/squad context and was emitted for cancelled building foundations. The non-foundation death at seq `18455` (lines 142013–142018, entity `1000005886`, squad `50043`) lacked owner and blueprint; seq `18456` `GE_SquadKilled` exposed only instance IDs. This reinforces that a death callback alone cannot safely decrement a canonical human-player unit count.

Use events only as optional extra recount triggers while retaining periodic polling:

1. Filter or resolve the affected owner.
2. Enumerate the human player's current squads.
3. Match canonical squad blueprints.
4. Recompute the authoritative active count.

Periodic reconciliation handles pre-existing units, conversions, cancelled foundations, grants, and missed/despawn paths more safely than increment/decrement bookkeeping. Event-trigger-only reconciliation can still go stale when no suitable callback fires.

## Human-player filtering rules

- Direct-player contexts (`Construction*`, `BuildItemComplete`) must compare `context.player` with the descriptor's bound human player before matching identity.
- Upgrade contexts may expose either `context.executer.PlayerID` directly or `context.executer.EntityID`; accept the direct player or resolve the entity owner before comparing with the bound human. `EntityCommandIssued` requires source-entity owner resolution.
- Ownerless squad/death contexts must be resolved through current ownership or retained instance state before affecting a check.
- Never infer ownership from event order, entity-number ranges, or the single-player test ID `1007`.
- Preserve the full PBG tuple when practical; PBG ID alone is sufficient for the official mod-pack-zero evidence here but may collide with modded content.

## Events observed as absent or unsuitable

| Event/signal | Finding |
| --- | --- |
| `GE_BuildItemStart` | Registered, no callbacks. |
| `GE_BuildItemCancelled` | Registered, no callbacks. |
| `GE_SquadProductionQueue` | Registered, no callbacks. |
| `GE_PlayerPhaseUp` | Registered, no callbacks during Economic Wing age-up. |
| Spawn/add/size events | `GE_SquadSpawn`, `GE_EntitySpawn`, `GE_PlayerAddEntity`, `GE_PlayerAddSquad`, `GE_SquadMembersChanged`, and `GE_SquadSizeChanged` produced no callbacks. |
| `GE_PlayerAddResource` | Extremely noisy; not an authoritative current-resource threshold. |
| `GE_AbilityExecuted` / `GE_AbilityComplete` | Extremely noisy passive/system traffic; unsuitable for these checks. |
| `GE_EntityKilled` | Includes cancelled foundations and cannot be treated as a unit-count decrement without identity/owner resolution. |

## Required follow-up

1. Switch GRI-56 completion handling to `GE_ConstructionComplete` while retaining activation reconciliation.
2. Switch completed GRI-59 descriptors to `GE_UpgradeComplete`, add activation reconciliation, and retain the queued limitation until a behind-another-item test or queue API proves insertion semantics.
3. Switch completed GRI-60 descriptors to `GE_BuildItemComplete`; explicitly define or defer queued-product semantics because the queue command lacks product identity.
4. Rework the proven Abbasid false positive around wing upgrade identity, then test event timing for positive progress and audit other civilizations' landmark construction events separately.
5. Keep GRI-62 periodic authoritative polling/reconciliation; events may only accelerate a recount.
6. Keep GRI-80 optional until target resource and Town Center identity can be safely resolved from the rally callback.
7. Leave GRI-55, GRI-58, and GRI-63 unchanged: the probe supports their existing polling/presentation designs.
8. Run a multiplayer probe before finalizing any global subscription, verifying that opponent actions are rejected by the same ownership predicates.
