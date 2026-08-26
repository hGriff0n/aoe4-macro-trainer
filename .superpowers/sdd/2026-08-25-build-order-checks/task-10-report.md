# GRI-80 Rallypoint Check Report

## Scope

Implemented the `rallypoint` compiler descriptor and a per-check SCAR handler on
`codex/gri-80-rallypoint-check`, based on `a85768f`.

## Official API and Source Research

- `Player_GetEntities(player)` is documented in `Essence_ScarFunctions.api`
  (line 1284) as returning that player's entities. The handler starts this query
  only from `context.localPlayer`.
- `Entity_GetPlayerOwner(entity)` is a documented high-confidence ownership API
  (`Essence_ScarFunctions.api`, line 671). Every candidate is explicitly checked
  against the stored local player before it is classified or observed.
- `Entity_GetBlueprint` and `Entity_IsEBPOfType` are documented high-confidence
  APIs. Official `gameplay/chatcheats.scar` uses
  `Entity_IsEBPOfType(ebp, "town_center_capital")` to identify the capital TC.
  The handler also recognizes `town_center` for later TCs, but this type's
  cross-civilization coverage could not be verified from the available official
  data index.
- `Entity_GetRallyPointPositions(entity)` is documented in
  `Essence_ScarFunctions.api` line 677 and has an official
  `missionomatic/missionomatic_leadertent.scar` usage. It returns only named
  positions (`position1`, etc.), not a target entity or resource category.
- `Rule_AddInterval` and `Rule_Remove` are high-confidence official SCAR
  wrappers (`rulesystem.scar` lines 82 and 337).

No supported API/source was available to map a rally position to a canonical
food/gold/wood/stone target, nor to establish that `Player_GetEntities` is
ordered by TC construction time. Spatial or TC-existence inference would be
unsafe, so it is intentionally not used.

## Behavior

- One configured resource emits `Rally new vils to <resource>`.
- Multiple resources emit `Rally Main TC to <resource>` followed by
  `Rally TC #<index> to <resource>`, with one-based `tc_index` and `tc_count`.
- Rally descriptors are `optional=True`: the visible objective stays
  non-blocking while the API capability gap exists.
- The handler has isolated state and interval rule per `check.id`, polls only
  explicitly local-owned TC candidates, stores the supported rally position for
  observation, and assigns `false` rather than inferring completion. It removes
  the exact rule and state during deactivation.

## TDD Evidence

RED:

`python -m unittest tests.test_build_order_rallypoint -v` failed as expected:
the old compiler produced `Rally to <resource>` with no index/count payload,
and `rallypoint.scar` did not exist.

GREEN:

The same focused command passed all 5 tests after the minimal compiler and
handler implementation. The tests cover one-/two-TC presentation and payloads,
optional non-blocking state, local-player origin, explicit owner guard,
capital/later-TC classification, supported rally-position observation,
non-inference, per-check rule state, and cleanup.

## Validation

- Focused: `python -m unittest tests.test_build_order_rallypoint -v` — 5 passed.
- Full: `python -m unittest discover -s tests -v` — 68 passed.
- SCAR API: `check_code` on `assets/scar/build_orders/checks/rallypoint.scar`
  — 0 unknown calls, 0 low-confidence APIs, 0 missing localization IDs.
- `git diff --check` — passed (the output reports only the repository's
  line-ending normalization warning for `compiler.py`).

No Content Editor build or mod export was run, as required.

## Files

- `tools/build_orders/compiler.py`
- `assets/scar/build_orders/checks/rallypoint.scar`
- `tests/test_build_order_rallypoint.py`

## Self-review

- Player selection and all TC/rally observation originate from the stored
  `context.localPlayer` handle.
- Foreign/opponent ownership is explicitly rejected before type or rally access;
  a matching opponent rally cannot set completion.
- No code path calls `BuildOrder_SetCheckComplete(..., true)` or derives success
  from a TC existing, target position, or index.
- State/rules are keyed by `check.id`; repeated deactivation is safe.
- The known limitation is deliberate: resource-target matching and verified
  construction-order indexing are unavailable with the supported API surface.

## Queued In-game Validation Request

Issue: GRI-80
Branch: codex/gri-80-rallypoint-check
Worktree: E:\Docs\github\aoemod\aoe4-macro-trainer\.worktrees\gri-80-rallypoint-check
Commit: this report is included in `feat: implement GRI-80 rallypoint check`.
Fixture/selection: English one-TC build with `[food]`; English two-TC build with
`[wood, gold]`.
Human actions: Set the local main TC rally to the stated resource; in the two-TC
case set the later local TC rally to the second stated resource, then change
either rally again.
Opponent guard: Set an opponent TC rally to the matching resource before and
after the local-player actions; it must not transition either local objective.
Expected UI: One-TC title is `Rally new vils to food`; two-TC titles are `Rally
Main TC to wood` and `Rally TC #2 to gold`. All remain visible optional checks
and do not block the step.
Limitations: `Entity_GetRallyPointPositions` supplies positions only. It cannot
prove a resource target, and available official source does not prove a stable
construction order for `Player_GetEntities`; therefore no rally action may mark
the check complete until a supported typed target/ordering API is found.

## Review Fix Round 1

The earlier handler still selected the configured TC ordinal using
`Player_GetEntities` order and installed a per-check interval rule. Neither a
documented construction-order signal nor a typed rally-resource target exists,
so retaining that observation was not safe. This round removes all TC discovery,
ownership queries, rally-position queries, completion calls, and rule
registration from `rallypoint.scar`.

Activation now creates one inert per-check record only when the ID is absent;
duplicate activation returns without replacing state. Deactivation only removes
that record, so repeated cleanup is idempotent and there is no late polling
callback or stale rule to remove.

The compiler now makes the capability gap visible in every title with the exact
suffix ` [OPTIONAL: rally target resource cannot be verified]`, while retaining
the one-/two-TC labels, payload index/count, and `optional=True` semantics.

### RED to GREEN Evidence

- RED: `python -m unittest tests.test_build_order_rallypoint -v` produced the
  expected three failures: missing visible limitation suffixes and the old
  handler's unsupported TC/rally/rule calls.
- GREEN: the same focused command passed 6 tests. In addition to real compiler
  output, an executable Python fallback model covers a matching opponent rally
  never transitioning, two independent check IDs, duplicate activation,
  idempotent cleanup, and a late poll remaining false. A narrow static safety
  check confirms the SCAR fallback performs no selection or observation.
- Full: `python -m unittest discover -s tests -v` passed 69 tests.
- SCAR API: `check_code` on `assets/scar/build_orders/checks/rallypoint.scar`
  reported 0 unknown calls, 0 low-confidence APIs, and 0 missing localization
  IDs.
- `git diff --check` passed; only Git's line-ending normalization warnings were
  printed.

### Updated Validation Request

Fixture/selection: English one-TC `[food]` and two-TC `[wood, gold]` build
orders.
Human actions: Set each local TC rally to the displayed resource, change it,
and reactivate/deactivate the same check through a step transition.
Opponent guard: Set an opponent TC to the same resource before and after every
local action; neither the opponent nor local action may transition a rally
descriptor.
Expected UI: `Rally new vils to food [OPTIONAL: rally target resource cannot be
verified]`; for two TCs, the equivalent `Rally Main TC ...` and `Rally TC #2
...` titles with the same suffix. They remain visible and do not block advance.
Limitations: no typed resource target or documented stable construction-order
API is available, so the handler intentionally performs no TC/rally observation
until such a supported signal is found.
