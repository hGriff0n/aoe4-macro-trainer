# GRI-83 post-merge reconciliation

## Scope and source commits

- GRI-56 local-only `d82ea824e63889d0572c956f4cc0cea97cd3f6e8` (`fix: show built objective counts`) and `1005c93a2d15b81a3b1ea009fe1a54d91c24c8a7` (`test: cover built choice counts`) were reconciled manually. Their compiler hunk was compatible, but their compiler test context conflicted with the integrated squad-family fixture and tests.
- GRI-58 `22de6d4b78e77ce0b441d1a4c31a03feaf132dc5` (`fix: make resource checks load and share named polling`) was reconciled manually. Its resource-handler behavior was retained; `b87bf1874ad4dc1c142cb577d38ee4daeae7bda4` was not cherry-picked because its duplicate import walker was replaced by assertions on the current shared import-graph helper.
- GRI-59 packaging semantics from `c6be58e04515884e819f317f615e920475161c42` were reconciled without changing `upgrades.scar`: root import coverage belongs in the existing import-graph test. The integration merge also left the compiler caller/signature, upgrade canonicalization/title, production count, and an unclosed compiler-test parenthesis inconsistent.

## Reconciled behavior

- Built check titles are `Build <label>` or `Build <count> <label>`, including counted `oneof` entries.
- The compiler helper accepts the caller's `civ` and `IdentityCatalog`, preserves squad-family resolution, restores non-upgrade count initialization, resolves upgrades canonically, and humanizes author IDs before completed/optional/queued title composition. Covered examples include `Queue fitted leatherwork for research` and `Queue wheelbarrow 1 for research`.
- Resource descriptors remain per-resource; positive villager splits compile as one aggregate descriptor with compact ordered titles, while `no_collect` constraints remain separate villager descriptors.
- Resources use one named `Resources_PollAll` interval listener, added on the first active descriptor and removed after the last; the handler remains scoped to `context.localPlayer` / stored state player.
- The packaged root imports resources and upgrades once each after the objective engine and before startup. Manual verification confirmed all seven handlers (`vils`, `built`, `age_up`, `resources`, `upgrades`, `produce`, `units`) appear exactly once in that interval.

## Red/green evidence

Initial focused evidence:

1. `python -m unittest tests.test_build_order_compiler -v` failed to load due to the missing closing `)` at line 329.
2. After restoring test syntax and adding the requested assertions, focused compiler/resource/upgrade tests failed with `_check_descriptors() takes 4 positional arguments but 6 were given`; resources also lacked `Resources_PollAll`, and import-graph tests observed zero packaged resources/upgrades imports.
3. After the first compiler repair, the integrated squad-family test exposed `KeyError: 'count'` in `produce`; restoring non-upgrade count initialization made it green.
4. The shared compiler's `no_collect` and villager-title tests then failed against the stale aggregate-villager implementation. Per-resource expectations were added first and failed; routing villager descriptors through `_resource_checks` made them green.

Green results:

- Focused required suite: `python -m unittest tests.test_build_order_compiler tests.test_build_order_built tests.test_build_order_resources tests.test_build_order_upgrades tests.test_build_order_import_graph tests.test_build_order_objectives tests.test_build_order_build -v` — 110 tests, OK.
- Final full suite: `$env:PYTHONDONTWRITEBYTECODE='1'; python -m unittest discover -s tests` — 241 tests, OK. The first sandboxed attempt could not create host temporary directories; rerunning with approved host-temp access passed.
- `python tools/build_mod.py --build-orders 'E:\Docs\github\aoemod\build orders' --generate-only` — exit 0.
- `git diff --check` — exit 0.

## Files changed

- `assets/scar/build_orders/checks/resources.scar`
- `assets/scar/winconditions/Macro Trainer.scar`
- `tools/build_orders/compiler.py`
- `tests/test_build_order_compiler.py`
- `tests/test_build_order_import_graph.py`
- `tests/test_build_order_resources.py`
- `tests/test_build_order_upgrades.py`

## Self-review and final status

- `upgrades.scar` was intentionally left unchanged; its existing runtime/player-owner checks remain intact.
- Built, resource, and upgrade flows retain local-human player scoping; no handler import was duplicated or removed.
- The constant-production implementation and squad-family IDs/titles are covered by the passing compiler/produce-related tests and were not reverted.
- Final integration commit: `fix: reconcile post-merge objective checks` (this commit contains the report).

## Fix round: restore GRI-55 aggregate villager splits

Review identified that the first reconciliation incorrectly routed `vils` through `_resource_checks`. The user-validated `codex/gri-55-vils-check` head `6a99d47` instead compiles positive splits into one descriptor with the payload `{food, gold, wood, stone}` and a compact resource-order title.

- Red: after restoring aggregate expectations, `python -m unittest tests.test_build_order_compiler.BuildOrderCompilerTests.test_compiles_single_mapping_with_canonical_immutable_model tests.test_build_order_compiler.BuildOrderCompilerTests.test_vils_mapping_compiles_one_aggregate_descriptor_in_resource_order tests.test_build_order_compiler.BuildOrderCompilerTests.test_supports_all_documented_check_shapes -v` failed 2 assertions: current output used individual `villagers` titles/payloads. The `no_collect` shape still passed.
- Fix: restored `RESOURCE_ORDER` and `_vils_check`; it builds exactly one positive threshold descriptor in food/gold/wood/stone order and appends validated `no_collect` descriptors separately. Resources continue using `_resource_checks`.
- Green: `python -m unittest tests.test_build_order_compiler tests.test_build_order_vils tests.test_build_order_build -v` — 51 tests, OK.
- Final verification: full discovery with host temp access — 241 tests, OK; `python tools/build_mod.py --build-orders 'E:\Docs\github\aoemod\build orders' --generate-only` — exit 0; `git diff --check` — exit 0.
- Fix-round commit: `fix: restore aggregate villager splits` (this commit appends this evidence).
