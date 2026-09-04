# Build Order Datastore Design

## Goal and scope

Finish the datastore portion of GRI-54 in two stacked branches. The first branch implements GRI-87 by loading compiled build orders from an AoE4 text datastore, merging them over the bundled catalog, and making datastore-only orders selectable through the existing startup modal. The second branch starts from the first and implements GRI-88 plus GRI-103 and its child issues GRI-104 through GRI-107: compile YAML into the datastore and provide `build`, `list`, `delete`, and `extract` commands.

This work does not add the future in-game build-order editor or dynamically modify the static lobby option enum. The modal chooser is the interim path for selecting datastore-only orders.

## Branch and delivery structure

The runtime work lives on `codex/gri-87-datastore-loading` in a project-local worktree. After its automated verification, the branch is built through `tools/build_mod.py` with `E:\Docs\github\aoemod\build orders` as the authoritative YAML directory.

The compiler work lives on a second branch created from the completed GRI-87 head. That branch contains GRI-88 and the complete GRI-103 command family. It is pushed and opened as a pull request whose base is `codex/gri-87-datastore-loading`, so the review contains only compiler/datastore-tooling changes above the runtime prerequisite.

## Canonical datastore

Macro Trainer uses one versioned text datastore named `macroTrainerBuildOrders.rlt`. The engine-facing datastore ID is `macroTrainerBuildOrders`. The file is located under the selected AoE4 profile:

```text
<Windows Documents>/My Games/Age of Empires IV/Users/<profile-id>/datastore/macroTrainerBuildOrders.rlt
```

The compiler resolves the Windows Documents directory through the operating system rather than assuming that it is below `C:\Users`. It discovers profile directories below the AoE4 `Users` directory. With exactly one profile it selects that profile automatically. With zero or multiple profiles it reports a controlled ambiguity error and requires `--profile <profile-id>`. Supplying a profile ID is sufficient even when the profile's `datastore` directory or the datastore file does not exist yet; the compiler creates those paths on its first successful write.

The `.rlt` is normal Lua datastore text with one `LuaDataStore` root. Its logical schema is:

```lua
LuaDataStore = {
    schema_version = 1,
    build_orders = {
        ["english-example"] = {
            id = "english-example",
            civ = "english",
            title = "Example",
            source = "https://example.com/build-order",
            steps = {
                {
                    title = "Opening",
                    checks = {
                        {
                            id = "english-example:1:1",
                            kind = "vils",
                            title = "Assign 7 food",
                            optional = false,
                            payload = { food = 7 },
                        },
                    },
                },
            },
        },
    },
}
```

Only compiled, ready-to-run records are stored. The datastore does not preserve the original YAML document or formatting. Runtime presentation values are literal strings because externally added records cannot depend on localization rows baked into the mod. The optional YAML `link` is stored as `source` metadata for listing and extraction.

Schema version, catalog keys, record IDs, required scalar types, step/check collections, and check payload shapes are validated before a Python command mutates the datastore. An unsupported version or malformed existing file is an error and is never silently replaced. Writes render deterministically and replace the target atomically only after validation and rendering succeed.

## GRI-87 runtime loading and merge

The bundled generated SCAR catalog remains the startup baseline. A focused datastore SCAR module calls `Game_LoadTextDataStore("macroTrainerBuildOrders", "")`, waits until the following rule tick, and retrieves the value with `Game_RetrieveTableData("macroTrainerBuildOrders", false)`, following the behavior established in GRI-86.

The loader accepts only a supported table-shaped datastore. It overlays valid datastore records onto `BUILD_ORDER_CATALOG` by record ID, so a datastore record replaces the bundled record with the same generated ID and unrelated bundled records remain available. Because IDs are deterministically generated from civilization and title, the ID is the canonical interpretation of the issue's "same id/name" replacement rule. Missing files, unavailable data, unsupported versions, and malformed catalogs leave the bundled catalog intact and log a controlled diagnostic rather than aborting match startup.

Build-order startup begins only after the load/retrieval attempt finishes. Cleanup removes any pending datastore-load or startup-pause rule so a late callback cannot start systems after game over.

## Dynamic modal chooser

The existing build-order error modal retains `Continue Without Build Order` as button 1 and adds `Choose Build Order` as button 2. The chooser is reachable both after an invalid/missing lobby selection and when no lobby build order was selected, making datastore-only records usable despite the static lobby enum.

The chooser builds a deterministic list from the merged catalog, filters it to the local player's civilization, and sorts it by title with ID as the tie-breaker. If no compatible orders exist, the normal continue-only error state explains that no compatible dynamic orders are available.

The known message-box API does not provide a dynamic list control, so selection uses a carousel that supports any catalog size. The chooser displays the current order's title, civilization, source when present, and its one-based position in the compatible catalog. Its buttons are `Use This Build Order`, `Next`, `Previous`, and `Cancel`. Next and previous wrap at the ends. Cancel returns to the build-order error modal.

Choosing an order updates `_mod.selectedBuildOrderID`, closes the startup alert, removes the pending pause rule, restores `NORMAL_SIM_RATE`, validates the selected record against the local civilization, and starts `BuildOrder_Start`. It starts the sim-speed cycle only when that setting is enabled. Repeated or late button callbacks are guarded so the build order and cycle cannot start twice.

## Compiler and command interface

The Python compiler retains the immutable compiled model and gains datastore parsing/rendering utilities plus a command entry point. The documented invocation is `python -m tools.build_orders.compiler`. With no subcommand, arguments are parsed as `build`, preserving the requested default-forwarding behavior from GRI-107.

The commands are:

```text
python -m tools.build_orders.compiler [build] <input> [<input> ...] [--profile <id>]
python -m tools.build_orders.compiler list [--profile <id>]
python -m tools.build_orders.compiler delete <id> [<id> ...] [--profile <id>]
python -m tools.build_orders.compiler extract <id> [<id> ...] [--output-dir <dir>] [--profile <id>]
```

Each build input may be a YAML file or a directory recursively containing `.yaml` and `.yml` files. All inputs compile and validate as one batch. Duplicate IDs within the batch are errors. A successful batch replaces datastore records with matching IDs and appends new IDs while preserving unrelated records. The final catalog is rendered in deterministic ID order.

`list` prints a stable table with ID, civilization, title, and source. An absent datastore is treated as an empty catalog; an invalid datastore is an error.

`delete` accepts one or more exact IDs. Unknown IDs produce a controlled nonzero error and no partial write. A successful deletion writes the remaining validated catalog atomically.

`extract` accepts one or more exact IDs and writes one YAML file per record to the current directory unless `--output-dir` is supplied. Unknown IDs or output filename collisions fail before any output is written. Extraction reconstructs valid normalized author YAML from compiled records; it does not promise the original aliases, aggregation, field ordering, comments, or formatting. Canonical game identity IDs and expanded check descriptors are acceptable output because the datastore intentionally stores compiled data only.

## Compatibility with mod packaging

`tools/build_mod.py` remains the sole wrapper for generating packaged assets and invoking Essence. Its existing interface remains valid so the repository's AoE4 mod-build workflow can build GRI-87 with the external YAML directory. The new datastore compiler commands do not invoke Essence and do not rewrite the mod package.

The packaged catalog continues to supply fallback orders and the static lobby enum. The datastore compiler supplies external versioning and management. A later issue may remove the bundled runtime path and add the full in-game editor after the datastore workflow is proven.

## Testing and verification

Runtime SCAR contract tests cover the exact load/retrieve sequencing, fallback behavior, overlay precedence, deterministic compatible-order selection, carousel navigation, cancel behavior, successful selection, idempotence, and cleanup. Existing startup, settings, objective, import-graph, and sim-speed tests remain green.

Python tests cover deterministic `.rlt` round trips, schema rejection, atomic writes, operating-system Documents resolution, profile auto-selection and ambiguity, first-write directory creation, single-file and directory builds, replacement and append semantics, default-to-build argument forwarding, stable list output, all-or-nothing deletion, and normalized extraction. CLI tests assert exit codes and user-facing errors through real temporary files rather than source-text inspection.

Before either branch is described as complete, the full unit-test suite and `git diff --check` run fresh. Before the GRI-87 build, the exact required `tools/build_mod.py --build-orders 'E:\Docs\github\aoemod\build orders'` command is shown for confirmation, then its final exit code and archive result are recorded. The compiler pull request is created only after the stacked branch passes its full verification.
