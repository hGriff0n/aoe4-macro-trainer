# Build-Order Checks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the nine production build-order check types tracked by GRI-83 with reliable human-player filtering and user-selected in-game validation.

**Architecture:** A shared engine foundation provides reversible check state and a strict handler lifecycle. Each Linear child issue is implemented by one persistent sub-agent in its own branch and worktree forked from the shared foundation, with one focused SCAR module plus issue-owned compiler and tests. Static review precedes a centralized validation queue; only user-selected worktrees are built by the main task.

**Tech Stack:** AoE4 SCAR/Lua, Python 3 `unittest`, PyYAML compiler/emitter pipeline, AoE4 MCP official API/source index, AoE4 Content Editor CLI for main-task validation only.

**Spec:** `docs/superpowers/specs/2026-08-25-build-order-checks-design.md`

## Global Constraints

- Every runtime query and event callback must target or verify `context.localPlayer`; an opponent performing the same action must not change an objective.
- Sub-agents run Python and AoE4 API-contract checks but never invoke the Content Editor or build an `.aoe4mod` package.
- Every handler stores per-check state keyed by `check.id`, supports multiple descriptors of the same kind, and performs idempotent cleanup.
- Handlers never delete objectives or advance steps directly; they report state to the engine.
- Reversible checks may become incomplete only while their own step remains active; completed earlier steps never rewind.
- Runtime matching uses canonical payload identifiers, never localized presentation text.
- Branches are named `codex/gri-<issue>-<slug>` and fork from the final shared-foundation commit on `codex/gri-83-objective-checks`.
- Each ready branch sends the validation request defined in `docs/build_order_check_handlers.md`; the main task builds only after the user chooses that request.

## File Ownership Map

- Shared foundation: `assets/scar/build_orders/objective_engine.scar`, `tests/test_build_order_objectives.py`, documentation.
- GRI-55: `checks/vils.scar`, `compiler.py` vils branch, vils-focused tests.
- GRI-56: `checks/built.scar`, `compiler.py` built titles, built-focused tests.
- GRI-57: `checks/age_up.scar`, `compiler.py` age-up titles, age-up-focused tests.
- GRI-58: `checks/resources.scar`, `compiler.py` resource titles, resource-focused tests.
- GRI-59: `checks/upgrades.scar`, `compiler.py` upgrade titles/metadata, upgrade-focused tests.
- GRI-60: `checks/produce.scar`, `compiler.py` production titles/metadata, production-focused tests.
- GRI-62: `checks/units.scar`, `compiler.py` unit titles, unit-focused tests.
- GRI-63: compiler-only hint presentation/optionality and hint-focused tests; no runtime module.
- GRI-80: `checks/rallypoint.scar`, `compiler.py` rallypoint titles/index payload, rallypoint-focused tests.
- Integration: `assets/scar/winconditions/Macro Trainer.scar`, combined compiler conflict resolution, combined fixtures/tests.

---

### Task 1: Shared Reversible Handler Foundation

**Files:**
- Modify: `assets/scar/build_orders/objective_engine.scar`
- Modify: `tests/test_build_order_objectives.py`
- Modify: `docs/build_order_check_handlers.md`

**Interfaces:**
- Consumes: existing `BUILD_ORDER_STATE.childByCheckID`, `BuildOrder_TryAdvance`, and `Obj_SetState`.
- Produces: `BuildOrder_SetCheckComplete(checkID, completed)` and compatibility wrapper `BuildOrder_NotifyComplete(checkID)`.

- [ ] **Step 1: Add failing reversible-state contract tests**

Add tests that extract both functions and require these transitions:

```python
def test_state_api_is_idempotent_reversible_and_advances_only_on_completion(self) -> None:
    body = function_body(self.engine, "BuildOrder_SetCheckComplete")
    self.assertIn("if child == nil or child.completed == completed then", body)
    self.assertIn("child.completed = completed", body)
    self.assertIn("OS_Complete", body)
    self.assertIn("OS_Incomplete", body)
    self.assertIn("if completed == true then", body)
    self.assertIn("BuildOrder_TryAdvance()", body)

def test_notify_complete_wraps_explicit_state_api(self) -> None:
    body = function_body(self.engine, "BuildOrder_NotifyComplete")
    self.assertIn("BuildOrder_SetCheckComplete(checkID, true)", body)
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `python -m unittest tests.test_build_order_objectives -v`

Expected: failure because `BuildOrder_SetCheckComplete` does not exist.

- [ ] **Step 3: Implement the explicit state API**

Implement this behavior in `objective_engine.scar`:

```lua
function BuildOrder_SetCheckComplete(checkID, completed)
	local child = BUILD_ORDER_STATE.childByCheckID[checkID]
	if child == nil or child.completed == completed then
		return
	end

	child.completed = completed
	if completed == true then
		Obj_SetState(child.objectiveID, OS_Complete)
		BuildOrder_TryAdvance()
	else
		Obj_SetState(child.objectiveID, OS_Incomplete)
	end
end

function BuildOrder_NotifyComplete(checkID)
	BuildOrder_SetCheckComplete(checkID, true)
end
```

- [ ] **Step 4: Run focused and full static suites**

Run: `python -m unittest tests.test_build_order_objectives -v`

Run: `python -m unittest discover -s tests -v`

Expected: all tests pass.

- [ ] **Step 5: Commit the shared foundation**

```powershell
git add assets/scar/build_orders/objective_engine.scar tests/test_build_order_objectives.py docs/build_order_check_handlers.md
git commit -m "feat: support reversible build-order checks"
```

Record the resulting SHA as `GRI83_FOUNDATION`. Every issue worktree starts at that exact commit.

---

### Task 2: GRI-55 `vils` Check

**Branch/worktree:** `codex/gri-55-vils-check` / `.worktrees/gri-55-vils-check`

**Files:**
- Create: `assets/scar/build_orders/checks/vils.scar`
- Modify: `tools/build_orders/compiler.py`
- Create: `tests/test_build_order_vils.py`
- Modify: `tests/test_build_order_compiler.py`

**Interfaces:**
- Consumes: `BuildOrder_SetCheckComplete`, `context.localPlayer`, payload `{food=?, gold=?, wood=?, stone=?}`.
- Produces: registered `vils` polling handler and one descriptor per YAML `vils` mapping.

- [ ] **Step 1: Research the exact official APIs**

Use AoE4 MCP `find_api`, `api_context`, and `find_usage` for player-owned villagers, current gather assignment, and safe repeating rules. Record exact signatures and official usage paths in the agent report before coding.

- [ ] **Step 2: Add RED compiler tests**

Compile a step with all four resources and assert exactly one descriptor, kind `vils`, required metadata, payload keys in canonical resource order, and title equivalent to `7 F | 3 G | 4 W | 2 S` using the supported icon/label representation.

- [ ] **Step 3: Add RED SCAR contract tests**

Require registration for `vils`, storage of `context.localPlayer`, a player-owned query, all configured thresholds combined into one Boolean, calls with both `true` and `false`, unique per-check polling state, and cleanup of the exact polling rule.

- [ ] **Step 4: Implement compiler and focused handler**

Replace per-resource vils expansion with one `CheckDescriptor("vils", title, False, thresholds)`. Implement a repeating player-scoped poll that calculates every configured threshold and reports the combined result.

- [ ] **Step 5: Validate statically and commit**

Run the focused tests, full `unittest` discovery, and AoE4 `check_code` on `vils.scar`. Commit as `feat: implement GRI-55 villager check` and queue validation with an opponent gatherer guard.

---

### Task 3: GRI-56 `built` Check

**Branch/worktree:** `codex/gri-56-built-check` / `.worktrees/gri-56-built-check`

**Files:**
- Create: `assets/scar/build_orders/checks/built.scar`
- Modify: `tools/build_orders/compiler.py`
- Create: `tests/test_build_order_built.py`
- Modify: `tests/test_build_order_compiler.py`

**Interfaces:**
- Consumes: payload `{id=...}` or `{oneof={...}}`, plus `count`, optional presentation hints `vils` and `location`.
- Produces: registered latched `built` event handler.

- [ ] **Step 1: Research player-scoped construction-complete events**

Find the official listener/delegate signature, event arguments, owner comparison, and blueprint comparison. Record the verified event path.

- [ ] **Step 2: Add RED compiler/title tests**

Cover singular, plural count, `oneof`, `with <vils> vils`, and `on <resource>` ordering. Assert `vils` text precedes `location` text.

- [ ] **Step 3: Add RED event-handler tests**

Require player comparison before blueprint comparison, ignore opponent and unrelated events, decrement only matching human completions, accept any `oneof` ID, latch at zero, ignore duplicates after completion, and unregister on deactivate.

- [ ] **Step 4: Implement and statically validate**

Implement per-check remaining counts and the verified event callback. Run focused/full tests and AoE4 `check_code`.

- [ ] **Step 5: Commit and queue validation**

Commit as `feat: implement GRI-56 building check`. The validation request constructs the same building for an opponent first and the human player second.

---

### Task 4: GRI-57 `age_up` Check

**Branch/worktree:** `codex/gri-57-age-up-check` / `.worktrees/gri-57-age-up-check`

**Files:**
- Create: `assets/scar/build_orders/checks/age_up.scar`
- Modify: `tools/build_orders/compiler.py`
- Create: `tests/test_build_order_age_up.py`
- Modify: `tests/test_build_order_compiler.py`

**Interfaces:**
- Consumes: payload `id` or `oneof`, optional `vils` and `location`.
- Produces: human-scoped latched handler that completes on started progress, not queue insertion.

- [ ] **Step 1: Research age-up signals by civilization mechanism**

Verify official APIs/usages for landmark construction start and non-building age-up progress. Explicitly cover Knights Templar, Golden Horde, and Abbasid in the research report.

- [ ] **Step 2: Add RED presentation tests**

Cover one ID, slash-joined `oneof`, vils suffix, location suffix, and suffix ordering.

- [ ] **Step 3: Add RED runtime contracts**

Require human-player ownership, positive progress rather than queued state, any-of ID matching, opponent rejection, latched completion, and lifecycle cleanup for every mechanism selected in research.

- [ ] **Step 4: Implement the smallest verified mechanism set**

Use separate internal adapters for landmark construction and verified non-building progression, both feeding one per-check completion function. Unsupported mechanisms remain explicit and non-blocking according to the spec; never auto-complete them.

- [ ] **Step 5: Validate, commit, and queue civilization scenarios**

Run focused/full tests and `check_code`; commit as `feat: implement GRI-57 age-up check`. Queue distinct validation scenarios for ordinary landmark, Knights Templar, Golden Horde, and Abbasid.

---

### Task 5: GRI-58 `resources` Check

**Branch/worktree:** `codex/gri-58-resources-check` / `.worktrees/gri-58-resources-check`

**Files:**
- Create: `assets/scar/build_orders/checks/resources.scar`
- Modify: `tools/build_orders/compiler.py`
- Create: `tests/test_build_order_resources.py`

**Interfaces:**
- Consumes: payload `{resource=..., count=...}`.
- Produces: one reversible polling handler instance per resource descriptor.

- [ ] **Step 1: Verify the official player-resource query and repeating-rule APIs**

Record signatures and official usage for the exact stored player handle.

- [ ] **Step 2: Add RED compiler and handler tests**

Require `Collect at least <count> <resource>`, YAML-order descriptors, player-specific resource query, true/false transitions across spending, unique rules, and cleanup.

- [ ] **Step 3: Implement polling handler**

Poll only the stored player bank for the descriptor's resource and call `BuildOrder_SetCheckComplete(check.id, amount >= check.payload.count)`.

- [ ] **Step 4: Validate and commit**

Run focused/full tests and `check_code`; commit as `feat: implement GRI-58 resource check`.

- [ ] **Step 5: Queue reversible validation**

Request a playtest that reaches the threshold, spends below it before the step advances by another required child, and confirms the resource child becomes incomplete. Include an opponent-bank guard.

---

### Task 6: GRI-59 `upgrades` Check

**Branch/worktree:** `codex/gri-59-upgrades-check` / `.worktrees/gri-59-upgrades-check`

**Files:**
- Create: `assets/scar/build_orders/checks/upgrades.scar`
- Modify: `tools/build_orders/compiler.py`
- Create: `tests/test_build_order_upgrades.py`

**Interfaces:**
- Consumes: payload `{id=..., queued=<bool>}` and descriptor `optional` metadata.
- Produces: completed-research detection plus the smallest reliable queued-research behavior.

- [ ] **Step 1: Research completed and queued technology APIs**

Verify player-specific research status, research-complete events, and queue inspection. Record whether queued state is reliably observable.

- [ ] **Step 2: Add RED presentation/metadata tests**

Cover `Research <upgrade>`, `[Optional] Research <upgrade>`, and `Queue <upgrade> for research`; assert `optional` affects engine blocking independently of `queued`.

- [ ] **Step 3: Add RED player-scope and lifecycle tests**

Require stored-player queries/events, opponent rejection, canonical ID matching, latched completion, and listener/rule cleanup.

- [ ] **Step 4: Implement verified paths**

Implement completed research using the strongest verified player-scoped API. Implement queued detection only if official evidence supports it; otherwise make the queued descriptor visibly non-blocking with an explicit limitation string and tests.

- [ ] **Step 5: Validate, commit, and queue both variants**

Run focused/full tests and `check_code`; commit as `feat: implement GRI-59 upgrade check`. Queue completed and queued/limitation scenarios with an opponent guard.

---

### Task 7: GRI-60 `produce` Check

**Branch/worktree:** `codex/gri-60-produce-check` / `.worktrees/gri-60-produce-check`

**Files:**
- Create: `assets/scar/build_orders/checks/produce.scar`
- Modify: `tools/build_orders/compiler.py`
- Create: `tests/test_build_order_produce.py`

**Interfaces:**
- Consumes: payload `{id=..., count=..., constant=<bool>, queued=<bool>}`.
- Produces: human-player production counter and verified constant/queue variants.

- [ ] **Step 1: Research production complete, queue, and continuous-production signals**

Verify event producer/player arguments and whether current queues and idle gaps can be inspected reliably.

- [ ] **Step 2: Add RED compiler/title tests**

Cover `Produce <count> <unit>`, `Constantly produce <unit>`, `Queue <unit> for production`, and `Have <count> <unit> queued`, including precedence when flags coexist.

- [ ] **Step 3: Add RED normal-production tests**

Require human-player comparison before unit ID comparison, opponent/unrelated rejection, exact count threshold, duplicate/late-event safety, and cleanup.

- [ ] **Step 4: Implement normal and capability-supported variants**

Normal production uses a per-check remaining counter. Queue and constant variants use only verified player-scoped APIs; unsupported variants become explicitly non-blocking and never auto-complete.

- [ ] **Step 5: Validate, commit, and queue variant scenarios**

Run focused/full tests and `check_code`; commit as `feat: implement GRI-60 production check`. Queue normal, queued, and constant scenarios or their verified limitation presentation.

---

### Task 8: GRI-62 `units` Check

**Branch/worktree:** `codex/gri-62-units-check` / `.worktrees/gri-62-units-check`

**Files:**
- Create: `assets/scar/build_orders/checks/units.scar`
- Modify: `tools/build_orders/compiler.py`
- Create: `tests/test_build_order_units.py`

**Interfaces:**
- Consumes: payload `{id=..., count=...}`.
- Produces: reversible count of living matching units controlled by the human player.

- [ ] **Step 1: Research player-owned living-unit group APIs**

Verify group construction/filtering, blueprint comparison, alive status, and ownership after conversion.

- [ ] **Step 2: Add RED compiler and runtime tests**

Require `Have <count> <unit> active`, human-owned group scope, alive and canonical-ID filters, opponent exclusion, true/false transitions after death or conversion, unique rules, and cleanup.

- [ ] **Step 3: Implement polling handler**

Recompute the living controlled count each poll and report `count >= check.payload.count`; do not accumulate historical production events.

- [ ] **Step 4: Validate and commit**

Run focused/full tests and `check_code`; commit as `feat: implement GRI-62 active-unit check`.

- [ ] **Step 5: Queue reversible ownership validation**

Request threshold, death/below-threshold, and opponent matching-unit scenarios.

---

### Task 9: GRI-63 `hints` Optional Objectives

**Branch/worktree:** `codex/gri-63-hints` / `.worktrees/gri-63-hints`

**Files:**
- Modify: `tools/build_orders/compiler.py`
- Create: `tests/test_build_order_hints.py`
- Modify: `tests/test_build_order_objectives.py`

**Interfaces:**
- Consumes: YAML list of strings.
- Produces: one descriptor per hint with title `[HINT] <text>`, `optional=True`, and no registered runtime handler.

- [ ] **Step 1: Add RED compiler tests**

Assert exact order, title, payload `{text: ...}`, and optional metadata for multiple hints.

- [ ] **Step 2: Add RED engine contract test**

Construct a step containing only optional missing-handler descriptors and require `BuildOrder_TryAdvance` not to wait for completion callbacks.

- [ ] **Step 3: Implement descriptor metadata and title**

Emit `CheckDescriptor("hints", f"[HINT] {text}", True, {"text": text})` for every string.

- [ ] **Step 4: Run focused/full tests and commit**

Commit as `feat: implement GRI-63 optional hints`.

- [ ] **Step 5: Queue display validation**

Request confirmation that hints display and that a step advances without interacting with them. Opponent guard is `not applicable: presentation-only descriptor`.

---

### Task 10: GRI-80 `rallypoint` Check

**Branch/worktree:** `codex/gri-80-rallypoint-check` / `.worktrees/gri-80-rallypoint-check`

**Files:**
- Create: `assets/scar/build_orders/checks/rallypoint.scar`
- Modify: `tools/build_orders/compiler.py`
- Create: `tests/test_build_order_rallypoint.py`

**Interfaces:**
- Consumes: payload `{resource=..., tc_index=<one-based integer>, tc_count=<integer>}`.
- Produces: reversible rally-resource checks over human-owned town centers in stable construction order.

- [ ] **Step 1: Research town-center discovery, construction ordering, and rally target APIs**

Verify human-player ownership, landmark/main-TC classification, stable ordering for later town centers, and resource interpretation of the rally target.

- [ ] **Step 2: Add RED compiler/title tests**

For one item require `Rally new vils to <resource>`. For multiple items require `Rally Main <tc> to <resource>` for index 1 and `Rally <tc> #2 to <resource>` for index 2, with explicit index/count payload.

- [ ] **Step 3: Add RED runtime tests**

Require player-owned TC filtering, deterministic index selection, opponent-TC exclusion, current rally resource comparison, true/false transitions, unique rule state, and cleanup.

- [ ] **Step 4: Implement verified polling behavior**

Use the strongest supported rally-target API. If resource intent cannot be observed reliably, keep the descriptor visibly non-blocking with an explicit limitation; never infer completion from an opponent or from TC existence alone.

- [ ] **Step 5: Validate, commit, and queue one-TC/two-TC scenarios**

Run focused/full tests and `check_code`; commit as `feat: implement GRI-80 rallypoint check`. Queue a matching opponent TC rally as the guard.

---

### Task 11: Per-Issue Review and Validation Queue

**Files:**
- Create outside Git: one task brief, report, and review package per issue in the SDD workspace.
- Do not modify source branches except through their persistent implementer fix loops.

**Interfaces:**
- Consumes: issue branch commit, static test evidence, AoE4 API-check evidence.
- Produces: clean spec/quality review and one queued validation request.

- [ ] **Step 1: Review each branch against its issue brief and global constraints**

Use a separate reviewer with the brief, report, and full branch diff package. Require both spec compliance and code-quality verdicts.

- [ ] **Step 2: Route findings through the persistent issue agent**

Critical/Important or spec failures return to the same implementer for up to the documented fix-loop cap. Re-review only the fix diff.

- [ ] **Step 3: Queue only clean branches**

Present issue, worktree, commit, scenario, opponent guard, expected UI/transitions, and limitations to the user.

- [ ] **Step 4: Build only the user-selected request**

The main task invokes the AoE4 mod build from the selected absolute worktree path. No other queued branch is built proactively.

- [ ] **Step 5: Forward playtest feedback verbatim**

Successful validation marks that issue eligible for integration. Failed validation returns to the same agent, static checks, review, and queue.

---

### Task 12: Integrate Validated Checks

**Branch/worktree:** `codex/gri-83-integration` / `.worktrees/gri-83-integration`, created from `GRI83_FOUNDATION`.

**Files:**
- Modify: `assets/scar/winconditions/Macro Trainer.scar`
- Modify: `tools/build_orders/compiler.py`
- Modify: combined build-order fixtures and tests as required by merged behavior.
- Import: every validated `assets/scar/build_orders/checks/*.scar` module except hints.

**Interfaces:**
- Consumes: all nine user-validated issue commits.
- Produces: one coherent GRI-83 branch with ordered imports and all descriptor variants.

- [ ] **Step 1: Integrate branches in descriptor order**

Apply GRI-55, 56, 57, 58, 59, 60, 62, 63, and 80. Resolve compiler conflicts by retaining every issue's tested branch and exact YAML field order.

- [ ] **Step 2: Add ordered handler imports**

Import the eight runtime modules after `objective_engine.scar` and before startup can activate a build order. Hints intentionally have no handler import.

- [ ] **Step 3: Add a combined fixture and integration contract**

Compile a build order containing every supported check and assert stable descriptor order, unique IDs, correct optional metadata, and imports for every runtime kind.

- [ ] **Step 4: Run complete verification**

Run `python -m unittest discover -s tests -v`, AoE4 `check_code` across all changed SCAR, and a final whole-branch code review.

- [ ] **Step 5: Queue final combined mod validation**

After static review is clean, build the integration worktree through the main task and hand off a combined playtest matrix, including opponent guards for every gameplay check.

- [ ] **Step 6: Commit integration**

```powershell
git add assets/scar tools/build_orders tests
git commit -m "feat: integrate GRI-83 build-order checks"
```
