# GRI-88 and GRI-103 Datastore Compiler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compile YAML files into the Macro Trainer datastore and provide deterministic `build`, `list`, `delete`, and `extract` commands.

**Architecture:** A strict datastore codec maps the existing immutable compiled model to a deterministic LuaDataStore subset and back. A profile resolver selects the AoE4 user directory, while the compiler module's CLI performs validated all-or-nothing catalog operations and reconstructs normalized YAML when extraction is requested.

**Tech Stack:** Python 3 standard library, PyYAML, `unittest`, Windows known-folder resolution.

**Spec:** `docs/superpowers/specs/2026-09-03-build-order-datastore-design.md`

## Global Constraints

- Create the compiler branch from the verified GRI-87 head, not from `main`.
- The datastore contains compiled data only and uses schema version `1`.
- Every mutation validates the complete existing datastore and the complete requested operation before replacing the file.
- An absent datastore is an empty catalog; a malformed or unsupported datastore is never overwritten.
- With exactly one AoE4 profile, no `--profile` argument is needed; zero or multiple profiles require it.
- `tools/build_mod.py` remains the only mod/Essence build wrapper.

---

### Task 1: Deterministic compiled-catalog datastore codec

**Files:**
- Create: `tools/build_orders/datastore.py`
- Create: `tests/test_build_order_datastore_codec.py`

**Interfaces:**
- Consumes: `Catalog`, `BuildOrder`, `Step`, and `CheckDescriptor` from `tools.build_orders.model`.
- Produces: `DatastoreError`, `parse_datastore(text: str) -> Catalog`, `render_datastore(catalog: Catalog) -> str`, `load_datastore(path: Path) -> Catalog`, and `write_datastore(path: Path, catalog: Catalog) -> None`.

- [ ] **Step 1: Add failing deterministic render and round-trip tests**

Use a literal compiled fixture and hand-derived assertions:

```python
ORDER = BuildOrder(
    "english-opening", "english", "Opening",
    (Step("Economy", (CheckDescriptor("vils", "Assign 7 food", False, {"food": 7}),)),),
    "https://example.com/opening",
)

def test_render_uses_versioned_lua_root_and_sorted_ids(self):
    text = render_datastore(Catalog((self.zulu, ORDER)))
    self.assertTrue(text.startswith("LuaDataStore = {\n    schema_version = 1,"))
    self.assertLess(text.index('["english-opening"]'), text.index('["zulu-opening"]'))
    self.assertIn('source = "https://example.com/opening"', text)

def test_parse_round_trips_the_compiled_model(self):
    text = render_datastore(Catalog((ORDER,)))
    self.assertEqual(parse_datastore(text), Catalog((ORDER,)))
```

- [ ] **Step 2: Run codec tests and verify RED**

Run `python -m unittest tests.test_build_order_datastore_codec -v` and confirm import failure for the missing datastore module.

- [ ] **Step 3: Implement the renderer and strict Lua subset parser**

Implement escaping for backslash, quote, CR, LF, and tab. The parser accepts only the generated subset: assignment to `LuaDataStore`, tables, bracketed string keys, identifier keys, strings, integers, booleans, and `nil`. It does not execute Lua. Convert the parsed root into immutable model objects only after validating schema version, exact key/ID agreement, scalar types, arrays, and payload values.

- [ ] **Step 4: Add failing malformed-input and atomic-write tests**

Cover unsupported versions, duplicate table keys, mismatched record IDs, malformed arrays, trailing executable text, and invalid payload values. Add a real-filesystem mutation test:

```python
def test_invalid_existing_datastore_is_not_replaced(self):
    path = self.root / "macroTrainerBuildOrders.rlt"
    path.write_text("LuaDataStore = { schema_version = 99 }", encoding="utf-8")
    before = path.read_bytes()
    with self.assertRaises(DatastoreError):
        load_datastore(path)
    self.assertEqual(path.read_bytes(), before)
```

Require `write_datastore` to write a sibling `.tmp`, replace only after full rendering, and remove a leftover temporary on failure.

- [ ] **Step 5: Run RED, implement validation/atomic I/O, and run GREEN**

Run the new failure cases, implement the minimal validation and I/O, then re-run the codec suite and `tests.test_build_order_compiler`.

- [ ] **Step 6: Commit the codec**

Run `git diff --check`, then:

```powershell
git add -- tools/build_orders/datastore.py tests/test_build_order_datastore_codec.py
git commit -m "feat: add compiled build order datastore codec"
```

### Task 2: AoE4 profile discovery

**Files:**
- Create: `tools/build_orders/profiles.py`
- Create: `tests/test_build_order_profiles.py`

**Interfaces:**
- Produces: `ProfileResolutionError` and `resolve_datastore_path(profile_id: str | None, documents_dir: Path | None = None) -> Path`.

- [ ] **Step 1: Add failing profile-resolution tests**

Use temporary Documents trees to prove: one profile auto-selects; multiple profiles require `--profile`; zero profiles require `--profile`; a supplied profile creates no directories during resolution; and invalid profile IDs containing separators or `..` are rejected. Assert the exact suffix `My Games/Age of Empires IV/Users/<id>/datastore/macroTrainerBuildOrders.rlt`.

- [ ] **Step 2: Run tests and verify RED**

Run `python -m unittest tests.test_build_order_profiles -v`. Expected: import failure for the missing module.

- [ ] **Step 3: Implement known-folder and profile logic**

When `documents_dir` is absent, obtain Documents through the Windows known-folder API exposed by `ctypes`/`SHGetKnownFolderPath`; isolate this behind `_documents_directory()` so tests inject a path. Enumerate only direct child directories of `Users`. Accept a supplied profile ID even if its directory does not exist, but reject empty, absolute, dot, dot-dot, or separator-containing values.

- [ ] **Step 4: Run GREEN and commit**

Run the focused tests plus `git diff --check`, then commit:

```powershell
git add -- tools/build_orders/profiles.py tests/test_build_order_profiles.py
git commit -m "feat: discover AoE4 datastore profiles"
```

### Task 3: File-or-directory compilation and datastore build operation

**Files:**
- Modify: `tools/build_orders/compiler.py`
- Modify: `tools/build_orders/datastore.py`
- Modify: `tests/test_build_order_compiler.py`
- Create: `tests/test_build_order_compiler_cli.py`

**Interfaces:**
- Produces: `compile_inputs(inputs: list[Path], identities: IdentityCatalog | None = None) -> Catalog` and `merge_catalog(existing: Catalog, incoming: Catalog) -> Catalog`.

- [ ] **Step 1: Add failing single-file, multi-input, collision, replacement, and append tests**

Use real YAML files. Assert that a file input compiles one order, directories recurse in stable relative-path order, batch duplicate IDs fail before datastore mutation, incoming IDs replace old records, unrelated records remain, and final records sort by ID.

- [ ] **Step 2: Run tests and verify RED**

Run `python -m unittest tests.test_build_order_compiler tests.test_build_order_compiler_cli -v`. Expected: failures because `compile_inputs` and `merge_catalog` do not exist.

- [ ] **Step 3: Refactor directory compilation through `compile_inputs`**

Keep the existing validation behavior and error paths. `compile_directory(input_dir, identities)` becomes a compatibility wrapper over `compile_inputs([input_dir], identities)`. Reject nonexistent paths and non-YAML file inputs with `BuildOrderValidationError`. Detect duplicate generated IDs across the entire batch.

- [ ] **Step 4: Implement the build operation and verify GREEN**

The command-layer build function resolves the datastore path, loads an absent file as `Catalog(())`, compiles the complete input batch, merges in memory, and calls `write_datastore` once. Re-run the compiler, codec, and CLI suites.

- [ ] **Step 5: Commit build support**

```powershell
git add -- tools/build_orders/compiler.py tools/build_orders/datastore.py tests/test_build_order_compiler.py tests/test_build_order_compiler_cli.py
git commit -m "feat: compile YAML into build order datastore"
```

### Task 4: GRI-103 command family

**Files:**
- Modify: `tools/build_orders/compiler.py`
- Modify: `tools/build_orders/datastore.py`
- Modify: `tests/test_build_order_compiler_cli.py`
- Modify: `README.md`

**Interfaces:**
- Produces: `main(argv: list[str] | None = None) -> int`, default-to-build argument forwarding, and the `build`, `list`, `delete`, and `extract` CLI contracts.

- [ ] **Step 1: Add failing parser/default-forwarding tests**

Invoke `[sys.executable, "-m", "tools.build_orders.compiler", ...]` against temporary Documents trees. Prove that both `build order.yaml --profile 123` and `order.yaml --profile 123` create the same datastore bytes. Assert validation failures return `2`, operational/profile/datastore errors return `3`, and no traceback reaches stderr.

- [ ] **Step 2: Run tests and verify RED, then implement parser dispatch**

Use `argparse` subparsers. Before parsing, prepend `build` when the first non-option token is not one of `build`, `list`, `delete`, or `extract`; prepend it for an empty argument list as well so default input can be `build_orders`. Keep `--profile` available on every command.

- [ ] **Step 3: Add failing stable-list tests and implement `list`**

Assert a literal header and ID-sorted rows with columns `ID`, `CIV`, `TITLE`, and `SOURCE`. Use standard-library formatting with calculated widths; do not add a table dependency. An absent datastore prints the header and no records.

- [ ] **Step 4: Add failing all-or-nothing delete tests and implement `delete`**

Test multiple exact IDs, duplicate requested IDs, an unknown ID mixed with a known ID, and deletion to an empty versioned catalog. Unknown IDs return nonzero and preserve the original bytes. Write once only after every requested ID is validated.

- [ ] **Step 5: Add failing normalized extraction tests**

Construct compiled records covering every supported check kind and assert that extraction produces YAML which recompiles successfully to an equivalent runtime catalog after normalization. Also test default current-directory output, `--output-dir`, unknown IDs, and filename collisions before any output write.

- [ ] **Step 6: Implement normalized compiled-to-YAML extraction**

Map compiled descriptors back to accepted YAML shapes. Preserve `civ`, `title`, optional source as `link`, step titles, check order, optionality/queued flags, canonical identity IDs, counts, and payload fields. Where compilation expanded one YAML field into several descriptors, emit a valid explicit representation that recompiles to the same descriptor sequence. Render through `yaml.safe_dump(..., sort_keys=False, allow_unicode=True)` and use atomic per-file staging; validate every target before replacing any output.

- [ ] **Step 7: Run command suites and update documentation**

Run:

```powershell
python -m unittest tests.test_build_order_compiler_cli tests.test_build_order_datastore_codec tests.test_build_order_profiles tests.test_build_order_compiler -v
```

Document profile discovery, first-time creation, all command forms, default-to-build behavior, normalized extraction limitations, and separation from `tools/build_mod.py` in `README.md`.

- [ ] **Step 8: Commit the command family**

```powershell
git add -- tools/build_orders/compiler.py tools/build_orders/datastore.py tests/test_build_order_compiler_cli.py README.md
git commit -m "feat: manage datastore build orders from CLI"
```

### Task 5: Stacked-branch verification and pull request

**Files:**
- Verify only.

**Interfaces:**
- Consumes: compiler branch based on the pushed GRI-87 head.
- Produces: a pushed compiler branch and pull request targeting `codex/gri-87-datastore-loading`.

- [ ] **Step 1: Run fresh complete verification**

Run:

```powershell
python -m unittest discover -s tests -v
python -m tools.build_orders.compiler --help
python -m tools.build_orders.compiler list --profile 76561198050151767
git diff --check
git status --short
```

The real-profile list command is read-only. Do not run a real-profile build, delete, or extract during verification.

- [ ] **Step 2: Review branch ownership and commits**

Compare the compiler branch with `codex/gri-87-datastore-loading`. Confirm the diff contains only datastore codec/profile/compiler/CLI tests and documentation expected by GRI-88/103/104-107. Confirm no generated assets or user data are tracked.

- [ ] **Step 3: Push the compiler branch**

Push with upstream tracking after resolving the exact branch name:

```powershell
git push -u origin codex/gri-88-103-datastore-compiler
```

- [ ] **Step 4: Create the stacked pull request**

Create a PR with base `codex/gri-87-datastore-loading` and head `codex/gri-88-103-datastore-compiler`. The title names GRI-88 and GRI-103. The body summarizes all child commands, compiled-only schema, profile discovery, normalized extraction, and fresh test evidence; it also states that GRI-87 is the prerequisite base.

- [ ] **Step 5: Report delivery state**

Provide the GRI-87 branch/commit, GRI-87 build result and archive, compiler branch/commit range, complete test count, and PR link. Explicitly call out any remaining manual in-game validation for datastore loading and modal interaction.

