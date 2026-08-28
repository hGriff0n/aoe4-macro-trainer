# Game Identity Catalog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Validate human-readable build-order IDs against a committed civilization-aware game catalog, compile them to canonical SCAR blueprint identifiers, and make age-up behavior depend on civilization rather than YAML capability metadata.

**Architecture:** A deterministic developer-only generator converts the AoE4 MCP SQLite base-data index into a committed JSON catalog keyed by civilization, blueprint category, and normalized official base ID. The compiler validates YAML through a focused catalog loader and emits canonical `attribName` strings; SCAR resolves those strings once to PBG tuples. The common GRI-83 branch supplies the interface, after which persistent sub-issue agents update their existing isolated worktrees without building the mod.

**Tech Stack:** Python 3 standard library (`argparse`, `dataclasses`, `json`, `sqlite3`, `unittest`), PyYAML, AoE4 SCAR, Git worktrees

**Spec:** `docs/superpowers/specs/2026-08-28-game-identity-catalog-design.md`

## Global Constraints

- Build-order YAML uses lowercase underscore-normalized official `baseId` values; raw PBG integers, canonical `attribName` strings, and shorthand aliases are rejected.
- Normal builds read the committed catalog and never require the sibling `aoe4-mcp` repository, MCP service, or SQLite database.
- The identity catalog contains no event, polling, capability, or other detection-mechanism field.
- Age-up category and runtime adapter selection use the build order's civilization; YAML has no `capability` field.
- Every runtime callback and query verifies or scopes to `context.localPlayer` before comparing blueprint identity.
- Each GRI-83 sub-issue remains in its existing dedicated worktree and is handled by its persistent sub-agent.
- Sub-agents run static tests but do not invoke the AoE4 Content Editor or build a `.aoe4mod`; validation requests return to the main task.
- Existing per-check PRs continue to target `codex/gri-83-objective-checks`; do not create an event-probe PR or a combined suite-to-main PR.

---

## File Structure

- `tools/build_orders/identities.py`: immutable catalog loader, schema validation, ID normalization, and lookup errors used by the compiler.
- `tools/build_orders/identity_generator.py`: pure conversion from official base-data records into the serialized catalog structure.
- `tools/generate_game_identities.py`: developer CLI that reads the AoE4 MCP SQLite database and atomically writes the committed catalog.
- `tools/build_orders/data/game_identities.json`: generated, committed identity catalog consumed by normal builds.
- `tests/fixtures/game_identities/minimal.json`: small catalog used by focused unit tests.
- `tests/test_game_identities.py`: loader and generator behavior.
- `tools/build_orders/compiler.py`: objective-to-category selection and human-ID-to-canonical-ID compilation.
- `tests/test_build_order_compiler.py`: catalog-backed compiler validation and payload emission.
- `tests/test_build_order_build.py`: generation/build integration using canonical payloads.
- `docs/build_order_schema.yaml`: official normalized-ID contract and removal of capability metadata.
- `README.md`: catalog refresh command and author-facing validation behavior.
- `assets/scar/build_orders/objective_engine.scar`: expose `context.civ` beside `context.localPlayer`.
- `tests/test_build_order_objectives.py`: engine civilization-context lifecycle contract.
- `.worktrees/gri-57-age-up-check/assets/scar/build_orders/checks/age_up.scar`: civilization-selected event adapters and cached PBG tuples.
- `.worktrees/gri-57-age-up-check/tests/test_build_order_age_up.py`: GRI-57 normalized IDs, compiler payloads, event dispatch, and player filtering.
- `.worktrees/gri-56-built-check/assets/scar/build_orders/checks/built.scar`: cached canonical entity PBG tuples.
- `.worktrees/gri-56-built-check/tests/test_build_order_built.py`: GRI-56 canonical payload and cached-PBG contract.
- `.worktrees/gri-59-upgrades-check/assets/scar/build_orders/checks/upgrades.scar`: cached canonical upgrade PBG tuple.
- `.worktrees/gri-59-upgrades-check/tests/test_build_order_upgrades.py`: GRI-59 canonical payload and cached-PBG contract.
- `.worktrees/gri-60-produce-check/assets/scar/build_orders/checks/produce.scar`: cached canonical squad PBG tuple.
- `.worktrees/gri-60-produce-check/tests/test_build_order_produce.py`: GRI-60 canonical payload and cached-PBG contract.
- `.worktrees/gri-62-units-check/assets/scar/build_orders/checks/units.scar`: cached canonical squad PBG tuple used by living-unit polling.
- `.worktrees/gri-62-units-check/tests/test_build_order_units.py`: GRI-62 canonical payload and cached-PBG contract.
- `E:/Docs/github/aoemod/build orders/*.yaml`: migrate guessed shorthand IDs to normalized official base IDs.

### Task 1: Catalog Loader and Lookup Contract

**Worktree:** `E:/Docs/github/aoemod/aoe4-macro-trainer/.worktrees/gri-83-objective-checks`

**Files:**
- Create: `tools/build_orders/identities.py`
- Create: `tests/fixtures/game_identities/minimal.json`
- Create: `tests/test_game_identities.py`

**Interfaces:**
- Consumes: JSON schema `{ "schema_version": 1, "source": "official_base_data", "civilizations": { ... } }`.
- Produces: `IdentityCatalog.load(path: Path) -> IdentityCatalog`, `IdentityCatalog.resolve(civ: str, category: str, identifier: str) -> str`, `normalize_identity_id(value: str) -> str`, `IdentityCatalogError`, and `DEFAULT_IDENTITY_CATALOG`.

- [ ] **Step 1: Write failing loader and lookup tests**

```python
def test_resolves_shared_id_by_civilization(self) -> None:
    catalog = IdentityCatalog.load(FIXTURE)
    self.assertEqual(
        catalog.resolve("english", "squad", "scout"),
        "unit_scout_1_eng",
    )
    self.assertEqual(
        catalog.resolve("abbasid", "squad", "scout"),
        "unit_scout_1_abb",
    )

def test_rejects_non_normalized_human_id(self) -> None:
    with self.assertRaisesRegex(IdentityCatalogError, "normalized official ID"):
        catalog.resolve("english", "entity", "town-center")

def test_rejects_unknown_civilization_category_and_id(self) -> None:
    for args, fragment in (
        (("unknown", "entity", "town_center"), "unknown civilization"),
        (("english", "ability", "scout"), "unknown category"),
        (("english", "entity", "not_real"), "unknown entity ID"),
    ):
        with self.subTest(args=args), self.assertRaisesRegex(IdentityCatalogError, fragment):
            catalog.resolve(*args)
```

The fixture must contain English and Abbasid `scout`, English `town_center` and `council_hall`, Abbasid `economic_wing`, and English `wheelbarrow`, each mapped to a distinct canonical `attribName` string.

- [ ] **Step 2: Run the focused tests and verify the missing module failure**

Run: `python -m unittest tests.test_game_identities -v`

Expected: FAIL with `ModuleNotFoundError` for `tools.build_orders.identities`.

- [ ] **Step 3: Implement immutable loading, structural validation, normalization, and lookup**

```python
SCHEMA_VERSION = 1
DEFAULT_IDENTITY_CATALOG = Path(__file__).with_name("data") / "game_identities.json"
IDENTITY_ID = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")

@dataclass(frozen=True)
class IdentityCatalog:
    civilizations: Mapping[str, Mapping[str, Mapping[str, str]]]

    @classmethod
    def load(cls, path: Path) -> "IdentityCatalog":
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("schema_version") != SCHEMA_VERSION:
            raise IdentityCatalogError(f"{path}: unsupported identity catalog schema version")
        return cls(_freeze_and_validate(document.get("civilizations"), path))

    def resolve(self, civ: str, category: str, identifier: str) -> str:
        normalized_civ = civ.casefold().replace(" ", "_").replace("-", "_")
        if not IDENTITY_ID.fullmatch(identifier):
            raise IdentityCatalogError(f"'{identifier}' is not a normalized official ID")
        # Perform explicit civ, category, and ID checks so errors are actionable.
        return self.civilizations[normalized_civ][category][identifier]
```

Use `MappingProxyType` recursively so callers cannot mutate loaded data. Validate that only `entity`, `squad`, and `upgrade` category keys exist and every leaf is a non-empty string.

- [ ] **Step 4: Run loader tests and the existing compiler suite**

Run: `python -m unittest tests.test_game_identities tests.test_build_order_compiler -v`

Expected: PASS.

- [ ] **Step 5: Commit the loader contract**

```powershell
git add -- tools/build_orders/identities.py tests/fixtures/game_identities/minimal.json tests/test_game_identities.py
git commit -m "feat: add game identity catalog loader"
```

### Task 2: Deterministic Catalog Generator and Committed Data

**Worktree:** `E:/Docs/github/aoemod/aoe4-macro-trainer/.worktrees/gri-83-objective-checks`

**Files:**
- Create: `tools/build_orders/identity_generator.py`
- Create: `tools/generate_game_identities.py`
- Create: `tools/build_orders/data/game_identities.json`
- Modify: `tests/test_game_identities.py`

**Interfaces:**
- Consumes: read-only SQLite table `base_data_entries(category, base_id, attrib_name, details_json, source_set)` and explicit `SOURCE_CIVILIZATIONS` entries.
- Produces: `generate_identity_document(rows: Iterable[Mapping[str, object]]) -> dict[str, object]`, `read_official_rows(database: Path) -> list[dict[str, object]]`, `write_identity_document(document, output: Path) -> None`, and CLI arguments `--database` and `--output`.

- [ ] **Step 1: Write failing generator tests with an in-memory SQLite fixture**

```python
def test_generator_normalizes_base_ids_and_sorts_output(self) -> None:
    document = generate_identity_document([
        row("units", "scout", "unit_scout_1_eng", ["en"]),
        row("buildings", "town-center", "building_town_center_eng", ["en"]),
    ])
    english = document["civilizations"]["english"]
    self.assertEqual(english["entity"]["town_center"], "building_town_center_eng")
    self.assertEqual(english["squad"]["scout"], "unit_scout_1_eng")

def test_generator_rejects_conflicting_normalized_key(self) -> None:
    rows = [
        row("buildings", "town-center", "building_a", ["en"]),
        row("buildings", "town_center", "building_b", ["en"]),
    ]
    with self.assertRaisesRegex(IdentityGenerationError, "conflicting identity"):
        generate_identity_document(rows)

def test_generator_rejects_unknown_source_civ(self) -> None:
    with self.assertRaisesRegex(IdentityGenerationError, "unknown source civilization 'new'"):
        generate_identity_document([row("units", "scout", "unit_scout_new", ["new"])])
```

Also assert that known campaign-only codes are explicitly excluded, malformed relevant records fail, duplicate identical records deduplicate, serialization is byte-identical across input order, and the SQLite connection uses URI `mode=ro`.

- [ ] **Step 2: Run the generator tests and verify they fail**

Run: `python -m unittest tests.test_game_identities -v`

Expected: FAIL because `identity_generator` and its CLI do not exist.

- [ ] **Step 3: Implement source mappings and pure generation**

```python
CATEGORY_MAP = {
    "buildings": "entity",
    "units": "squad",
    "technologies": "upgrade",
}

SOURCE_CIVILIZATIONS = {
    "ab": "abbasid", "ay": "ayyubids", "by": "byzantines",
    "ch": "chinese", "de": "delhi", "en": "english", "fr": "french",
    "hl": "house_of_lancaster", "horde": "golden_horde", "hr": "hre",
    "ja": "japanese", "je": "jeanne_darc", "jin": "jin_dynasty",
    "kt": "templar", "ma": "malians", "macedonian": "macedonian_dynasty",
    "mo": "mongols", "od": "order_of_the_dragon", "ot": "ottomans",
    "ru": "rus", "daimyo": "sengoku_daimyo", "tughlaq": "tughlaq_dynasty",
    "zx": "zhu_xi",
    "aybCmp": None, "crdCmp": None, "rogue": None, "song_cmp": None,
}
```

For every relevant row, parse `details_json`, require `baseId`, `attribName`, and non-empty `civs`, normalize `baseId` by replacing hyphens with underscores, then insert the canonical `attribName` under every included civilization. Reject any source civ code absent from the explicit mapping. Serialize with `json.dumps(document, indent=2, sort_keys=True) + "\n"` and replace the destination through a same-directory temporary file.

- [ ] **Step 4: Implement the read-only developer CLI**

```python
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_IDENTITY_CATALOG,
    )
    args = parser.parse_args(argv)
    document = generate_identity_document(read_official_rows(args.database))
    write_identity_document(document, args.output)
    IdentityCatalog.load(args.output)
    return 0
```

The SQL query must filter `source_set = 'official_base_data'` and the three supported categories, order rows deterministically, and never import `aoe4_mcp`.

- [ ] **Step 5: Run generator tests**

Run: `python -m unittest tests.test_game_identities -v`

Expected: PASS.

- [ ] **Step 6: Generate and inspect the committed catalog**

Run:

```powershell
python tools/generate_game_identities.py --database E:/Docs/github/aoemod/aoe4-mcp/data/index.sanitized.sqlite3
python -c "from tools.build_orders.identities import IdentityCatalog,DEFAULT_IDENTITY_CATALOG; c=IdentityCatalog.load(DEFAULT_IDENTITY_CATALOG); print(c.resolve('english','entity','town_center')); print(c.resolve('abbasid','squad','scout')); print(c.resolve('golden_horde','upgrade','khan_and_torguuds'))"
```

Expected output includes `building_town_center_eng`, `unit_scout_1_abb`, and `upgrade_tent_dark_1_khan_mon_ha_gol`.

- [ ] **Step 7: Prove deterministic regeneration**

Run:

```powershell
$firstDigest = (Get-FileHash tools/build_orders/data/game_identities.json -Algorithm SHA256).Hash
python tools/generate_game_identities.py --database E:/Docs/github/aoemod/aoe4-mcp/data/index.sanitized.sqlite3
$secondDigest = (Get-FileHash tools/build_orders/data/game_identities.json -Algorithm SHA256).Hash
if ($firstDigest -ne $secondDigest) { throw "identity catalog regeneration was not deterministic" }
git diff --check
```

Expected: the digests match and `git diff --check` exits 0.

- [ ] **Step 8: Commit generator and data**

```powershell
git add -- tools/build_orders/identity_generator.py tools/generate_game_identities.py tools/build_orders/data/game_identities.json tests/test_game_identities.py
git commit -m "feat: generate game identity catalog"
```

### Task 3: Catalog-Backed Compiler Validation

**Worktree:** `E:/Docs/github/aoemod/aoe4-macro-trainer/.worktrees/gri-83-objective-checks`

**Files:**
- Modify: `tools/build_orders/compiler.py`
- Modify: `tests/test_build_order_compiler.py`
- Modify: `tests/test_build_order_build.py`
- Modify: `docs/build_order_schema.yaml`
- Modify: `README.md`

**Interfaces:**
- Consumes: `IdentityCatalog.resolve(civ, category, identifier)` from Task 1 and `DEFAULT_IDENTITY_CATALOG` from Task 2.
- Produces: `compile_directory(input_dir: Path, identities: IdentityCatalog | None = None) -> Catalog`; descriptors keep human-readable titles but payload `id` and `oneof` values are canonical SCAR identifiers.

- [ ] **Step 1: Write failing compiler-resolution tests**

```python
def compile(self, files: dict[str, str], identities=None) -> Catalog:
    with tempfile.TemporaryDirectory() as temp:
        directory = Path(temp)
        for name, content in files.items():
            self.write(directory, name, content)
        return compile_directory(directory, identities=identities or self.identities)

def compile_age(self, civ: str, identifier: str) -> CheckDescriptor:
    catalog = self.compile({
        "age.yaml": f"civ: {civ}\ntitle: Age\nsteps:\n  - age_up: {{id: {identifier}}}\n"
    })
    return catalog.build_orders[0].steps[0].checks[0]

def test_resolves_each_check_category_to_canonical_payload(self) -> None:
    catalog = self.compile({"order.yaml": """civ: english
title: IDs
steps:
  - built: [{id: town_center}]
    produce: [{id: scout}]
    units: [{id: scout}]
    upgrades: [{id: wheelbarrow}]
    age_up: {id: council_hall}
"""}, identities=self.identities)
    payloads = [check.payload for check in catalog.build_orders[0].steps[0].checks]
    self.assertEqual(payloads[0]["id"], "building_town_center_eng")
    self.assertEqual(payloads[1]["id"], "unit_scout_1_eng")
    self.assertEqual(payloads[3]["id"], "upgrade_wheelbarrow_eng")
    self.assertEqual(payloads[4]["id"], "building_landmark_age2_eng")

def test_age_up_category_depends_on_civilization(self) -> None:
    english = self.compile_age("english", "council_hall")
    abbasid = self.compile_age("abbasid", "economic_wing")
    self.assertEqual(english.payload["id"], "building_landmark_age2_eng")
    self.assertEqual(abbasid.payload["id"], "upgrade_add_economy_wing")

def test_rejects_capability_and_reports_catalog_context(self) -> None:
    self.assert_invalid(
        "civ: english\ntitle: x\nsteps:\n  - age_up: {id: council_hall, capability: landmark}\n",
        "steps[0].age_up.capability: unknown field",
    )
    self.assert_invalid(
        "civ: english\ntitle: x\nsteps:\n  - units: [{id: economic_wing}]\n",
        "civilization 'english', units check, expected squad ID 'economic_wing'",
    )
```

Add `oneof` coverage proving that each member resolves in order while the title remains the joined human-readable IDs. Use the minimal fixture catalog rather than weakening validation for synthetic IDs.

- [ ] **Step 2: Run compiler/build tests and verify catalog assertions fail**

Run: `python -m unittest tests.test_build_order_compiler tests.test_build_order_build -v`

Expected: FAIL because payloads still contain YAML IDs and `compile_directory` has no `identities` parameter.

- [ ] **Step 3: Implement objective-category and age-up-category selection**

```python
CHECK_ID_CATEGORIES = {
    "built": "entity",
    "buildings": "entity",
    "produce": "squad",
    "units": "squad",
    "upgrades": "upgrade",
}
UPGRADE_AGE_UP_CIVS = frozenset({"abbasid", "ayyubids", "templar", "golden_horde"})

def _identity_category(kind: str, civ: str) -> str:
    if kind == "age_up":
        return "upgrade" if normalize_civ(civ) in UPGRADE_AGE_UP_CIVS else "entity"
    return CHECK_ID_CATEGORIES[kind]

def _resolve_identity_payload(payload, *, kind, civ, identities, file, path):
    category = _identity_category(kind, civ)
    key = "id" if "id" in payload else "oneof"
    human_ids = [payload[key]] if key == "id" else payload[key]
    try:
        canonical = [identities.resolve(civ, category, item) for item in human_ids]
    except IdentityCatalogError as exc:
        _error(file, path, f"civilization '{normalize_civ(civ)}', {kind} check, expected {category} ID: {exc}")
    payload[key] = canonical[0] if key == "id" else canonical
```

Pass `civ` and the loaded identity catalog into `_check_descriptors`. Capture the human IDs before resolution so presentation titles stay readable. Load `DEFAULT_IDENTITY_CATALOG` once at the start of `compile_directory` only when no test catalog is injected.

- [ ] **Step 4: Update existing tests to use real normalized IDs or the minimal catalog**

Replace synthetic catalog-validated IDs (`a`, `age2_a`, `golden_horde_landmark`) with fixture-backed IDs. Keep schema-only invalid tests isolated by injecting a catalog that contains their otherwise valid ID, ensuring the asserted failure remains about the intended field.

Update emitted-payload assertions from human IDs to canonical strings, for example:

```python
self.assertIn(
    'payload = {id = "building_barracks_eng", count = 2, vils = 3, location = "forward"}',
    scar,
)
```

- [ ] **Step 5: Document the author and refresh contracts**

In `docs/build_order_schema.yaml`, state that every building, unit, technology, and age-up ID is the lowercase underscore-normalized official base ID and remove any capability description. In `README.md`, document:

```powershell
python tools/generate_game_identities.py --database E:/path/to/index.sanitized.sqlite3
```

State that the command is developer-only, the generated JSON is committed, and ordinary builds perform catalog validation without accessing that database.

- [ ] **Step 6: Run compiler, build, and full common-base tests**

Run: `python -m unittest tests.test_game_identities tests.test_build_order_compiler tests.test_build_order_build -v`

Expected: PASS.

Run: `python -m unittest discover -s tests -p "test_*.py" -v`

Expected: PASS.

- [ ] **Step 7: Commit compiler integration**

```powershell
git add -- tools/build_orders/compiler.py tests/test_build_order_compiler.py tests/test_build_order_build.py docs/build_order_schema.yaml README.md
git commit -m "feat: validate build order game identities"
```

### Task 4: Civilization in the Runtime Handler Context

**Worktree:** `E:/Docs/github/aoemod/aoe4-macro-trainer/.worktrees/gri-83-objective-checks`

**Files:**
- Modify: `assets/scar/build_orders/objective_engine.scar`
- Modify: `tests/test_build_order_objectives.py`
- Modify: `docs/build_order_check_handlers.md`

**Interfaces:**
- Consumes: generated build order record `{ civ = "...", steps = ... }`.
- Produces: handler context fields `context.localPlayer` and `context.civ`, with `context.civ` cleared by `BuildOrder_Stop`.

- [ ] **Step 1: Write failing lifecycle tests**

```python
def test_engine_exposes_selected_build_civilization_to_handlers(self) -> None:
    self.assertIn("civ = nil", self.source)
    self.assertIn("BUILD_ORDER_STATE.civ = string.lower(buildOrder.civ)", self.source)
    activation = self.source[self.source.index("function BuildOrder_Start"):]
    self.assertLess(
        activation.index("BUILD_ORDER_STATE.civ = string.lower(buildOrder.civ)"),
        activation.index("BuildOrder_ActivateStep(1)"),
    )

def test_stop_clears_civilization_context(self) -> None:
    start = self.source.index("function BuildOrder_Stop")
    end = self.source.index("\nfunction ", start + 1)
    stop = self.source[start:end]
    self.assertIn("BUILD_ORDER_STATE.civ = nil", stop)
```

- [ ] **Step 2: Run the engine contract tests and verify failure**

Run: `python -m unittest tests.test_build_order_objectives -v`

Expected: FAIL because `BUILD_ORDER_STATE` has no `civ` field.

- [ ] **Step 3: Implement context initialization and cleanup**

```lua
BUILD_ORDER_STATE = {
	localPlayer = nil,
	civ = nil,
	-- existing fields remain unchanged
}

function BuildOrder_Start(buildOrder, player)
	BuildOrder_Stop()
	if buildOrder == nil or player == nil then
		return
	end
	BUILD_ORDER_STATE.localPlayer = player
	BUILD_ORDER_STATE.civ = string.lower(buildOrder.civ)
	BUILD_ORDER_STATE.selectedBuild = buildOrder
	BuildOrder_ActivateStep(1)
end
```

Set `BUILD_ORDER_STATE.civ = nil` in `BuildOrder_Stop`. Document `context.civ` as authoritative for civilization-specific behavior and retain `context.localPlayer` as authoritative for player scope.

- [ ] **Step 4: Run objective-engine and full common-base tests**

Run: `python -m unittest tests.test_build_order_objectives -v`

Expected: PASS.

Run: `python -m unittest discover -s tests -p "test_*.py" -v`

Expected: PASS.

- [ ] **Step 5: Commit and publish the common-base interface**

```powershell
git add -- assets/scar/build_orders/objective_engine.scar tests/test_build_order_objectives.py docs/build_order_check_handlers.md
git commit -m "feat: expose build order civilization to checks"
git push origin codex/gri-83-objective-checks
```

Record the resulting common-base commit SHA. Do not begin branch updates until the push succeeds.

### Task 5: GRI-57 Civilization-Driven Age-Up Events

**Worktree:** `E:/Docs/github/aoemod/aoe4-macro-trainer/.worktrees/gri-57-age-up-check`

**Files:**
- Modify: `assets/scar/build_orders/checks/age_up.scar`
- Modify: `tests/test_build_order_age_up.py`
- Modify: `docs/build_order_schema.yaml`
- Modify: `tools/build_orders/compiler.py` only through merging the common base; do not reimplement catalog logic.

**Interfaces:**
- Consumes: common-base `context.civ`, canonical payload identifiers, `GE_ConstructionComplete`, `GE_UpgradeComplete`, `context.localPlayer`, `context.entity`/`context.executer`, and `context.pbg`.
- Produces: capability-free age-up handler with per-check cached PBG tuples and `UPGRADE_AGE_UP_CIVS = { abbasid, ayyubids, templar, golden_horde }`.

- [ ] **Step 1: Merge the common base into the isolated branch**

Run:

```powershell
git fetch origin
git merge --no-edit codex/gri-83-objective-checks
```

Resolve conflicts by retaining GRI-57 presentation behavior while taking the common catalog compiler wholesale. Confirm `git status --short` is clean after the merge commit.

- [ ] **Step 2: Replace capability tests with failing civilization-dispatch tests**

```python
def test_normalized_age_up_ids_compile_to_canonical_upgrade_ids(self) -> None:
    cases = (
        ("abbasid", "economic_wing", "upgrade_add_economy_wing"),
        ("templar", "knights_hospitaller", "upgrade_age_dark_com_1_tem"),
        ("golden_horde", "khan_and_torguuds", "upgrade_tent_dark_1_khan_mon_ha_gol"),
    )
    for civ, human_id, canonical in cases:
        with self.subTest(civ=civ):
            check = self.compile_check(f"{{id: {human_id}}}", civ=civ)
            self.assertFalse(check.optional)
            self.assertEqual(check.payload, {"id": canonical})

def test_runtime_dispatches_on_context_civ_without_capability(self) -> None:
    self.assertIn("civ = context.civ", self.source)
    self.assertIn("AgeUp_UsesUpgradeEvent(state.civ)", self.source)
    self.assertNotIn("capability", self.source)
```

Add Ayyubid coverage with `feudal_economic_wing_growth`, conventional English coverage with `council_hall`, and a compiler rejection test for the removed `capability` field.

- [ ] **Step 3: Run GRI-57 tests and verify failure**

Run: `python -m unittest tests.test_build_order_age_up -v`

Expected: FAIL because the handler still reads `state.payload.capability` and resolves PBGs inside callbacks.

- [ ] **Step 4: Implement cached PBG sets and civilization-selected adapters**

```lua
AGE_UP_UPGRADE_CIVS = {
	abbasid = true,
	ayyubids = true,
	templar = true,
	golden_horde = true,
}

local function AgeUp_ResolvePBGs(payload, civ)
	local pbgs = {}
	local resolver = BP_GetEntityBlueprint
	if AGE_UP_UPGRADE_CIVS[civ] == true then
		resolver = BP_GetUpgradeBlueprint
	end
	if payload.id ~= nil then
		table.insert(pbgs, resolver(payload.id))
	else
		for _, identifier in ipairs(payload.oneof) do
			table.insert(pbgs, resolver(identifier))
		end
	end
	return pbgs
end
```

Store `civ`, `player`, and `pbgs` per check. `AgeUp_OnConstructionComplete` must first require `Entity_GetPlayerOwner(context.entity) == state.player`, then compare `Entity_GetBlueprint(context.entity)` to cached PBGs. `AgeUp_OnUpgradeComplete` must first require `Entity_GetPlayerOwner(context.executer) == state.player`, then compare `context.pbg` to cached PBGs. Register only the event family needed by active states and remove shared listeners when the final matching state deactivates.

Activation baseline reconciliation uses `Player_HasUpgrade(state.player, pbg)` for upgrade civilizations and a player-scoped entity scan that requires completed construction for conventional landmarks. Unsupported or nil `context.civ` logs a diagnostic and leaves the required check incomplete.

- [ ] **Step 5: Run focused and full GRI-57 tests**

Run: `python -m unittest tests.test_build_order_age_up -v`

Expected: PASS.

Run: `python -m unittest discover -s tests -p "test_*.py" -v`

Expected: PASS.

- [ ] **Step 6: Commit and queue validation without building**

```powershell
git add -- assets/scar/build_orders/checks/age_up.scar tests/test_build_order_age_up.py docs/build_order_schema.yaml
git commit -m "fix: select age up events by civilization"
git push origin codex/gri-57-age-up-check
```

Return the commit SHA, test count, normalized test IDs, human and opponent playtest actions, and expected objective transitions to the main task. Do not run the Content Editor.

### Task 6: GRI-56 Canonical Building PBG Cache

**Worktree:** `E:/Docs/github/aoemod/aoe4-macro-trainer/.worktrees/gri-56-built-check`

**Files:**
- Modify: `assets/scar/build_orders/checks/built.scar`
- Modify: `tests/test_build_order_built.py`

**Interfaces:**
- Consumes: common-base canonical entity IDs and existing `GE_ConstructionComplete` human-owner filtering.
- Produces: per-check `pbgs` resolved during activation and reused for baseline/entity-event matching.

- [ ] **Step 1: Merge `codex/gri-83-objective-checks` and write a failing cached-resolution contract**

```python
def test_resolves_entity_blueprints_only_during_activation(self) -> None:
    self.assertIn("pbgs = Built_ResolvePBGs(check.payload)", self.source)
    start = self.source.index("function Built_OnConstructionComplete")
    end = self.source.index("function Built_EnsureEventRegistered", start + 1)
    callback = self.source[start:end]
    self.assertNotIn("BP_GetEntityBlueprint", callback)
    self.assertIn("Built_MatchesPBG(state.pbgs, Entity_GetBlueprint(entity))", callback)
```

Run: `python -m unittest tests.test_build_order_built -v`

Expected: FAIL until cached PBG state is implemented.

- [ ] **Step 2: Implement the cached entity PBG list without weakening player scope**

```lua
local function Built_ResolvePBGs(payload)
	local pbgs = {}
	if payload.id ~= nil then
		table.insert(pbgs, BP_GetEntityBlueprint(payload.id))
	else
		for _, identifier in ipairs(payload.oneof) do
			table.insert(pbgs, BP_GetEntityBlueprint(identifier))
		end
	end
	return pbgs
end
```

Store `pbgs` on `BUILT_STATE[check.id]`. Preserve the existing baseline snapshot, event owner comparison against the stored human player, full PBG equality, count threshold, and spawned/entity deduplication.

- [ ] **Step 3: Run full tests, commit, push, and queue validation**

Run: `python -m unittest discover -s tests -p "test_*.py" -v`

Expected: PASS.

```powershell
git add -- assets/scar/build_orders/checks/built.scar tests/test_build_order_built.py
git commit -m "refactor: cache built objective blueprints"
git push origin codex/gri-56-built-check
```

Return a validation request to the main task; do not build.

### Task 7: GRI-59 Canonical Upgrade PBG Cache

**Worktree:** `E:/Docs/github/aoemod/aoe4-macro-trainer/.worktrees/gri-59-upgrades-check`

**Files:**
- Modify: `assets/scar/build_orders/checks/upgrades.scar`
- Modify: `tests/test_build_order_upgrades.py`

**Interfaces:**
- Consumes: common-base canonical upgrade ID and existing `GE_UpgradeComplete` human-owner filtering.
- Produces: per-check `pbg = BP_GetUpgradeBlueprint(check.payload.id)` resolved at activation and reused by completed and queued paths.

- [ ] **Step 1: Merge the common base and write the failing cache contract**

```python
def test_resolves_upgrade_blueprint_once_at_activation(self) -> None:
    self.assertIn("pbg = BP_GetUpgradeBlueprint(check.payload.id)", self.source)
    start = self.source.index("function Upgrades_OnUpgradeComplete")
    end = self.source.index("function Upgrades_UpdateObservers", start + 1)
    callback = self.source[start:end]
    self.assertIn("context.pbg == state.pbg", callback)
    self.assertNotIn("BP_GetUpgradeBlueprint", callback)
```

Run: `python -m unittest tests.test_build_order_upgrades -v`

Expected: FAIL until state stores `pbg`.

- [ ] **Step 2: Cache the PBG and preserve completed-event and queued-poll semantics**

At activation, store:

```lua
UPGRADES_STATE[check.id] = {
	checkID = check.id,
	player = context.localPlayer,
	pbg = BP_GetUpgradeBlueprint(check.payload.id),
	queued = check.payload.queued,
	completed = false,
}
```

The completion callback must check the executor owner against `state.player` before `context.pbg == state.pbg`. Existing verified queue polling remains unchanged except that it reuses `state.pbg`.

- [ ] **Step 3: Run full tests, commit, push, and queue validation**

Run: `python -m unittest discover -s tests -p "test_*.py" -v`

Expected: PASS.

```powershell
git add -- assets/scar/build_orders/checks/upgrades.scar tests/test_build_order_upgrades.py
git commit -m "refactor: cache upgrade objective blueprints"
git push origin codex/gri-59-upgrades-check
```

Return a validation request to the main task; do not build.

### Task 8: GRI-60 Canonical Production PBG Cache

**Worktree:** `E:/Docs/github/aoemod/aoe4-macro-trainer/.worktrees/gri-60-produce-check`

**Files:**
- Modify: `assets/scar/build_orders/checks/produce.scar`
- Modify: `tests/test_build_order_produce.py`

**Interfaces:**
- Consumes: common-base canonical squad ID and existing `GE_BuildItemComplete` human-owner filtering.
- Produces: per-check `pbg = BP_GetSquadBlueprint(check.payload.id)` resolved at activation and reused for event, baseline, constant, and queued logic.

- [ ] **Step 1: Merge the common base and write the failing cache contract**

```python
def test_resolves_produced_squad_blueprint_once_at_activation(self) -> None:
    self.assertIn("pbg = BP_GetSquadBlueprint(check.payload.id)", self.source)
    start = self.source.index("function Produce_OnBuildItemComplete")
    end = self.source.index("local function Produce_EnsureEventRegistered", start + 1)
    callback = self.source[start:end]
    self.assertIn("context.pbg == state.pbg", callback)
    self.assertNotIn("BP_GetSquadBlueprint", callback)
```

Run: `python -m unittest tests.test_build_order_produce -v`

Expected: FAIL until state stores `pbg`.

- [ ] **Step 2: Cache the PBG and preserve event deduplication**

Add `pbg = BP_GetSquadBlueprint(check.payload.id)` to each state record. Reuse it in the human producer-owner event predicate, spawned-squad PBG verification, baseline count, constant living-count query, and existing verified queue polling. Preserve the current spawned squad/entity dedupe so one completion event increments once.

- [ ] **Step 3: Run full tests, commit, push, and queue validation**

Run: `python -m unittest discover -s tests -p "test_*.py" -v`

Expected: PASS.

```powershell
git add -- assets/scar/build_orders/checks/produce.scar tests/test_build_order_produce.py
git commit -m "refactor: cache production objective blueprints"
git push origin codex/gri-60-produce-check
```

Return a validation request to the main task; do not build.

### Task 9: GRI-62 Canonical Living-Unit PBG Cache

**Worktree:** `E:/Docs/github/aoemod/aoe4-macro-trainer/.worktrees/gri-62-units-check`

**Files:**
- Modify: `assets/scar/build_orders/checks/units.scar`
- Modify: `tests/test_build_order_units.py`

**Interfaces:**
- Consumes: common-base canonical squad ID and the existing human-player living-unit polling contract.
- Produces: per-check cached squad PBG used by the player-scoped count query; polling remains authoritative because the objective is reversible.

- [ ] **Step 1: Merge the common base and write the failing cached-poll contract**

```python
def test_resolves_unit_blueprint_at_activation_not_each_poll(self) -> None:
    self.assertIn("pbg = BP_GetSquadBlueprint(check.payload.id)", self.source)
    start = self.source.index("function Units_Poll")
    end = self.source.index("function Units_Activate", start + 1)
    poll = self.source[start:end]
    self.assertNotIn("BP_GetSquadBlueprint", poll)
    self.assertIn("state.pbg", poll)
```

Run: `python -m unittest tests.test_build_order_units -v`

Expected: FAIL until activation stores `pbg`.

- [ ] **Step 2: Cache the PBG while retaining reversible human-player polling**

Store `pbg` beside `player`, `count`, and `checkID`. Keep the query rooted in `state.player`, recompute living controlled units every poll, and continue calling `BuildOrder_SetCheckComplete(checkID, current >= required)` with both true and false transitions. Do not replace this state check with production events.

- [ ] **Step 3: Run full tests, commit, push, and queue validation**

Run: `python -m unittest discover -s tests -p "test_*.py" -v`

Expected: PASS.

```powershell
git add -- assets/scar/build_orders/checks/units.scar tests/test_build_order_units.py
git commit -m "refactor: cache living unit blueprints"
git push origin codex/gri-62-units-check
```

Return a validation request to the main task; do not build.

### Task 10: Migrate Existing Build-Order YAML to Official Normalized IDs

**Workspace:** `E:/Docs/github/aoemod/build orders`

**Files:**
- Modify: `E:/Docs/github/aoemod/build orders/test_age_templar.yaml`
- Modify: `E:/Docs/github/aoemod/build orders/templar_aggro.yaml`
- Modify: `E:/Docs/github/aoemod/build orders/templar_2tc.yaml`
- Modify any other YAML file rejected by catalog validation solely because it uses a non-official shorthand.

**Interfaces:**
- Consumes: committed default identity catalog and `compile_directory` validation.
- Produces: external build-order sources containing only normalized official base IDs.

- [ ] **Step 1: Apply the known official-ID migrations**

Make these exact replacements in YAML identity fields only:

```text
age_up hospitallers → knights_hospitaller
age_up antioch → principality_of_antioch
aachen → aachen_chapel
meinwerk → meinwerk_palace
regnitz → regnitz_cathedral
swabia → palace_of_swabia
abbey_of_trinity → abbey_of_the_trinity
golden_gate → the_golden_gate
mine → mining_camp
lumber → lumber_camp
archery → archery_range
```

Remove the `built` entries containing `hospitallers` or `antioch` from `templar_2tc.yaml` and `templar_aggro.yaml`: these selections are upgrade identities and have no entity identity. In `templar_2tc.yaml`, replace `age_up: { id: town_center, location: deer }` with `built: [{ id: town_center, location: deer }]`. Correct `test_age_horde.yaml` from `civ: abbasid` to `civ: golden_horde` so `khan_and_torguuds` resolves through the intended civilization.

Do not change titles, hints, comments, resources, counts, or paths beyond those two category corrections.

- [ ] **Step 2: Run compiler validation over the complete external directory**

Run:

```powershell
python -c "from pathlib import Path; from tools.build_orders.compiler import compile_directory; c=compile_directory(Path(r'E:/Docs/github/aoemod/build orders')); print(len(c.build_orders))"
```

Expected: exit 0 and print the number of compiled build orders. If validation names another shorthand, use the official normalized `baseId` already present in `tools/build_orders/data/game_identities.json`, make that exact substitution, and rerun until the directory compiles without an alias or bypass.

- [ ] **Step 3: Verify only identity and intended civilization fields changed**

Run a read-only diff if the external directory is version-controlled; otherwise compare the changed YAML files and record every substitution in the task report. Do not copy generated canonical `attribName` strings into YAML.

### Task 11: Cross-Branch Static Verification and Validation Queue

**Worktrees:** common base plus GRI-56, GRI-57, GRI-59, GRI-60, and GRI-62 worktrees listed above.

**Files:**
- Modify only task reports if the subagent-driven workflow creates them.

**Interfaces:**
- Consumes: pushed common-base and sub-issue commits from Tasks 4–9.
- Produces: evidence-backed validation requests; no mod build until the user selects one.

- [ ] **Step 1: Run the full Python suite in every changed worktree**

Run `python -m unittest discover -s tests -p "test_*.py" -v` separately in each changed worktree. Record command, exit code, and test count. A failure in one branch returns only to that branch's persistent sub-agent.

- [ ] **Step 2: Run whitespace and working-tree checks**

Run `git diff --check` and `git status --short` in each changed worktree. Expected: no whitespace errors and no uncommitted implementation files.

- [ ] **Step 3: Review branch diffs against the common base**

For each branch, run:

```powershell
git diff --stat codex/gri-83-objective-checks...HEAD
git diff --check codex/gri-83-objective-checks...HEAD
```

Confirm the branch owns only its focused handler/tests plus intentional report files. Confirm no branch reintroduces human IDs into compiled payloads, capability metadata, opponent-wide queries, or proactive Content Editor builds.

- [ ] **Step 4: Present the waiting validation queue**

For every ready branch, report issue, branch, absolute worktree, commit SHA, static test evidence, build-order selection, human actions, opponent actions that must be ignored, expected text/transitions, and known limitations. Wait for the user to select one request before invoking the AoE4 build workflow.

---

## Plan Self-Review

- Spec coverage: Tasks 1–2 cover committed deterministic identity data and explicit refresh; Task 3 covers compiler validation, normalized YAML, canonical payloads, errors, and documentation; Task 4 covers runtime civilization context; Task 5 removes capability and implements civilization dispatch; Tasks 6–9 apply cached PBG resolution without weakening human-player semantics; Task 10 migrates shorthand YAML; Task 11 enforces the requested validation queue.
- Placeholder scan: the plan contains no deferred implementation markers. Task 10's validation-driven additional substitutions are bounded by the committed official catalog rather than guessed aliases.
- Type consistency: `IdentityCatalog.resolve(civ, category, identifier) -> str`, category names, `compile_directory(..., identities=None)`, `context.civ`, and cached `pbg`/`pbgs` state names are consistent across producer and consumer tasks.
