# aoe4-macro-trainer
App for training macro habits via overlays, gameplay mods, and puzzles/scenarios

## Build orders

Build-order YAML files in `build_orders/` are authoritative. Build outputs under
`assets/` are generated local files and are intentionally ignored by Git. Every
build first resets those files to the checked-in baseline templates, then parses
and validates all YAML before emitting a new catalog.

Use `python tools/build_mod.py --build-orders build_orders --generate-only` to
validate and generate assets without launching the editor (useful for tests).
Ordinary builds validate author-facing IDs against the committed game identity
catalog and do not access an external game database.

Catalog regeneration is a developer-only operation:

```powershell
python tools/generate_game_identities.py --database E:/path/to/index.sanitized.sqlite3
```

The generated JSON is committed so authors and ordinary builds do not need the
source database.

Normal builds require the Age of Empires IV Content Editor launcher at
`F:\Program Files (x86)\Steam\steamapps\common\Age of Empires IV Content Editor\EssenceLauncher.exe`
and must name the authoritative YAML directory so those orders are bundled:

```powershell
python tools/build_mod.py --build-orders '<absolute-path-to-build-orders>'
```

### Player datastore

The standalone compiler stores ready-to-run build orders in the selected Age of
Empires IV profile's `datastore/macroTrainerBuildOrders.rlt`. It resolves the
Windows Documents known folder and automatically selects the profile when there
is exactly one directory under `My Games/Age of Empires IV/Users`. With no
profiles or more than one profile, pass the profile ID (not a filesystem path):

```powershell
python -m tools.build_orders.compiler build build_orders --profile 76561198000000000
```

An explicit profile ID also works before the profile directory or datastore file
exists; the first successful build creates the required directories. `build`
accepts any combination of YAML files and recursively scanned directories. It
replaces matching IDs, appends new IDs, and retains unrelated datastore orders.
The `build` word is optional, so this is equivalent:

```powershell
python -m tools.build_orders.compiler build_orders --profile 76561198000000000
```

With no input argument, the default input is the repository's `build_orders`
directory. The remaining commands are:

```powershell
python -m tools.build_orders.compiler list --profile 76561198000000000
python -m tools.build_orders.compiler delete english-opening english-fast-castle --profile 76561198000000000
python -m tools.build_orders.compiler extract english-opening --output-dir exported --profile 76561198000000000
```

`list` shows each compiled ID, civilization, title, and source. `delete` and
`extract` validate all requested IDs before changing anything. Extraction writes
normalized, recompilable YAML; because the datastore contains compiled data, it
does not preserve original aliases, comments, formatting, or field grouping.

The datastore compiler does not package the mod or invoke Essence. Continue to
use `tools/build_mod.py` for developer asset generation and `.aoe4mod` builds.
