# aoe4-macro-trainer
App for training macro habits via overlays, gameplay mods, and puzzles/scenarios

## Build orders

Build-order YAML is compiled into the active Age of Empires IV player's datastore.
The `.aoe4mod` package contains the objective runtime but no bundled build-order
catalog.

### Importing RTS Overlay and aoe4guides build orders

The build-order compiler can translate an RTS Overlay `.bo` JSON file or an
aoe4guides build URL into authoritative Macro Trainer YAML and store the result
in the player datastore. File and URL input are mutually exclusive:

```powershell
python -m tools.build_orders.compiler import --file "2 TC.bo"
python -m tools.build_orders.compiler import --url "https://aoe4guides.com/builds/<id>"
python -m tools.build_orders.compiler import --file "2 TC.bo" --save_yaml "2 TC.yaml"
```

Import replaces an existing order with the same generated ID, preserves
unrelated datastore records, and accepts `--profile <id>` when the target
profile cannot be selected automatically. `--save_yaml` is additional output;
it writes the translated YAML while the imported order is still stored in the
datastore.

URL import accepts HTTPS build-page and build-API URLs on `aoe4guides.com`.
It extracts the build ID and requests the fixed overlay endpoint; it never
fetches an arbitrary host supplied by the URL. The HTTP client rejects
redirects; it never follows them. The resulting YAML retains the
canonical source link for attribution. Ordinary builds remain offline because
only the explicit import command accesses aoe4guides.

The baseline translation preserves source-step ordering. A step's timestamp is
used as its title, positive food/gold/wood/stone allocations become a `vils`
check, and non-empty notes become ordered hints after HTML entity decoding.
RTS Overlay image tokens are rendered as readable labels, such as `Town Center`
or `Gold`; unknown tokens fall back to a humanized filename. Zero allocations do
not create checks. Age, population, total-villager, and builder fields are
validated but are not converted into inferred actions. Arbitrary-language prose
remains unchanged, and later reviewable translation passes may derive additional
checks from it.

Catalog regeneration is a developer-only operation:

```powershell
python tools/generate_game_identities.py --database E:/path/to/index.sanitized.sqlite3
```

The generated JSON is committed so authors and ordinary builds do not need the
source database.

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

The datastore compiler does not package the mod or invoke Essence.

## Build the mod

Build the checked-in assets directly with the Age of Empires IV Content Editor.
From PowerShell:

```powershell
& 'F:\Program Files (x86)\Steam\steamapps\common\Age of Empires IV Content Editor\EssenceLauncher.exe' --build_mod '<absolute-path-to-Macro Trainer.aoe4mod>' --auto_close_burn_window
```

From Git Bash or another MSYS shell on Windows:

```bash
MSYS2_ARG_CONV_EXCL='*' '/f/Program Files (x86)/Steam/steamapps/common/Age of Empires IV Content Editor/EssenceLauncher.exe' --build_mod '<absolute-Windows-path-to-Macro Trainer.aoe4mod>' --auto_close_burn_window
```
