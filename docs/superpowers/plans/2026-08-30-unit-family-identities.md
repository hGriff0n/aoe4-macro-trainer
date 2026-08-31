# Unit Family Identities Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `produce` and `units` treat official age-tier squad blueprints as one author-facing gameplay unit family.

**Architecture:** Advance the generated identity catalog to schema version 2 and represent each squad `baseId` as one family containing aliases and all canonical SCAR identifiers. The compiler emits canonical `ids` lists for `produce` and `units`; their isolated runtime handlers resolve and structurally match any family PBG while retaining their existing event/polling and human-player contracts.

**Tech Stack:** Python 3 standard library, SQLite-backed official identity extraction, JSON catalog, YAML build-order compiler, AoE4 SCAR, `unittest`.

**Spec:** `docs/superpowers/specs/2026-08-30-unit-family-identities-design.md`

## Global Constraints

- Unit IDs used by `produce` and `units` represent gameplay unit families rather than one age-specific squad blueprint.
- Family membership comes only from official `baseId`; do not infer it by removing numeric suffixes.
- Existing age-specific YAML IDs remain accepted as aliases, while new content uses the family ID.
- Runtime payload identity values are canonical SCAR identifiers; author aliases are presentation/compiler inputs only.
- Both handlers compare all three PBG fields: `PropertyBagGroupID`, `PropertyBagGroupModPackID`, and `PropertyBagGroupType`.
- Every runtime query/event remains explicitly scoped to `context.localPlayer`; opponent actions and squads never contribute.
- GRI-60 remains event-driven with named callbacks and next-tick reconciliation; do not add periodic polling or `GE_BuildItemStart`.
- GRI-62 remains a reversible named shared poll with first-active/last-inactive lifecycle.
- Entity, building, upgrade, and age-up identity resolution remains scalar and unchanged.
- Subagents run static tests only. Only the main thread invokes the Content Editor build wrapper after review.

---

## File Structure

- `tools/build_orders/identities.py`: validates schema v2, exposes scalar identity resolution and immutable squad-family resolution.
- `tools/build_orders/identity_generator.py`: groups official squad records by civilization and `baseId`, emitting deterministic aliases/canonical IDs.
- `tools/build_orders/data/game_identities.json`: committed generated schema-v2 catalog.
- `tools/build_orders/compiler.py`: converts squad-family author IDs/aliases into display family IDs plus canonical runtime `ids`.
- `tests/test_game_identities.py`: generator/loader determinism, validation, family aliases, and scalar compatibility.
- `tests/test_build_order_compiler.py`: shared compiler payload/title/error contracts.
- `assets/scar/build_orders/checks/produce.scar`: GRI-60 family PBG caching and matching.
- `tests/test_build_order_produce.py`: GRI-60 family completion/queue behavior and human filtering.
- `assets/scar/build_orders/checks/units.scar`: GRI-62 family PBG caching and living-squad matching.
- `tests/test_build_order_units.py`: GRI-62 cross-age reversible count behavior and human filtering.
- `docs/build_order_schema.yaml`: documents family IDs and legacy alias compatibility for `produce`/`units`.

### Task 1: Schema-v2 Catalog Loader and Family API

**Worktree:** `E:/Docs/github/aoemod/aoe4-macro-trainer/.worktrees/gri-83-objective-checks`

**Files:**
- Modify: `tools/build_orders/identities.py`
- Modify: `tests/fixtures/game_identities/minimal.json`
- Modify: `tests/test_game_identities.py`

**Interfaces:**
- Produces: `SquadFamilyIdentity(family_id: str, canonical_ids: tuple[str, ...])`.
- Produces: `IdentityCatalog.resolve_squad_family(civ: str, identifier: str) -> SquadFamilyIdentity`.
- Preserves: `IdentityCatalog.resolve(civ: str, category: str, identifier: str) -> str` for `entity` and `upgrade`.

- [ ] **Step 1: Add failing loader and alias-resolution tests**

Use a schema-v2 fixture shaped as:

```json
{
  "schema_version": 2,
  "source": "official_base_data",
  "civilizations": {
    "english": {
      "entity": {"town_center": "building_town_center_eng"},
      "squad": {
        "spearman": {
          "aliases": ["spearman", "spearman_2", "spearman_3"],
          "canonical_ids": ["unit_spearman_2_eng", "unit_spearman_3_eng"]
        },
        "scout": {
          "aliases": ["scout"],
          "canonical_ids": ["unit_scout_1_eng"]
        }
      },
      "upgrade": {"wheelbarrow": "upgrade_wheelbarrow_eng"}
    }
  }
}
```

Assert `spearman`, `spearman_2`, and `spearman_3` resolve to the same immutable result, Scout is a one-member family, and scalar entity/upgrade resolution is unchanged. Add failures for an alias appearing in two families, missing base alias, empty canonical list, duplicate canonical IDs, unsorted lists, and calling scalar `resolve(..., "squad", ...)`.

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
python -m unittest tests.test_game_identities.IdentityCatalogTests -v
```

Expected: failures because schema version 2 and `resolve_squad_family` are unsupported.

- [ ] **Step 3: Implement immutable family loading**

Add:

```python
SCHEMA_VERSION = 2

@dataclass(frozen=True)
class SquadFamilyIdentity:
    family_id: str
    canonical_ids: tuple[str, ...]
```

During load, validate normalized family/alias IDs, require the family ID in `aliases`, require sorted unique non-empty alias and canonical lists, create one `SquadFamilyIdentity` per family, and create a per-civilization alias index. `resolve_squad_family` normalizes the civilization, validates the supplied already-normalized author ID, and returns the indexed immutable family. Keep entity/upgrade mappings frozen and scalar.

- [ ] **Step 4: Run focused tests and verify GREEN**

```powershell
python -m unittest tests.test_game_identities.IdentityCatalogTests -v
```

Expected: all catalog loader tests pass.

- [ ] **Step 5: Commit**

```powershell
git add -- tools/build_orders/identities.py tests/fixtures/game_identities/minimal.json tests/test_game_identities.py
git commit -m "feat: load squad identity families"
```

### Task 2: Deterministic Official Family Generation

**Worktree:** `E:/Docs/github/aoemod/aoe4-macro-trainer/.worktrees/gri-83-objective-checks`

**Files:**
- Modify: `tools/build_orders/identity_generator.py`
- Modify: `tests/test_game_identities.py`
- Regenerate: `tools/build_orders/data/game_identities.json`

**Interfaces:**
- Consumes: schema-v2 squad family shape from Task 1.
- Produces: each official squad `baseId` as one family with sorted aliases and canonical IDs.

- [ ] **Step 1: Add failing generator tests**

Feed official-style rows for `spearman_1`, `spearman_2`, and `spearman_3` sharing `baseId: "spearman"`. Assert the generated English squad document is exactly:

```python
{
    "spearman": {
        "aliases": ["spearman", "spearman_1", "spearman_2", "spearman_3"],
        "canonical_ids": [
            "unit_spearman_1_eng",
            "unit_spearman_2_eng",
            "unit_spearman_3_eng",
        ],
    }
}
```

Add a reversed-input determinism test, a one-member Scout family test, and an alias collision test using two distinct `baseId` groups that claim the same normalized item ID.

- [ ] **Step 2: Run tests and verify RED**

```powershell
python -m unittest tests.test_game_identities.IdentityGeneratorTests -v
```

Expected: failures because the generator emits scalar item mappings.

- [ ] **Step 3: Generate squad families while preserving scalar categories**

For `identity_category == "squad"`, group by `(civilization, baseId)`, construct aliases from normalized `baseId` plus normalized item IDs, construct canonical IDs from `attribName`, sort/deduplicate both, and emit the family object. Keep existing entity/upgrade grouping and scalar conflict rules unchanged.

- [ ] **Step 4: Regenerate and validate the committed catalog**

Use the existing AoE4 MCP sanitized official-data index, then load the output with `IdentityCatalog.load`. Run generation twice and compare file hashes; they must be identical.

```powershell
python tools/generate_game_identities.py --database E:/Docs/github/aoemod/aoe4-mcp/data/index.sanitized.sqlite3 --output tools/build_orders/data/game_identities.json
python -c "from tools.build_orders.identities import IdentityCatalog, DEFAULT_IDENTITY_CATALOG; IdentityCatalog.load(DEFAULT_IDENTITY_CATALOG)"
```

If `E:/Docs/github/aoemod/aoe4-mcp/data/index.sanitized.sqlite3` is absent, stop this task and report the missing source; do not substitute fixture data for the committed catalog.

- [ ] **Step 5: Run focused and full identity tests**

```powershell
python -m unittest tests.test_game_identities -v
```

Expected: all generator and loader tests pass.

- [ ] **Step 6: Commit**

```powershell
git add -- tools/build_orders/identity_generator.py tools/build_orders/data/game_identities.json tests/test_game_identities.py
git commit -m "feat: generate official squad families"
```

### Task 3: Compile Family Titles and Canonical ID Lists

**Worktree:** `E:/Docs/github/aoemod/aoe4-macro-trainer/.worktrees/gri-83-objective-checks`

**Files:**
- Modify: `tools/build_orders/compiler.py`
- Modify: `tests/test_build_order_compiler.py`
- Modify: `docs/build_order_schema.yaml`

**Interfaces:**
- Consumes: `IdentityCatalog.resolve_squad_family` from Task 1.
- Produces: `produce`/`units` payload field `ids: list[str]` and family-derived display labels.

- [ ] **Step 1: Add failing compiler tests**

Construct a test catalog with `spearman` aliases `spearman`, `spearman_1`, and `spearman_2`. Compile both family and legacy YAML IDs and assert both produce:

```python
{
    "ids": ["unit_spearman_1_eng", "unit_spearman_2_eng"],
    "count": 2,
    "constant": False,
    "queued": True,
}
```

with `Queue 2 spearmen`, and that `units` produces the same `ids` with `Have 2 spearman active`. Assert an unknown alias reports the exact `steps[...].produce[...].id` or `steps[...].units[...].id` path.

- [ ] **Step 2: Run tests and verify RED**

```powershell
python -m unittest tests.test_build_order_compiler -v
```

Expected: failures because squad payloads still contain one scalar `id` and age-specific titles.

- [ ] **Step 3: Implement squad-family compilation**

Add a focused helper:

```python
def _resolve_squad_family_payload(payload, *, civ, identities, file, path):
    author_id = payload.pop("id")
    family = identities.resolve_squad_family(civ, author_id)
    payload["ids"] = list(family.canonical_ids)
    return family.family_id
```

Use it only for `produce` and `units`. Derive title labels from returned `family_id`. Keep current queued/constant/count/optional formatting, including catalog-safe pluralization, and leave other identity categories on `_resolve_identity_payload`.

- [ ] **Step 4: Document author-facing family IDs**

Update `docs/build_order_schema.yaml` so `produce[].id` and `units[].id` describe official gameplay family IDs, give `spearman` as the example, and state that generated age-specific aliases remain temporarily accepted for compatibility.

- [ ] **Step 5: Run compiler and complete common suites**

```powershell
python -m unittest tests.test_build_order_compiler tests.test_game_identities -v
python -m unittest discover -s tests
git diff --check
```

Expected: all tests pass and no whitespace errors.

- [ ] **Step 6: Commit and publish the reviewed common base**

```powershell
git add -- tools/build_orders/compiler.py tests/test_build_order_compiler.py docs/build_order_schema.yaml
git commit -m "feat: compile gameplay unit families"
```

After independent review, the main thread pushes `codex/gri-83-objective-checks`. Runtime branches merge this exact reviewed head.

### Task 4: GRI-60 Production Family Matching

**Worktree:** `E:/Docs/github/aoemod/aoe4-macro-trainer/.worktrees/gri-60-produce-check`

**Files:**
- Modify: `assets/scar/build_orders/checks/produce.scar`
- Modify: `tests/test_build_order_produce.py`

**Interfaces:**
- Consumes: Task 3 payload `ids: list[str]`.
- Produces: cached `state.pbgs` and `Produce_MatchesPBG(pbgs, pbg) -> boolean`.

- [ ] **Step 1: Merge the reviewed common family head**

```powershell
git merge codex/gri-83-objective-checks
```

Resolve compiler/title tests in favor of the reviewed common family payload while retaining GRI-60's check-ID-keyed pending recount and validated title grammar.

- [ ] **Step 2: Add failing cross-age runtime tests**

Assert activation resolves every `check.payload.ids` member with `BP_GetSquadBlueprint`. Extend the behavior harness so a queued Dark Age Spearman, a completed Feudal Spearman, and a Castle Spearman each match one `spearman` family, while an Archer and opponent Spearman do not. Assert queue removal still reverses the queued objective.

- [ ] **Step 3: Run tests and verify RED**

```powershell
python -m unittest tests.test_build_order_produce -v
```

Expected: failures because GRI-60 caches one `state.pbg` from `payload.id`.

- [ ] **Step 4: Implement family PBG matching**

Add named helpers equivalent to:

```lua
function Produce_ResolvePBGs(ids)
    local pbgs = {}
    for _, id in ipairs(ids) do
        table.insert(pbgs, BP_GetSquadBlueprint(id))
    end
    return pbgs
end

function Produce_MatchesPBG(pbgs, pbg)
    for _, candidate in ipairs(pbgs) do
        if Produce_BlueprintsEqual(candidate, pbg) then
            return true
        end
    end
    return false
end
```

Store `pbgs = Produce_ResolvePBGs(check.payload.ids)`. Replace every single-PBG queue/completion comparison with `Produce_MatchesPBG(state.pbgs, observedPBG)`. Do not change event registration, human-owner filtering, check-ID pending reconciliation, deduplication, or cleanup.

- [ ] **Step 5: Run verification**

```powershell
python -m unittest tests.test_build_order_produce tests.test_build_order_compiler -v
python -m unittest discover -s tests
git diff --check
```

Expected: all tests pass.

- [ ] **Step 6: Commit and queue main-thread validation**

```powershell
git add -- assets/scar/build_orders/checks/produce.scar tests/test_build_order_produce.py
git commit -m "feat: match production unit families"
```

Subagent reports the commit without building or pushing. After independent review, the main thread builds GRI-60 with `tools/build_mod.py` and the external build-order directory.

### Task 5: GRI-62 Living Unit Family Matching

**Worktree:** `E:/Docs/github/aoemod/aoe4-macro-trainer/.worktrees/gri-62-units-check`

**Files:**
- Modify: `assets/scar/build_orders/checks/units.scar`
- Modify: `tests/test_build_order_units.py`

**Interfaces:**
- Consumes: Task 3 payload `ids: list[str]`.
- Produces: cached `state.pbgs` and `Units_MatchesPBG(pbgs, pbg) -> boolean`.

- [ ] **Step 1: Merge the reviewed common family head**

```powershell
git merge codex/gri-83-objective-checks
```

Retain GRI-62's structural three-field equality fix and documented `Have <count> <unit> active` title grammar from the common compiler.

- [ ] **Step 2: Add failing cross-age and ownership tests**

Extend the behavior harness with distinct PBG wrapper objects for Dark, Feudal, and Castle Spearmen in one family. Assert two owned/alive tiers satisfy `Have 2 spearman active`; an opponent Spearman and converted-away Spearman never count; death or loss of ownership reverses completion.

- [ ] **Step 3: Run tests and verify RED**

```powershell
python -m unittest tests.test_build_order_units -v
```

Expected: failures because GRI-62 caches and compares one `state.pbg`.

- [ ] **Step 4: Implement family PBG matching**

Add `Units_ResolvePBGs(ids)` and `Units_MatchesPBG(pbgs, pbg)` using `Units_BlueprintsEqual`. Store `pbgs` on activation and count a squad when its structurally read blueprint matches any candidate. Preserve the existing order: reject non-human ownership before blueprint/alive processing.

- [ ] **Step 5: Run verification**

```powershell
python -m unittest tests.test_build_order_units tests.test_build_order_compiler -v
python -m unittest discover -s tests
git diff --check
```

Expected: all tests pass.

- [ ] **Step 6: Commit and queue main-thread validation**

```powershell
git add -- assets/scar/build_orders/checks/units.scar tests/test_build_order_units.py
git commit -m "feat: count living unit families"
```

Subagent reports the commit without building or pushing. After independent review, the main thread builds GRI-62 with `tools/build_mod.py` and the external build-order directory.

### Task 6: Integration and Validation

**Files:**
- Verify: `tools/build_orders/data/game_identities.json`
- Verify: `assets/scar/build_orders/checks/produce.scar`
- Verify: `assets/scar/build_orders/checks/units.scar`
- Verify: `docs/build_order_schema.yaml`

**Interfaces:**
- Consumes: reviewed common, GRI-60, and GRI-62 commits.
- Produces: published issue branches and evidence-backed validation results.

- [ ] **Step 1: Run independent reviews**

Review the common catalog/compiler range first. After it is clean and pushed, review each runtime branch against the exact common head it merged. Resolve every important finding through the owning subagent and scoped re-review.

- [ ] **Step 2: Verify deterministic data and all static suites**

```powershell
python -m unittest discover -s tests
git diff --check
```

Regenerate the catalog a second time from the same official database and verify no diff.

- [ ] **Step 3: Build only from the selected issue worktree**

For GRI-60:

```powershell
python 'E:\Docs\github\aoemod\aoe4-macro-trainer\.worktrees\gri-60-produce-check\tools\build_mod.py' --build-orders 'E:\Docs\github\aoemod\build orders'
```

For GRI-62:

```powershell
python 'E:\Docs\github\aoemod\aoe4-macro-trainer\.worktrees\gri-62-units-check\tools\build_mod.py' --build-orders 'E:\Docs\github\aoemod\build orders'
```

- [ ] **Step 4: Validate in game**

For GRI-60, queue and complete at least two tiers of one family and cancel one queued item; verify exact title text, completion, and reversal. For GRI-62, begin with an owned Dark Age member, age/upgrade into a later tier, and verify the same objective remains correct; confirm an opponent performing the same action has no effect.

- [ ] **Step 5: Publish validated branches**

After the user reports success, push the reviewed common, GRI-60, and GRI-62 heads to their existing GitHub branches. Do not create the full-suite-to-main PR until every remaining GRI-83 child validation is complete.
